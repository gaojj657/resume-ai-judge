import os
import secrets
from pathlib import Path
import click
from cryptography.fernet import Fernet
from flask import Flask
from werkzeug.security import generate_password_hash
from sqlalchemy import select
from .db import init_db, transaction
from .models import User


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        DATA_DIR=os.environ.get("DATA_DIR", app.instance_path),
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024,
        MAX_PDF_PAGES=int(os.environ.get("MAX_PDF_PAGES", "30")),
        MODEL_TIMEOUT_SECONDS=int(os.environ.get("MODEL_TIMEOUT_SECONDS", "180")),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        START_WORKER=False,
    )
    if config:
        app.config.update(config)
    data = Path(app.config["DATA_DIR"])
    (data / "uploads").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(data / "ocr-cache"))
    os.environ.setdefault("HF_HOME", str(data / "ocr-cache" / "huggingface"))
    os.environ.setdefault("MODELSCOPE_CACHE", str(data / "ocr-cache" / "modelscope"))
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "bos")
    for filename, key, generator in [("session.key", "SECRET_KEY", lambda: secrets.token_hex(32)),
                                      ("settings.key", "SETTINGS_ENCRYPTION_KEY", lambda: Fernet.generate_key().decode())]:
        value = app.config.get(key) or os.environ.get(key)
        if not value:
            path = data / filename
            if not path.exists():
                path.write_text(generator(), encoding="utf-8")
            value = path.read_text(encoding="utf-8").strip()
        app.config[key] = value
    init_db(app)
    from .routes import bp
    app.register_blueprint(bp)

    @app.cli.command("create-admin")
    @click.option("--username", default="admin", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin(username, password):
        if len(password) < 10:
            raise click.ClickException("密码至少10位")
        with transaction(app, write=True) as db:
            if db.scalar(select(User).where(User.username == username)):
                raise click.ClickException("用户名已存在")
            if db.scalar(select(User.id)):
                raise click.ClickException("首版仅支持一个管理员")
            db.add(User(username=username, password_hash=generate_password_hash(password)))
            from .job_seeding import seed_jobs_in_session
            seed_jobs_in_session(db)
        click.echo("管理员已创建")

    if app.config["START_WORKER"]:
        from .tasks import Worker
        app.extensions["worker"] = Worker(app)
        app.extensions["worker"].start()
    return app

