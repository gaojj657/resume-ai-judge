"""初始化八个岗位；同名岗位跳过，不覆盖现有数据。"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from app import create_app
from app.db import transaction
from app.job_seeding import seed_jobs_in_session


def seed_jobs(app, dry_run=False):
    # BEGIN IMMEDIATE 将同名检查与新增放在一个事务中，避免并发重复导入。
    with transaction(app, write=not dry_run) as db:
        return seed_jobs_in_session(db, dry_run=dry_run)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="数据目录；默认使用应用的DATA_DIR或instance")
    parser.add_argument("--dry-run", action="store_true", help="仅校验并显示计划，不写入岗位")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    config = {"START_WORKER": False}
    if args.data_dir is not None:
        config["DATA_DIR"] = str(args.data_dir.resolve())
    app = create_app(config)
    try:
        result = seed_jobs(app, args.dry_run)
        print(f"数据库：{Path(app.config['DATA_DIR']).resolve() / 'app.sqlite3'}")
        print(f"{'计划新增' if args.dry_run else '已新增'} {len(result['created'])} 个岗位；跳过 {len(result['skipped'])} 个同名岗位。")
        for name in result["created"]:
            print(f"  + {name}（必须项80分 + 加分项20分）")
        for name in result["skipped"]:
            print(f"  = {name}（保留现有内容）")
    finally:
        app.extensions["engine"].dispose()


if __name__ == "__main__":
    main()
