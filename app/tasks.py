import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pydantic_core import from_json
from sqlalchemy import select, update
from .db import transaction
from .models import Task, TaskEvent, Resume, Evaluation, now
from .ai import structured_call, validate_report, Report, Profile, JobDraft, SYSTEM, safe_error
from .parsers import parse_file


def add_task(db, kind, target_id, payload=None):
    task = Task(kind=kind, target_id=target_id, payload=payload or {})
    db.add(task)
    db.flush()
    return task


def emit(app, task_id, type_, payload):
    with transaction(app, write=True) as db:
        if db.get(Task, task_id):
            db.add(TaskEvent(task_id=task_id, type=type_, payload=payload))
            db.get(Task, task_id).updated_at = now()


class Worker:
    def __init__(self, app):
        self.app = app
        self.stop_event = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="resume-task")
        self.ocr_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="resume-parse")
        self.futures = {}

    def start(self):
        self.lock_file = (Path(self.app.config["DATA_DIR"]) / "worker.lock").open("a+b")
        if self.lock_file.tell() == 0:
            self.lock_file.write(b"0")
            self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            raise RuntimeError("该数据目录已有任务进程运行，请勿重复启动") from None
        with transaction(self.app, write=True) as db:
            for task in db.scalars(select(Task).where(Task.status == "running")):
                if task.kind == "cleanup":
                    task.status = "queued"
                    continue
                task.status, task.error = "failed", "服务重启中断任务，请手动重试"
                if task.kind == "evaluate":
                    item = db.get(Evaluation, task.target_id)
                elif task.kind == "parse":
                    item = db.get(Resume, task.target_id)
                else:
                    item = None
                if item:
                    item.status, item.error = "failed", task.error
                db.add(TaskEvent(task_id=task.id, type="failed", payload={"message": task.error}))
        self.thread = threading.Thread(target=self.loop, daemon=True, name="task-dispatch")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        self.pool.shutdown(wait=True)
        self.ocr_pool.shutdown(wait=True)
        self.lock_file.close()

    def loop(self):
        while not self.stop_event.wait(.5):
            try:
                self.futures = {k: v for k, v in self.futures.items() if not v[0].done()}
                with transaction(self.app, write=True) as db:
                    for task in db.scalars(select(Task).where(Task.status == "queued").order_by(Task.id)):
                        kind = "parse" if task.kind == "parse" else "model"
                        limit = 1 if kind == "parse" else 2
                        if sum(v[1] == kind for v in self.futures.values()) >= limit:
                            continue
                        task.status, task.updated_at = "running", now()
                        executor = self.ocr_pool if kind == "parse" else self.pool
                        self.futures[task.id] = (executor.submit(execute_task, self.app, task.id), kind)
            except Exception:
                self.app.logger.error("任务调度失败；将在下一轮重试")


def execute_task(app, task_id):
    try:
        with transaction(app, write=True) as db:
            task = db.get(Task, task_id)
            if not task:
                return
            kind, target, payload = task.kind, task.target_id, task.payload
            task.status = "running"
            if kind == "evaluate":
                item = db.get(Evaluation, target)
                item.status = "running"
                snapshot = item.snapshot
            elif kind in ("parse", "extract"):
                resume = db.get(Resume, target)
                path, markdown = resume.path, resume.markdown
                if kind == "parse":
                    resume.status = "running"
        emit(app, task_id, "status", {"message": {"cleanup": "正在清理已删除文件", "parse": "正在解析文档", "extract": "正在提取候选人信息",
                                                     "draft": "正在生成评分标准草稿", "evaluate": "正在生成匹配报告"}[kind]})
        if kind == "cleanup":
            root = (Path(app.config["DATA_DIR"]) / "uploads").resolve()
            for relative_path in payload["paths"]:
                path = (root / relative_path).resolve()
                if path.parent != root:
                    raise ValueError("文件清理路径不合法")
                path.unlink(missing_ok=True)
            result = {"cleaned": len(payload["paths"])}
        elif kind == "parse":
            text = parse_file(str(Path(app.config["DATA_DIR"]) / "uploads" / path), app.config["MAX_PDF_PAGES"])
            with transaction(app, write=True) as db:
                resume = db.get(Resume, target)
                if resume:
                    resume.markdown, resume.status, resume.error = text, "succeeded", ""
            result = {"resume_id": target}
        elif kind == "extract":
            result, _ = structured_call(app, Profile, SYSTEM + "提取候选人资料；缺失字符串用空字符串，不猜测姓名。", {"markdown": payload["markdown"]})
            with transaction(app, write=True) as db:
                resume = db.get(Resume, target)
                if resume and resume.revision == payload["revision"]:
                    resume.extracted = result
        elif kind == "draft":
            result, _ = structured_call(app, JobDraft, SYSTEM + "从JD生成可人工编辑的岗位评分标准，必须项和加分项满分合计100，key使用唯一英文标识。", payload)
            from .services import validate_criteria
            validate_criteria(result["criteria"])
        else:
            buffer, last, sent = "", 0., None

            def on_delta(delta):
                nonlocal buffer, last, sent
                buffer += delta
                if time.monotonic() - last < .7:
                    return
                last = time.monotonic()
                try:
                    partial = from_json(buffer, allow_partial=True)
                    if isinstance(partial, dict) and partial != sent:
                        emit(app, task_id, "report_patch", {"report": partial})
                        sent = partial
                except ValueError:
                    pass

            instructions = SYSTEM + """逐项按scoring_rule评分，必须项partial表示尚未达到硬性要求。
每个criterion_key恰好返回一次。score为0到对应满分的整数。
met必须有简历原文依据，evidence.quote逐字引用简历文本，location使用页码或段落标识。
unknown表示简历没写，必须单独待核实。缺失信息按评分说明保守给分。
strengths/gaps/interview_questions使用简短中文。"""
            raw, meta = structured_call(app, Report, instructions, snapshot, on_delta)
            emit(app, task_id, "status", {"message": "正在校验评分及简历依据"})
            try:
                result = validate_report(raw, snapshot)
            except ValueError as error:
                emit(app, task_id, "status", {"message": "正在修复报告格式或引用"})
                raw, meta = structured_call(app, Report, instructions,
                                            {"input": snapshot, "previous": raw, "validation_error": str(error)})
                result = validate_report(raw, snapshot)
            with transaction(app, write=True) as db:
                item = db.get(Evaluation, target)
                if not item:
                    return
                item.report, item.total_score = result, result["total_score"]
                item.status, item.completed_at, item.error = "succeeded", now(), ""
                item.model, item.response_id, item.usage = meta["model"], meta["response_id"], meta["usage"]
            result = {"evaluation_id": target}
        with transaction(app, write=True) as db:
            task = db.get(Task, task_id)
            if task:
                task.status, task.result, task.updated_at = "succeeded", result, now()
                db.add(TaskEvent(task_id=task_id, type="completed", payload=result))
    except Exception as exc:
        message = safe_error(exc)
        with transaction(app, write=True) as db:
            task = db.get(Task, task_id)
            if task:
                task.status, task.error, task.updated_at = "failed", message, now()
                if task.kind == "evaluate":
                    item = db.get(Evaluation, task.target_id)
                elif task.kind == "parse":
                    item = db.get(Resume, task.target_id)
                else:
                    item = None
                if item:
                    item.status, item.error = "failed", message
                db.add(TaskEvent(task_id=task_id, type="failed", payload={"message": message}))
