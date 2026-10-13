"""Offline, credential-free restoration of a reviewed business backup.

Run after closing the workbench: ``python -m trade_agent.restore backup.zip
--data-dir DIRECTORY``. Existing business data requires ``--replace`` and is
snapshotted before replacement. No network requests or credentials are used.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


BUSINESS_DIRS = ("uploads", "documents", "imports", "mail_attachments", "mail_inbound")
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 50_000


def _process_alive(pid: int) -> bool:
    if pid < 1:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) is not a safe process probe on Windows.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER (87) establishes that this positive PID
            # does not exist. Access denied and all other query failures cannot
            # establish exit, so preserve the offline-restore boundary.
            return ctypes.get_last_error() != 87
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _require_stopped(target: Path):
    marker = target / ".app.pid"
    if marker.exists():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            pid = int(value["pid"] if isinstance(value, dict) else value)
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("运行标记无法核实；请关闭程序并检查 .app.pid 后重试") from None
        if _process_alive(pid):
            raise ValueError("程序仍在运行；请先关闭工作台，再离线恢复")


def _members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_FILES or sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
        raise ValueError("备份内容超过安全恢复上限")
    members, seen = {}, set()
    for info in infos:
        name = info.filename.rstrip("/")
        parts = name.split("/")
        mode = info.external_attr >> 16
        if not name or "\\" in name or ":" in name or name.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("备份包含不安全的文件路径")
        if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR} or info.flag_bits & 1:
            raise ValueError("备份不允许符号链接、特殊文件或加密条目")
        key = name.casefold()
        if key in seen:
            raise ValueError("备份包含重复文件路径")
        seen.add(key)
        if len(parts) == 1 and name in {"manifest.json", "trade.sqlite3"} and not info.is_dir():
            pass
        elif parts[0] in BUSINESS_DIRS and (len(parts) > 1 or info.is_dir()):
            pass
        else:
            raise ValueError("备份只能包含业务数据库和业务文件；不允许覆盖认证资料")
        members[name] = info
    if not {"manifest.json", "trade.sqlite3"}.issubset(members):
        raise ValueError("缺少 manifest.json 或 trade.sqlite3；请用当前程序重新备份")
    return members


def _manifest(archive: zipfile.ZipFile, members: dict) -> dict:
    if members["manifest.json"].file_size > 64 * 1024:
        raise ValueError("备份清单过大")
    try:
        manifest = json.loads(archive.read(members["manifest.json"]))
    except (ValueError, UnicodeError):
        raise ValueError("备份清单格式不正确") from None
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("不支持的备份清单版本")
    original = manifest.get("original_data_dir")
    if not isinstance(original, str) or len(original) > 4096 or not (original.startswith("/") or (len(original) > 2 and original[1] == ":")):
        raise ValueError("备份清单缺少原始资料目录")
    if any(ord(char) < 32 for char in original):
        raise ValueError("备份清单目录格式不正确")
    return manifest


def _extract(archive: zipfile.ZipFile, members: dict, stage: Path):
    for name, info in members.items():
        if name == "manifest.json":
            continue
        destination = stage.joinpath(*PurePosixPath(name).parts)
        if info.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
    for folder in BUSINESS_DIRS:
        (stage / folder).mkdir(exist_ok=True)


def _rebase_database(stage: Path, target: Path, original: str) -> dict:
    old = original.replace("\\", "/").rstrip("/")
    windows = len(old) > 1 and old[1] == ":"
    rebased, removed_files = 0, 0

    def transform(value: Any):
        nonlocal rebased
        if isinstance(value, dict):
            return {key: transform(item) for key, item in value.items()}
        if isinstance(value, list):
            return [transform(item) for item in value]
        if isinstance(value, str):
            normalized = value.replace("\\", "/")
            left, right = (normalized.casefold(), old.casefold()) if windows else (normalized, old)
            if left.startswith(right + "/"):
                suffix = normalized[len(old) + 1:]
                parts = suffix.split("/")
                if parts[0] in BUSINESS_DIRS and all(part not in {"", ".", ".."} and ":" not in part for part in parts):
                    rebased += 1
                    return str(target.joinpath(*parts))
                # Backups and credential/database references are never attachments.
                return ""
        return value

    try:
        with sqlite3.connect(stage / "trade.sqlite3") as conn:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("备份数据库完整性检查未通过")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"records", "audit"}.issubset(tables):
                raise ValueError("备份数据库缺少业务表")
            records = conn.execute("SELECT kind,id,data FROM records").fetchall()
            for kind, record_id, encoded in records:
                record = transform(json.loads(encoded))
                if not isinstance(record, dict):
                    raise ValueError("备份包含非对象业务记录")
                if kind == "files":
                    path = Path(str(record.get("path", "")))
                    try:
                        relative = path.relative_to(target)
                        present = relative.parts[0] in BUSINESS_DIRS and stage.joinpath(relative).is_file()
                    except (ValueError, IndexError):
                        present = False
                    if not present:
                        conn.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, record_id))
                        removed_files += 1
                        continue
                if kind == "tasks" and record.get("state") in {"queued", "running"}:
                    record.update(state="interrupted", error="从备份恢复；请核对进度后按指令继续，不会自动重跑")
                if kind == "mail_drafts" and record.get("state") == "approved":
                    record.update(state="draft", review_required=True)
                    record.pop("batch_id", None)
                if kind == "mail_batches" and record.get("state") != "completed":
                    record.update(state="restore_review_required", pause_reason="restored_approval_requires_new_review")
                    for item in record.get("items", []):
                        if item.get("state") == "sending":
                            item.update(state="unknown", reason="restored_delivery_requires_reconciliation")
                conn.execute("UPDATE records SET data=? WHERE kind=? AND id=?", (json.dumps(record, ensure_ascii=False, allow_nan=False), kind, record_id))
            conn.commit()
            conn.execute("PRAGMA journal_mode=DELETE")
    except (sqlite3.Error, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("备份数据库无法读取或格式不正确") from exc
    return {"rebased_paths": rebased, "removed_missing_file_records": removed_files}


def _snapshot(target: Path, connection: sqlite3.Connection | None) -> Path:
    directory = target / "backups"
    if directory.is_symlink():
        raise ValueError("备份目录不允许为符号链接")
    directory.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"pre-restore-{stamp}-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"version": 1, "original_data_dir": str(target), "created_at": stamp}))
        if connection is not None:
            archive.writestr("trade.sqlite3", connection.serialize())
        for folder in BUSINESS_DIRS:
            root = target / folder
            if root.is_symlink():
                raise ValueError("业务目录不允许为符号链接")
            if root.exists():
                for file in root.rglob("*"):
                    if file.is_file() and not file.is_symlink():
                        archive.write(file, file.relative_to(target).as_posix())
    return path


def restore_backup(archive_path: Path | str, data_dir: Path | str, *, replace: bool = False) -> dict:
    """Restore only business data; target secrets and API key remain untouched."""
    target = Path(data_dir).expanduser().resolve()
    source = Path(archive_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".trade-restore-", dir=target.parent))
    rollback = stage / "previous"
    connection = None
    lock_created = False
    rollback_safe_to_remove = True
    try:
        with zipfile.ZipFile(source) as archive:
            members = _members(archive)
            manifest = _manifest(archive, members)
            _extract(archive, members, stage)
        metrics = _rebase_database(stage, target, manifest["original_data_dir"])
        target.mkdir(parents=True, exist_ok=True)
        _require_stopped(target)
        try:
            fd = os.open(target / ".restore.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ValueError("已有恢复任务或恢复标记；请核实后重试") from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        lock_created = True
        _require_stopped(target)  # Protect against startup between initial check and lock.
        existing = (target / "trade.sqlite3").exists() or any((target / folder).exists() for folder in BUSINESS_DIRS)
        if existing and not replace:
            raise ValueError("目标已有业务数据；关闭程序后显式添加 --replace 才能替换")
        for name in ("trade.sqlite3", "trade.sqlite3-wal", "trade.sqlite3-shm", *BUSINESS_DIRS):
            if (target / name).is_symlink():
                raise ValueError("目标业务文件或目录不允许为符号链接")
        if (target / "trade.sqlite3").exists():
            connection = sqlite3.connect(target / "trade.sqlite3", timeout=0)
            try:
                connection.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError:
                raise ValueError("数据库仍被使用；请关闭所有程序后离线恢复") from None
        snapshot = _snapshot(target, connection) if existing else None
        if connection is not None:
            connection.rollback()
            connection.close()
            connection = None
        rollback.mkdir()
        moved, installed = [], []
        try:
            for name in ("trade.sqlite3", "trade.sqlite3-wal", "trade.sqlite3-shm", *BUSINESS_DIRS):
                old_path = target / name
                if old_path.exists():
                    os.replace(old_path, rollback / name)
                    moved.append(name)
            for name in ("trade.sqlite3", *BUSINESS_DIRS):
                os.replace(stage / name, target / name)
                installed.append(name)
        except Exception:
            try:
                for name in reversed(installed):
                    path = target / name
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
                for name in reversed(moved):
                    os.replace(rollback / name, target / name)
            except Exception as error:
                rollback_safe_to_remove = False
                raise RuntimeError(f"恢复中断；原数据保留于 {rollback}，请勿删除") from error
            raise
        return {"restored": True, "data_dir": str(target), "pre_restore_snapshot": str(snapshot) if snapshot else None, "credentials_restored": False, "mail_approval_requires_review": True, **metrics}
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()
        if lock_created:
            (target / ".restore.lock").unlink(missing_ok=True)
        if rollback_safe_to_remove:
            shutil.rmtree(stage, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="关闭程序后离线恢复外贸业务备份；不恢复认证资料")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--replace", action="store_true", help="允许替换已有业务数据；替换前自动备份")
    args = parser.parse_args()
    try:
        result = restore_backup(args.backup, args.data_dir, replace=args.replace)
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(1, f"恢复未完成：{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
