from sqlalchemy import select
from app.db import transaction
from app.models import Job
from app.models import User
from scripts.job_seed_data import build_jobs
from scripts.seed_jobs import seed_jobs


def test_seed_is_idempotent_and_preserves_edits(app):
    assert len(seed_jobs(app)["created"]) == 8
    with transaction(app, write=True) as db:
        job = db.scalar(select(Job).where(Job.name == "Java开发"))
        job.jd = "用户手动修改的JD"
        job.status = "closed"
        job.version = 3
        db.add(Job(name="用户自建岗位", jd="保留", criteria=[]))
    result = seed_jobs(app)
    assert result["created"] == []
    assert len(result["skipped"]) == 8
    with transaction(app) as db:
        jobs = db.scalars(select(Job)).all()
        assert len(jobs) == 9
        java = next(job for job in jobs if job.name == "Java开发")
        assert (java.jd, java.status, java.version) == ("用户手动修改的JD", "closed", 3)


def test_dry_run_and_scoring(app):
    assert len(seed_jobs(app, dry_run=True)["created"]) == 8
    with transaction(app) as db:
        assert db.scalar(select(Job.id)) is None
    jobs = build_jobs()
    assert len(jobs) == 8
    for job in jobs:
        assert sum(row["max_score"] for row in job["criteria"]) == 100
        assert sum(row["max_score"] for row in job["criteria"] if row["type"] == "must") == 80
        assert "https://" in job["jd"]
        assert "待核实" in job["jd"]
    jobs[0]["criteria"][0]["max_score"] = 0
    assert build_jobs()[0]["criteria"][0]["max_score"] == 25


def test_first_setup_seeds_jobs(app, client):
    with transaction(app) as db:
        assert len(db.scalars(select(Job)).all()) == 8
    # 删除后普通登录或再次打开设置页不重新生成岗位。
    with transaction(app, write=True) as db:
        db.delete(db.scalar(select(Job).where(Job.name == "Java开发")))
    assert client.get("/setup").status_code == 302
    with transaction(app) as db:
        assert len(db.scalars(select(Job)).all()) == 7


def test_setup_seed_failure_rolls_back_admin(app, monkeypatch):
    def fail(db):
        db.add(Job(name="未完成岗位", jd="应回滚", criteria=[]))
        db.flush()
        raise RuntimeError("模拟初始化失败")

    monkeypatch.setattr("app.routes.seed_jobs_in_session", fail)
    client = app.test_client()
    assert client.get("/setup").status_code == 200
    with client.session_transaction() as session:
        token = session["csrf"]
    response = client.post("/setup", data={"username": "tester", "password": "test-password-123", "csrf_token": token})
    assert response.status_code == 500
    with transaction(app) as db:
        assert db.scalar(select(User.id)) is None
        assert db.scalar(select(Job.id)) is None
    with client.session_transaction() as session:
        assert "user_id" not in session
