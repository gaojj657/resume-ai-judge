import hashlib
import io
import json
import secrets
import time
import zipfile
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from cryptography.fernet import Fernet
from flask import Blueprint, current_app, session, request, jsonify, render_template, redirect, url_for, Response, send_file
from PIL import Image
from sqlalchemy import select, delete, or_, func
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from .db import transaction
from .models import User, Job, Candidate, Resume, Evaluation, Recruitment, StageEvent, Task, TaskEvent, Setting, now
from .services import BusinessError, get, validate_criteria, create_evaluations, decision, change_stage, dashboard, STAGES
from .tasks import add_task
from .ai import settings
from .job_seeding import seed_jobs_in_session

bp = Blueprint("web", __name__)
login_attempts = defaultdict(deque)


def serialize(item):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BusinessError("请提交JSON对象")
    return data


def text(data, key, required=False, limit=100000):
    value = data.get(key, "")
    if not isinstance(value, str) or len(value) > limit:
        raise BusinessError(f"字段{key}不合法或过长")
    value = value.strip()
    if required and not value:
        raise BusinessError(f"请填写{key}")
    return value


@bp.before_app_request
def guard():
    session.setdefault("csrf", secrets.token_hex(32))
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not isinstance(token, str) or not secrets.compare_digest(token, session["csrf"]):
            raise BusinessError("页面会话已失效，请刷新后重试", 403)
    public = {"web.login", "web.setup", "static"}
    if request.endpoint not in public and not session.get("user_id"):
        if request.path.startswith("/api/"):
            raise BusinessError("请先登录", 401)
        return redirect(url_for("web.login"))


@bp.app_errorhandler(BusinessError)
def business_error(error):
    return jsonify(error={"code": "business_error", "message": str(error)}), error.status


@bp.app_errorhandler(HTTPException)
def http_error(error):
    messages = {413: "文件超过上传大小限制", 404: "页面或记录不存在", 400: "请求格式不合法"}
    if request.path.startswith("/api/"):
        return jsonify(error={"code": str(error.code), "message": messages.get(error.code, "请求失败")}), error.code
    return render_template("error.html", message=messages.get(error.code, "请求失败")), error.code


@bp.app_errorhandler(Exception)
def unexpected_error(error):
    current_app.logger.error("未预期错误：%s", type(error).__name__)
    if request.path.startswith("/api/"):
        return jsonify(error={"code": "internal_error", "message": "服务暂时异常，请重试"}), 500
    return render_template("error.html", message="服务暂时异常，请重试"), 500


@bp.app_context_processor
def context():
    return {"csrf_token": session.get("csrf", ""), "stages": STAGES, "username": session.get("username", ""),
            "demo_mode": current_app.config.get("DEMO_MODE", False)}


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    with transaction(current_app) as db:
        exists = db.scalar(select(User.id))
    if exists:
        return redirect(url_for("web.login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or len(username) > 100 or len(password) < 10:
            return render_template("auth.html", setup=True, error="用户名必填，密码至少10位"), 400
        with transaction(current_app, write=True) as db:
            if db.scalar(select(User.id)):
                raise BusinessError("管理员已创建", 409)
            user = User(username=username, password_hash=generate_password_hash(password))
            db.add(user)
            seed_jobs_in_session(db)
            db.flush()
            user_id = user.id
        session.clear()
        session.update(user_id=user_id, username=username, csrf=secrets.token_hex(32))
        return redirect("/")
    return render_template("auth.html", setup=True)


@bp.route("/login", methods=["GET", "POST"])
def login():
    with transaction(current_app) as db:
        if not db.scalar(select(User.id)):
            return redirect(url_for("web.setup"))
    error = None
    if request.method == "POST":
        attempts = login_attempts[request.remote_addr]
        while attempts and attempts[0] < time.monotonic() - 300:
            attempts.popleft()
        if len(attempts) >= 10:
            return render_template("auth.html", error="尝试过于频繁，请5分钟后重试"), 429
        with transaction(current_app) as db:
            user = db.scalar(select(User).where(User.username == request.form.get("username", "")))
            if user and check_password_hash(user.password_hash, request.form.get("password", "")):
                session.clear()
                session.update(user_id=user.id, username=user.username, csrf=secrets.token_hex(32))
                attempts.clear()
                return redirect("/")
        attempts.append(time.monotonic())
        error = "用户名或密码错误"
    return render_template("auth.html", error=error)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.login"))


@bp.get("/")
def home():
    return render_template("dashboard.html", page="dashboard", title="招聘概览", subtitle="从简历匹配到入职，把招聘进展看清楚。")


@bp.get("/jobs")
def jobs_page():
    return render_template("jobs.html", page="jobs", title="岗位管理", subtitle="把岗位要求变成清晰、可解释的100分标准。")


@bp.get("/upload")
def upload_page():
    return render_template("upload.html", page="upload", title="简历评估", subtitle="上传简历，确认信息，选择岗位，获得匹配分析。")


@bp.get("/evaluations")
def evaluations_page():
    return render_template("evaluations.html", page="evaluations", title="评估记录", subtitle="保留每一次判断，回看报告并决定是否推进。")


@bp.get("/evaluations/<int:id>")
def report_page(id):
    with transaction(current_app) as db:
        get(db, Evaluation, id)
    return render_template("report.html", page="evaluations", title="匹配分析报告", subtitle="有依据的评分，保留你的最终判断。", evaluation_id=id)


@bp.get("/candidates")
def candidates_page():
    return render_template("candidates.html", page="candidates", title="候选人进度", subtitle="仅显示已推进的候选人，各岗位独立跟踪。")


@bp.get("/settings")
def settings_page():
    return render_template("settings.html", page="settings", title="模型设置", subtitle="连接OpenAI，为匹配分析提供模型能力。")


@bp.route("/api/jobs", methods=["GET", "POST"])
def jobs_api():
    with transaction(current_app, write=request.method == "POST") as db:
        if request.method == "GET":
            return jsonify(items=[serialize(j) for j in db.scalars(select(Job).order_by(Job.id.desc()))])
        data = body()
        validate_criteria(data.get("criteria"))
        job = Job(name=text(data, "name", True, 200), jd=text(data, "jd", True),
                  description=text(data, "description"), criteria=data["criteria"])
        db.add(job)
        db.flush()
        return jsonify(serialize(job)), 201


@bp.route("/api/jobs/<int:id>", methods=["GET", "PATCH"])
def job_api(id):
    with transaction(current_app, write=request.method == "PATCH") as db:
        job = get(db, Job, id)
        if request.method == "PATCH":
            data = body()
            if data.get("version") != job.version:
                raise BusinessError("岗位已更新，请刷新后再保存", 409)
            if "name" in data:
                job.name = text(data, "name", True, 200)
            if "jd" in data:
                job.jd = text(data, "jd", True)
            if "description" in data:
                job.description = text(data, "description")
            if "criteria" in data:
                job.criteria = validate_criteria(data["criteria"])
            if "status" in data:
                if data["status"] not in ("open", "closed"):
                    raise BusinessError("岗位状态不合法")
                job.status = data["status"]
            job.version, job.updated_at = job.version + 1, now()
        return jsonify(serialize(job))


@bp.post("/api/jobs/draft")
def job_draft():
    data = body()
    with transaction(current_app, write=True) as db:
        task = add_task(db, "draft", 0, {"jd": text(data, "jd", True)})
        return jsonify(task_id=task.id), 202


def validate_upload(content, suffix):
    if suffix == ".pdf":
        if not content.lstrip().startswith(b"%PDF-"):
            raise BusinessError("文件内容不是有效PDF")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise BusinessError("文件内容不是有效DOCX")
                if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                    raise BusinessError("DOCX解压体积过大")
        except zipfile.BadZipFile as exc:
            raise BusinessError("Word文件已损坏") from exc
    else:
        try:
            with Image.open(io.BytesIO(content)) as image:
                expected = "PNG" if suffix == ".png" else "JPEG"
                if image.format != expected:
                    raise BusinessError("图片格式与后缀不一致")
                if image.width * image.height > 40_000_000:
                    raise BusinessError("图片尺寸过大")
                image.verify()
        except (OSError, Image.DecompressionBombError) as exc:
            raise BusinessError("图片已损坏或尺寸过大") from exc


@bp.route("/api/resumes", methods=["GET", "POST"])
def resumes_api():
    if request.method == "GET":
        with transaction(current_app) as db:
            rows = list(db.scalars(select(Resume).where(Resume.purpose == "resume").order_by(Resume.id.desc()).limit(100)))
            return jsonify(items=[resume_data(db, r) for r in rows])
    files = request.files.getlist("files")
    if not 1 <= len(files) <= 5:
        raise BusinessError("每次上传1—5份文件")
    purpose = request.form.get("purpose", "resume")
    if purpose not in ("resume", "jd"):
        raise BusinessError("上传用途不合法")
    pending = []
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".pdf", ".docx", ".png", ".jpg", ".jpeg"):
            raise BusinessError("支持PDF、DOCX、PNG、JPG，不支持旧版DOC")
        content = file.read()
        validate_upload(content, suffix)
        pending.append((file.filename[:250], uuid4().hex + suffix, content))
    results, written = [], []
    try:
        with transaction(current_app, write=True) as db:
            for filename, storage, content in pending:
                path = Path(current_app.config["DATA_DIR"]) / "uploads" / storage
                path.write_bytes(content)
                written.append(path)
                sha = hashlib.sha256(content).hexdigest()
                duplicates = list(db.scalars(select(Resume.id).where(Resume.sha256 == sha, Resume.purpose == purpose)))
                resume = Resume(filename=filename, path=storage, sha256=sha, purpose=purpose)
                db.add(resume)
                db.flush()
                task = add_task(db, "parse", resume.id)
                results.append({"resume_id": resume.id, "task_id": task.id, "filename": filename, "duplicates": duplicates})
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return jsonify(items=results), 202


def resume_data(db, resume):
    result = serialize(resume)
    result.pop("path")
    if resume.candidate_id:
        result["candidate"] = serialize(get(db, Candidate, resume.candidate_id))
    task = db.scalar(select(Task).where(Task.kind == "parse", Task.target_id == resume.id).order_by(Task.id.desc()))
    result["task_id"] = task.id if task else None
    return result


@bp.route("/api/resumes/<int:id>", methods=["GET", "PATCH"])
def resume_api(id):
    with transaction(current_app, write=request.method == "PATCH") as db:
        resume = get(db, Resume, id)
        if request.method == "PATCH":
            data = body()
            if resume.status != "succeeded":
                raise BusinessError("解析完成后才能修改文本")
            if data.get("revision") != resume.revision:
                raise BusinessError("简历已更新，请刷新后重试", 409)
            resume.markdown = text(data, "markdown", True)
            resume.revision += 1
            resume.extracted = {}
        return jsonify(resume_data(db, resume))


@bp.post("/api/resumes/<int:id>/retry")
def resume_retry(id):
    with transaction(current_app, write=True) as db:
        resume = get(db, Resume, id)
        if resume.status != "failed":
            raise BusinessError("只有失败的解析任务可重试")
        resume.status, resume.error = "queued", ""
        task = add_task(db, "parse", resume.id)
        return jsonify(task_id=task.id), 202


@bp.post("/api/resumes/<int:id>/extract")
def extract(id):
    with transaction(current_app, write=True) as db:
        resume = get(db, Resume, id)
        if resume.status != "succeeded":
            raise BusinessError("请先完成解析")
        task = add_task(db, "extract", resume.id, {"markdown": resume.markdown, "revision": resume.revision})
        return jsonify(task_id=task.id), 202


@bp.post("/api/resumes/<int:id>/candidate")
def link_candidate(id):
    data = body()
    with transaction(current_app, write=True) as db:
        resume = get(db, Resume, id)
        if resume.status != "succeeded" or resume.purpose != "resume":
            raise BusinessError("请先完成简历解析")
        if resume.candidate_id:
            raise BusinessError("简历已关联候选人；请上传新的简历版本变更归属", 409)
        if data.get("candidate_id"):
            candidate = get(db, Candidate, data["candidate_id"])
        else:
            candidate = Candidate(name=text(data, "name", True, 200), phone=text(data, "phone", limit=100),
                                  email=text(data, "email", limit=200), education=text(data, "education", limit=300), major=text(data, "major", limit=300))
            db.add(candidate)
            db.flush()
        resume.candidate_id = candidate.id
        return jsonify(candidate=serialize(candidate))


@bp.get("/api/candidates")
def candidates_api():
    q = request.args.get("q", "").strip()[:200]
    with transaction(current_app) as db:
        stmt = select(Candidate).order_by(Candidate.id.desc())
        if q:
            stmt = stmt.where(or_(Candidate.name.contains(q), Candidate.phone.contains(q), Candidate.email.contains(q)))
        return jsonify(items=[serialize(c) for c in db.scalars(stmt.limit(100))])


@bp.get("/api/resumes/<int:id>/file")
def file_api(id):
    with transaction(current_app) as db:
        resume = get(db, Resume, id)
        return send_file(Path(current_app.config["DATA_DIR"]) / "uploads" / resume.path,
                         as_attachment=True, download_name=resume.filename)


def evaluation_data(db, ev):
    result = serialize(ev)
    result["candidate"] = serialize(get(db, Candidate, ev.candidate_id))
    result["job_name"] = ev.snapshot["job_name"]
    result["resume_filename"] = get(db, Resume, ev.resume_id).filename
    task = db.scalar(select(Task).where(Task.kind == "evaluate", Task.target_id == ev.id).order_by(Task.id.desc()))
    result["task_id"] = task.id if task else None
    rec = db.scalar(select(Recruitment).where(Recruitment.candidate_id == ev.candidate_id, Recruitment.job_id == ev.job_id))
    result["recruitment"] = serialize(rec) if rec else None
    return result


@bp.route("/api/evaluations", methods=["GET", "POST"])
def evaluations_api():
    with transaction(current_app, write=request.method == "POST") as db:
        if request.method == "POST":
            data = body()
            key = text(data, "idempotency_key", True, 100)
            ids = data.get("job_ids")
            if not isinstance(ids, list) or not 1 <= len(ids) <= 20 or any(type(id) is not int for id in ids) or len(set(ids)) != len(ids):
                raise BusinessError("请选择1—20个不同岗位")
            existing = list(db.scalars(select(Evaluation).where(Evaluation.batch_key == key)))
            if existing:
                if any(e.resume_id != data.get("resume_id") for e in existing) or {e.job_id for e in existing} != set(data.get("job_ids", [])):
                    raise BusinessError("重复请求键与提交内容不一致", 409)
                return jsonify(items=[{"evaluation_id": e.id, "task_id": evaluation_data(db, e)["task_id"], "job_name": e.snapshot["job_name"]} for e in existing])
            resume = get(db, Resume, data.get("resume_id"))
            return jsonify(items=create_evaluations(db, resume, [get(db, Job, id) for id in ids], key)), 202
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            raise BusinessError("分页参数不合法")
        stmt = select(Evaluation).join(Candidate).order_by(Evaluation.id.desc())
        if request.args.get("job_id"):
            stmt = stmt.where(Evaluation.job_id == request.args["job_id"])
        q = request.args.get("q", "").strip()[:200]
        if q:
            stmt = stmt.where(or_(Candidate.name.contains(q), Candidate.phone.contains(q)))
        count = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        rows = list(db.scalars(stmt.offset((page - 1) * 20).limit(20)))
        return jsonify(items=[evaluation_data(db, e) for e in rows], total=count, page=page)


@bp.get("/api/evaluations/<int:id>")
def evaluation_api(id):
    with transaction(current_app) as db:
        return jsonify(evaluation_data(db, get(db, Evaluation, id)))


@bp.post("/api/evaluations/<int:id>/retry")
def evaluation_retry(id):
    data = body()
    key = text(data, "idempotency_key", True, 100)
    with transaction(current_app, write=True) as db:
        ev = get(db, Evaluation, id)
        if ev.status in ("queued", "running"):
            raise BusinessError("请等待当前评估结束")
        existing = db.scalar(select(Evaluation).where(Evaluation.batch_key == key))
        if existing:
            if existing.retry_of != id:
                raise BusinessError("请求键已使用", 409)
            return jsonify(items=[{"evaluation_id": existing.id, "task_id": evaluation_data(db, existing)["task_id"]}])
        return jsonify(items=create_evaluations(db, get(db, Resume, ev.resume_id), [get(db, Job, ev.job_id)], key, retry_of=id)), 202


@bp.put("/api/evaluations/<int:id>/decision")
def decision_api(id):
    data = body()
    with transaction(current_app, write=True) as db:
        rec = decision(db, get(db, Evaluation, id), data.get("decision"), text(data, "note", limit=5000))
        return jsonify(recruitment=serialize(rec) if rec else None)


def recruitment_data(db, r):
    result = serialize(r)
    result["candidate"] = serialize(get(db, Candidate, r.candidate_id))
    result["job"] = serialize(get(db, Job, r.job_id))
    basis = get(db, Evaluation, r.basis_evaluation_id)
    result["score"], result["resume_id"] = basis.total_score, basis.resume_id
    result["events"] = [serialize(e) for e in db.scalars(select(StageEvent).where(StageEvent.recruitment_id == r.id).order_by(StageEvent.id))]
    return result


@bp.get("/api/recruitments")
def recruitments_api():
    with transaction(current_app) as db:
        stmt = select(Recruitment).join(Candidate).where(Recruitment.active == True).order_by(Recruitment.updated_at.desc())
        for arg, col in [("job_id", Recruitment.job_id), ("stage", Recruitment.stage)]:
            if request.args.get(arg):
                stmt = stmt.where(col == request.args[arg])
        q = request.args.get("q", "").strip()[:200]
        if q:
            stmt = stmt.where(or_(Candidate.name.contains(q), Candidate.phone.contains(q), Candidate.email.contains(q)))
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            raise BusinessError("分页参数不合法")
        count = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        return jsonify(items=[recruitment_data(db, r) for r in db.scalars(stmt.offset((page - 1) * 20).limit(20))], total=count, page=page)


@bp.get("/api/recruitments/<int:id>")
def recruitment_api(id):
    with transaction(current_app) as db:
        return jsonify(recruitment_data(db, get(db, Recruitment, id)))


@bp.post("/api/recruitments/<int:id>/stages")
@bp.post("/api/recruitments/<int:id>/corrections")
def stage_api(id):
    data = body()
    correction = data.get("event_id") if request.path.endswith("corrections") else None
    if request.path.endswith("corrections") and not correction:
        raise BusinessError("请选择需要纠正的历史事件")
    with transaction(current_app, write=True) as db:
        rec = get(db, Recruitment, id)
        change_stage(db, rec, data.get("stage"), data.get("version"), text(data, "note", limit=5000), correction)
        db.flush()
        return jsonify(recruitment_data(db, rec))


@bp.get("/api/dashboard")
def dashboard_api():
    try:
        job_id = int(request.args["job_id"]) if request.args.get("job_id") else None
    except ValueError:
        raise BusinessError("岗位参数不合法")
    with transaction(current_app) as db:
        return jsonify(dashboard(db, job_id, request.args.get("start"), request.args.get("end")))


@bp.get("/api/tasks/<int:id>")
def task_api(id):
    with transaction(current_app) as db:
        task = serialize(get(db, Task, id))
        task.pop("payload")
        return jsonify(task)


@bp.get("/api/tasks/<int:id>/events")
def events_api(id):
    app = current_app._get_current_object()
    with transaction(app) as db:
        get(db, Task, id)
    try:
        cursor = int(request.headers.get("Last-Event-ID", "0"))
    except ValueError:
        raise BusinessError("事件游标不合法")

    def generate():
        nonlocal cursor
        heartbeat = time.monotonic()
        while True:
            with transaction(app) as db:
                task = db.get(Task, id)
                if not task:
                    yield 'event: failed\ndata: {"message":"任务已删除"}\n\n'
                    return
                events = list(db.scalars(select(TaskEvent).where(TaskEvent.task_id == id, TaskEvent.id > cursor).order_by(TaskEvent.id)))
                status = task.status
                fallback = task.result if status == "succeeded" else {"message": task.error}
            for event in events:
                cursor = event.id
                yield f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
            if status in ("succeeded", "failed"):
                if not any(e.type in ("completed", "failed") for e in events):
                    type_ = "completed" if status == "succeeded" else "failed"
                    yield f"event: {type_}\ndata: {json.dumps(fallback, ensure_ascii=False)}\n\n"
                return
            if time.monotonic() - heartbeat >= 15:
                heartbeat = time.monotonic()
                yield ": heartbeat\n\n"
            time.sleep(.7)
    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.route("/api/settings/model", methods=["GET", "PUT"])
def settings_api():
    if request.method == "GET":
        cfg = settings(current_app)
        return jsonify(model=cfg["model"], base_url=cfg["base_url"], key_configured=bool(cfg["api_key"]))
    data = body()
    model, base_url = text(data, "model", True, 200), text(data, "base_url", True, 500)
    url = urlparse(base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise BusinessError("API地址须为不含用户名密码的HTTPS地址")
    key = text(data, "api_key", limit=500)
    with transaction(current_app, write=True) as db:
        values = {"model": model, "base_url": base_url.rstrip("/")}
        if key:
            values["api_key"] = Fernet(current_app.config["SETTINGS_ENCRYPTION_KEY"].encode()).encrypt(key.encode()).decode()
        for k, v in values.items():
            setting = db.get(Setting, k)
            if setting:
                setting.value = v
            else:
                db.add(Setting(key=k, value=v))
    return jsonify(ok=True)


def deletion_scope(db, kind, id):
    if kind == "candidate":
        target = get(db, Candidate, id)
        resumes = list(db.scalars(select(Resume).where(Resume.candidate_id == id)))
        evs = list(db.scalars(select(Evaluation).where(Evaluation.candidate_id == id)))
    elif kind == "resume":
        target = get(db, Resume, id)
        resumes = [target]
        evs = list(db.scalars(select(Evaluation).where(Evaluation.resume_id == id)))
    elif kind == "evaluation":
        target = get(db, Evaluation, id)
        resumes, evs = [], [target]
    else:
        raise BusinessError("删除类型不合法")
    ev_ids = [e.id for e in evs]
    recs = list(db.scalars(select(Recruitment).where(Recruitment.basis_evaluation_id.in_(ev_ids)))) if ev_ids else []
    if kind == "candidate":
        recs = list(db.scalars(select(Recruitment).where(Recruitment.candidate_id == id)))
    task_conditions = []
    if ev_ids:
        task_conditions.append((Task.kind == "evaluate") & Task.target_id.in_(ev_ids))
    if resumes:
        task_conditions.append(Task.kind.in_(["parse", "extract"]) & Task.target_id.in_([r.id for r in resumes]))
    tasks = list(db.scalars(select(Task).where(or_(*task_conditions)))) if task_conditions else []
    return target, resumes, evs, recs, tasks


@bp.get("/api/deletion-preview")
def deletion_preview():
    with transaction(current_app) as db:
        target, resumes, evs, recs, tasks = deletion_scope(db, request.args.get("kind"), request.args.get("id"))
        return jsonify(resumes=len(resumes), evaluations=len(evs), recruitments=len(recs),
                       jobs=list({get(db, Job, e.job_id).name for e in evs}),
                       blocked=any(t.status in ("running", "queued") for t in tasks))


@bp.delete("/api/resumes/<int:id>")
@bp.delete("/api/evaluations/<int:id>")
@bp.delete("/api/candidates/<int:id>")
def delete_api(id):
    data = body()
    if data.get("confirm") is not True:
        raise BusinessError("请确认删除关联数据")
    kind = {"resumes": "resume", "evaluations": "evaluation", "candidates": "candidate"}[request.path.split("/")[2]]
    # Commit business deletion and a durable cleanup job atomically; don't delete files before commit.
    with transaction(current_app, write=True) as db:
        target, resumes, evs, recs, tasks = deletion_scope(db, kind, id)
        if any(t.status in ("queued", "running") for t in tasks):
            raise BusinessError("有关联任务执行中，请等待完成后删除", 409)
        file_paths = [resume.path for resume in resumes]
        task_ids, rec_ids, ev_ids = [t.id for t in tasks], [r.id for r in recs], [e.id for e in evs]
        db.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids)))
        db.execute(delete(Task).where(Task.id.in_(task_ids)))
        db.execute(delete(StageEvent).where(StageEvent.recruitment_id.in_(rec_ids)))
        db.execute(delete(Recruitment).where(Recruitment.id.in_(rec_ids)))
        for ev in db.scalars(select(Evaluation).where(Evaluation.retry_of.in_(ev_ids))):
            ev.retry_of = None
        db.flush()
        db.execute(delete(Evaluation).where(Evaluation.id.in_(ev_ids)))
        if resumes:
            db.execute(delete(Resume).where(Resume.id.in_([r.id for r in resumes])))
        if kind == "candidate":
            db.delete(target)
        if file_paths:
            add_task(db, "cleanup", 0, {"paths": file_paths})
    return jsonify(ok=True)


@bp.post("/api/tasks/<int:id>/retry-cleanup")
def cleanup_retry(id):
    with transaction(current_app, write=True) as db:
        task = get(db, Task, id)
        if task.kind != "cleanup" or task.status != "failed":
            raise BusinessError("只有失败的文件清理任务可重试")
        task.status, task.error = "queued", ""
        return jsonify(ok=True)


@bp.get("/api/maintenance")
def maintenance():
    with transaction(current_app) as db:
        rows = list(db.scalars(select(Task).where(Task.kind == "cleanup", Task.status.in_(["failed", "queued", "running"])) .order_by(Task.id.desc())))
        return jsonify(items=[{"id": t.id, "status": t.status, "error": t.error} for t in rows])
