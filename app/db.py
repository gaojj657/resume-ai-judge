from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from .models import Base


def init_db(app):
    engine = create_engine("sqlite:///" + str(Path(app.config["DATA_DIR"]) / "app.sqlite3"),
                           connect_args={"timeout": 15})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=15000")

    from alembic.config import Config
    from alembic import command
    root = Path(__file__).resolve().parent.parent
    migration = Config(str(root / "alembic.ini"))
    migration.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        migration.attributes["connection"] = connection
        command.upgrade(migration, "head")
    app.extensions["db"] = sessionmaker(engine, expire_on_commit=False)
    app.extensions["engine"] = engine


@contextmanager
def transaction(app, write=False):
    from sqlalchemy import text
    with app.extensions["db"]() as db:
        try:
            if write:
                db.execute(text("BEGIN IMMEDIATE"))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

