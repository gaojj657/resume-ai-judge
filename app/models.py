from datetime import datetime, timezone
from sqlalchemy import ForeignKey, UniqueConstraint, Index, JSON, String, Text, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    jd: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="open")
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(default="", index=True)
    email: Mapped[str] = mapped_column(default="", index=True)
    education: Mapped[str] = mapped_column(default="")
    major: Mapped[str] = mapped_column(default="")
    created_at: Mapped[str] = mapped_column(default=now)


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"))
    purpose: Mapped[str] = mapped_column(default="resume")
    filename: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="queued")
    markdown: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(default=now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (Index("ix_eval_pair", "candidate_id", "job_id", "status", "completed_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    status: Mapped[str] = mapped_column(default="queued")
    snapshot: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    total_score: Mapped[int | None] = mapped_column()
    decision: Mapped[str] = mapped_column(default="pending")
    note: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(default="")
    response_id: Mapped[str] = mapped_column(default="")
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(default="1")
    schema_version: Mapped[str] = mapped_column(default="1")
    retry_of: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"))
    batch_key: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[str] = mapped_column(default=now)
    completed_at: Mapped[str | None] = mapped_column()


class Recruitment(Base):
    __tablename__ = "recruitments"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    basis_evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"))
    stage: Mapped[str] = mapped_column(default="pending_interview", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
    promoted_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class StageEvent(Base):
    __tablename__ = "stage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    recruitment_id: Mapped[int] = mapped_column(ForeignKey("recruitments.id"), index=True)
    from_stage: Mapped[str] = mapped_column()
    to_stage: Mapped[str] = mapped_column()
    valid: Mapped[bool] = mapped_column(default=True)
    kind: Mapped[str] = mapped_column(default="transition")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(default=now)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column()
    target_id: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    type: Mapped[str] = mapped_column()
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text)

