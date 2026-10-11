"""Run after shutting down the application, so DB and uploaded files form one snapshot."""
import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description="停止应用后备份数据库、文件和本地密钥")
parser.add_argument("--data-dir", default="instance")
parser.add_argument("--output", default="backups")
args = parser.parse_args()
source = Path(args.data_dir).resolve()
target = Path(args.output).resolve() / datetime.now().strftime("%Y%m%d-%H%M%S")
if target == source or source in target.parents:
    raise SystemExit("备份输出目录必须位于数据目录之外")
if not (source / "app.sqlite3").exists():
    raise SystemExit("数据目录中没有数据库")
target.mkdir(parents=True, exist_ok=False)
with sqlite3.connect(source / "app.sqlite3") as db, sqlite3.connect(target / "app.sqlite3") as backup:
    db.backup(backup)
if (source / "uploads").exists():
    shutil.copytree(source / "uploads", target / "uploads")
for filename in ("session.key", "settings.key"):
    if (source / filename).exists():
        shutil.copy2(source / filename, target / filename)
print(f"备份完成：{target}。若密钥来自环境变量，请另行安全备份。")

