"""Offline first-run migration, preserving the original installation."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

from .restore import BUSINESS_DIRS, _rebase_database, _require_stopped, restore_backup

ACCOUNT_FILES = ("api-key.txt", "gmail-client.json", "gmail-token.json")


def locate_source(selected: Path | str) -> Path:
    root = Path(selected).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("请选择旧版工作台文件夹")
    candidates = [root, root / "data", root / ".runtime" / "data"]
    # Windows 'Extract all' commonly adds one wrapper directory.
    candidates.extend(child / ".runtime" / "data" for child in root.iterdir() if child.is_dir() and not child.is_symlink())
    matches = list(dict.fromkeys(p.resolve() for p in candidates if (p / "trade.sqlite3").is_file()))
    if len(matches) != 1:
        raise ValueError("未找到唯一的旧版资料库，请选择包含 start.cmd 和 .runtime 的工作台文件夹")
    return matches[0]


def migrate(source: Path | str, target: Path | str) -> dict:
    original = locate_source(source)
    destination = Path(target).expanduser().resolve()
    if original == destination or destination.is_relative_to(original) or original.is_relative_to(destination):
        raise ValueError("新旧资料目录不能相同或相互包含")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("桌面版已有资料，不会覆盖。请保留现有资料并使用备份恢复功能处理。")
    _require_stopped(original)
    if (original / "trade.sqlite3").is_symlink():
        raise ValueError("原数据库不能是符号链接")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_lock = original / ".restore.lock"
    # The legacy server refuses to start while this temporary marker exists.
    try:
        lock_fd = os.open(source_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("旧目录正在恢复或迁移，请结束该操作后重试") from None
    with os.fdopen(lock_fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        _require_stopped(original)
        with tempfile.TemporaryDirectory(prefix=".desktop-migrate-", dir=destination.parent) as workspace:
            work = Path(workspace)
            snapshot = work / "trade.sqlite3"
            started = time.monotonic()

            def progress(status, remaining, total):
                if time.monotonic() - started > 30:
                    raise ValueError("读取旧资料库超时；请确认旧版已完全退出后重试")

            with closing(sqlite3.connect((original / "trade.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=5)) as source_db:
                with closing(sqlite3.connect(snapshot)) as copy_db:
                    source_db.backup(copy_db, pages=256, progress=progress)
            archive_path = work / "business.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps({"version": 1, "original_data_dir": str(original)}))
                archive.write(snapshot, "trade.sqlite3")
                for folder in BUSINESS_DIRS:
                    directory = original / folder
                    if directory.is_symlink():
                        raise ValueError("业务目录包含符号链接，请先整理实际文件后迁移")
                    if directory.exists():
                        for item in directory.rglob("*"):
                            if item.is_symlink():
                                raise ValueError("业务附件包含符号链接，请先整理实际文件后迁移")
                            if item.is_file():
                                archive.write(item, item.relative_to(original).as_posix())
            staged = work / "data"
            result = restore_backup(archive_path, staged)
            _rebase_database(staged, destination, str(staged))
            copied = []
            secrets_dir = original / "secrets"
            if secrets_dir.is_symlink():
                raise ValueError("旧账号配置目录为符号链接，请先整理后迁移")
            for name in ACCOUNT_FILES:
                old = secrets_dir / name
                if old.is_symlink():
                    raise ValueError("旧账号配置文件为符号链接，请先整理后迁移")
                if old.is_file():
                    if old.stat().st_size > 2 * 1024 * 1024:
                        raise ValueError("旧账号配置文件异常大，请核查后重试")
                    (staged / "secrets").mkdir(mode=0o700, exist_ok=True)
                    shutil.copyfile(old, staged / "secrets" / name)
                    (staged / "secrets" / name).chmod(0o600)
                    copied.append(name)
            # Recheck before the single commit; the source is never deleted.
            _require_stopped(original)
            if destination.exists():
                destination.rmdir()  # Fails instead of overwriting any new files.
            staged.rename(destination)
            return {
                "migrated": True, "source_preserved": True,
                "rebased_paths": result["rebased_paths"],
                "account_files_copied": copied,
                "mail_approval_requires_review": True,
                "message": "旧资料已复制到桌面版，原文件保留。请核对数据和邮箱状态；未完成发送需重新复核。",
            }
    finally:
        source_lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="首次使用时导入已停止的旧版工作台；不会覆盖已有资料")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = migrate(args.source, args.target)
        code = 0
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        # No account file contents or database records are included in reports.
        result = {"migrated": False, "message": str(exc)}
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["message"])
    raise SystemExit(code)


if __name__ == "__main__":
    main()
