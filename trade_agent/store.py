from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_SETTINGS = {
    "demo_mode": True,
    "public_url": "",
    "selected_country": "",
    "mail_policy_reviewed": False,
    "mail_policy_reviewed_at": "",
    "mail_daily_limit": 20,
    "mail_batch_limit": 20,
    "mail_min_interval_seconds": 120,
    "mail_external_usage_estimate": 0,
    "mail_signature": "",
    "company_name": "",
    "mail_language": "English",
    "search_min_interval_seconds": 10,
    "followup_days": 7,
}


class Store:
    """Every write is durable; module locks coordinate read-modify-write operations."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "trade.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
            conn.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL)")

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @staticmethod
    def _kind(kind: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind):
            raise ValueError("不支持的资料类型")
        return kind

    def put(self, kind: str, data: dict, record_id: str | None = None) -> dict:
        self._kind(kind)
        if not isinstance(data, dict):
            raise ValueError("记录必须是对象")
        record_id = str(record_id or data.get("id") or f"{kind[:3]}-{uuid.uuid4().hex[:16]}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", record_id):
            raise ValueError("记录 ID 格式不正确")
        with self.lock, self.connect() as conn:
            old = conn.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
            previous = json.loads(old[0]) if old else {}
            result = dict(data)
            result.update(id=record_id, created_at=previous.get("created_at", now()), updated_at=now())
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
            conn.execute("INSERT INTO records(kind,id,data) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, record_id, encoded))
        return result

    def get(self, kind: str, record_id: str) -> dict:
        self._kind(kind)
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, str(record_id))).fetchone()
        if row is None:
            raise KeyError(f"找不到记录：{kind}/{record_id}")
        return json.loads(row[0])

    def list(self, kind: str, limit: int = 5000) -> list[dict]:
        self._kind(kind)
        with self.connect() as conn:
            rows = conn.execute("SELECT data FROM records WHERE kind=? ORDER BY rowid DESC LIMIT ?", (kind, min(max(int(limit), 1), 50000))).fetchall()
        return [json.loads(row[0]) for row in rows]

    def delete(self, kind: str, record_id: str):
        with self.lock, self.connect() as conn:
            conn.execute("DELETE FROM records WHERE kind=? AND id=?", (self._kind(kind), str(record_id)))

    def settings(self) -> dict:
        try:
            saved = self.get("settings", "main")
        except KeyError:
            saved = {}
        return {**DEFAULT_SETTINGS, **{k: v for k, v in saved.items() if k not in {"id", "created_at", "updated_at"}}}

    def update_settings(self, patch: dict) -> dict:
        with self.lock:
            current = self.settings()
            current.update(patch)
            self.put("settings", current, "main")
            return self.settings()

    def event(self, action: str, details: dict):
        # Callers log identifiers and outcomes, never authentication values.
        forbidden = {"api_key", "access_token", "refresh_token", "client_secret", "code", "password"}
        def clean(value: Any):
            if isinstance(value, dict):
                return {k: ("[redacted]" if k.lower() in forbidden else clean(v)) for k, v in value.items()}
            if isinstance(value, list):
                return [clean(v) for v in value]
            return value
        with self.lock, self.connect() as conn:
            conn.execute("INSERT INTO audit(at,action,details) VALUES(?,?,?)", (now(), action, json.dumps(clean(details), ensure_ascii=False)))

    def backup_database(self, destination: Path):
        with self.lock, self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
