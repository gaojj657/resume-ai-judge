"""供首次管理员设置和手动脚本共用的岗位初始化。"""
from sqlalchemy import select
from .models import Job
from .services import validate_criteria
from scripts.job_seed_data import build_jobs


def seed_jobs_in_session(db, dry_run=False):
    jobs = build_jobs()
    names = [job["name"] for job in jobs]
    if len(set(names)) != len(names):
        raise ValueError("初始化数据中存在重复岗位名")
    for job in jobs:
        validate_criteria(job["criteria"])
    created, skipped = [], []
    existing = set(db.scalars(select(Job.name).where(Job.name.in_(names))))
    for job in jobs:
        if job["name"] in existing:
            skipped.append(job["name"])
        else:
            created.append(job["name"])
            if not dry_run:
                db.add(Job(**job))
    return {"created": created, "skipped": skipped}
