from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
from sqlalchemy import select
from .models import Job, Candidate, Resume, Evaluation, Recruitment, StageEvent, now
from .tasks import add_task

STAGES = {"pending_interview": "待安排面试", "group_interview": "群面", "technical_1": "技术一面",
          "technical_2": "技术二面", "hr": "HR面", "intent": "录用意向", "offer_signed": "Offer签约",
          "onboarded": "已入职", "rejected": "已淘汰", "withdrawn": "候选人退出"}


class BusinessError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def get(db, model, id):
    try:
        item = db.get(model, int(id))
    except (ValueError, TypeError):
        item = None
    if item is None:
        raise BusinessError("记录不存在", 404)
    return item


def validate_criteria(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise BusinessError("请配置1—50条评分项")
    keys = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("type") not in ("must", "bonus"):
            raise BusinessError("评分项类型不合法")
        if not isinstance(row.get("key"), str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", row["key"]) or row["key"] in keys:
            raise BusinessError("评分项标识必须是唯一英文标识")
        keys.add(row["key"])
        if type(row.get("max_score")) is not int or not 0 <= row["max_score"] <= 100:
            raise BusinessError("单项满分必须是0—100的整数")
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("name", "requirement", "scoring_rule")):
            raise BusinessError("请填写每条评分项的名称、要求和评分说明")
    if sum(row["max_score"] for row in rows) != 100:
        raise BusinessError("必须项与加分项满分合计必须为100分")
    return rows


def create_evaluations(db, resume, jobs, batch_key, retry_of=None):
    if resume.status != "succeeded" or not resume.candidate_id:
        raise BusinessError("请先完成简历解析并确认候选人资料")
    candidate = get(db, Candidate, resume.candidate_id)
    profile = {k: getattr(candidate, k) for k in ("id", "name", "education", "major")}
    result = []
    for job in jobs:
        if job.status != "open":
            raise BusinessError("已关闭岗位不能发起新评估")
        validate_criteria(job.criteria)
        markdown = resume.markdown
        # Personal contact details aren't needed for scoring.
        for contact in (candidate.phone, candidate.email):
            if contact:
                markdown = markdown.replace(contact, "[联系方式已隐藏]")
        snapshot = {"job_name": job.name, "jd": job.jd, "criteria": job.criteria,
                    "criteria_version": job.version, "markdown": markdown,
                    "resume_revision": resume.revision, "candidate": profile}
        evaluation = Evaluation(candidate_id=candidate.id, resume_id=resume.id, job_id=job.id,
                                snapshot=snapshot, batch_key=batch_key, retry_of=retry_of)
        db.add(evaluation)
        db.flush()
        task = add_task(db, "evaluate", evaluation.id)
        result.append({"evaluation_id": evaluation.id, "task_id": task.id, "job_name": job.name})
    return result


def decision(db, evaluation, value, note):
    if evaluation.status != "succeeded":
        raise BusinessError("只有完整且校验成功的报告才能决定推进")
    if value not in ("advance", "reject"):
        raise BusinessError("推进决定不合法")
    rec = db.scalar(select(Recruitment).where(Recruitment.candidate_id == evaluation.candidate_id,
                                             Recruitment.job_id == evaluation.job_id))
    evaluation.decision, evaluation.note = value, note
    if value == "advance":
        if rec is None:
            rec = Recruitment(candidate_id=evaluation.candidate_id, job_id=evaluation.job_id,
                              basis_evaluation_id=evaluation.id, stage="pending_interview", active=True)
            db.add(rec)
            db.flush()
            db.add(StageEvent(recruitment_id=rec.id, from_stage="", to_stage="pending_interview"))
        elif not rec.active:
            rec.active, rec.version, rec.updated_at = True, rec.version + 1, now()
    elif rec and rec.active:
        rec.active, rec.version, rec.updated_at = False, rec.version + 1, now()
    return rec


def change_stage(db, rec, stage, version, note="", correct_event_id=None):
    if stage not in STAGES:
        raise BusinessError("招聘阶段不合法")
    if not rec.active:
        raise BusinessError("请先恢复推进后再更新阶段")
    if version != rec.version:
        raise BusinessError("记录已被更新，请刷新后重试", 409)
    if correct_event_id:
        event = get(db, StageEvent, correct_event_id)
        if event.recruitment_id != rec.id or not event.valid:
            raise BusinessError("纠正事件不合法")
        # Correcting an earlier event invalidates its dependent suffix explicitly.
        for e in db.scalars(select(StageEvent).where(StageEvent.recruitment_id == rec.id,
                                                      StageEvent.id >= event.id, StageEvent.valid == True)):
            e.valid = False
    elif rec.stage == stage:
        return
    db.add(StageEvent(recruitment_id=rec.id, from_stage=rec.stage, to_stage=stage,
                      kind="correction" if correct_event_id else "transition", note=note))
    rec.stage, rec.version, rec.updated_at = stage, rec.version + 1, now()


def date_boundary(value, end=False):
    if not value:
        return None
    try:
        date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
    except ValueError as exc:
        raise BusinessError("日期格式应为YYYY-MM-DD") from exc
    if end:
        date += timedelta(days=1)
    return date.astimezone(timezone.utc).isoformat(timespec="microseconds")


def dashboard(db, job_id=None, start=None, end=None):
    lower, upper = date_boundary(start), date_boundary(end, True)
    if lower and upper and lower >= upper:
        raise BusinessError("开始日期不能晚于结束日期")
    jobs = {j.id: j for j in db.scalars(select(Job))}
    evaluations = list(db.scalars(select(Evaluation).where(Evaluation.status == "succeeded").order_by(Evaluation.completed_at, Evaluation.id)))
    pairs = defaultdict(list)
    for ev in evaluations:
        if job_id is None or ev.job_id == job_id:
            pairs[(ev.candidate_id, ev.job_id)].append(ev)
    pairs = {pair: rows for pair, rows in pairs.items()
             if (not lower or rows[0].completed_at >= lower) and (not upper or rows[0].completed_at < upper)}
    recs = { (r.candidate_id, r.job_id): r for r in db.scalars(select(Recruitment).where(Recruitment.active == True))
             if (r.candidate_id, r.job_id) in pairs }
    events = defaultdict(set)
    for event in db.scalars(select(StageEvent).where(StageEvent.valid == True)):
        events[event.recruitment_id].add(event.to_stage)
    advanced = {pair[0] for pair in recs}
    onboarded = {pair[0] for pair, rec in recs.items() if "onboarded" in events[rec.id]}
    funnel = [{"label": "已评估", "count": len(pairs)}, {"label": "已推进", "count": len(recs)}]
    for stage in list(STAGES)[1:8]:
        funnel.append({"label": STAGES[stage], "count": sum(stage in events[r.id] for r in recs.values())})
    for i, item in enumerate(funnel):
        denominator = funnel[i - 1]["count"] if i else None
        item["ratio"] = round(item["count"] / denominator * 100, 1) if denominator else None
    distribution = [{"label": label, "count": sum(r.stage == key for r in recs.values())} for key, label in STAGES.items()]
    overview = []
    for id, job in jobs.items():
        if job_id is not None and id != job_id:
            continue
        selected = {pair: rows for pair, rows in pairs.items() if pair[1] == id}
        selected_recs = [r for pair, r in recs.items() if pair[1] == id]
        overview.append({"id": id, "name": job.name, "status": job.status, "evaluated": len(selected),
                         "advanced": len(selected_recs), "onboarded": sum("onboarded" in events[r.id] for r in selected_recs),
                         "average_score": round(sum(rows[-1].total_score for rows in selected.values()) / len(selected), 1) if selected else None})
    return {"stats": {"open_jobs": sum(j.status == "open" for j in jobs.values() if job_id is None or j.id == job_id),
                       "evaluated": len({pair[0] for pair in pairs}), "advanced": len(advanced), "onboarded": len(onboarded)},
            "funnel": funnel, "distribution": distribution, "jobs": overview,
            "cohort_count": len(pairs)}
