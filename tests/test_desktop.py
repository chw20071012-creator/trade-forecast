import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trade_agent.app import create_app
from trade_agent.config import Config
from trade_agent.desktop_migrate import migrate
from trade_agent.desktop_server import attach_desktop
from trade_agent.store import Store


def test_migration_keeps_source_rebases_attachments_and_preserves_local_accounts(tmp_path):
    old = tmp_path / "旧版 有空格" / ".runtime" / "data"
    store = Store(old)
    attachment = old / "uploads" / "客户附件.txt"
    attachment.parent.mkdir()
    attachment.write_text("sample attachment", encoding="utf-8")
    store.put("files", {"path": str(attachment)}, "file-one")
    store.put("customers", {"name": "test customer", "catalog": str(attachment)}, "one")
    store.put("mail_drafts", {"state": "approved"}, "draft-one")
    secrets_dir = old / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "gmail-token.json").write_text('{"test_fixture":true}')
    (secrets_dir / "gmail-oauth-flow.json").write_text('{"test_fixture":true}')
    (old / ".app.pid").write_text('{"pid":99999999}')
    target = tmp_path / "新版 数据" / "data"
    result = migrate(old.parent.parent, target)
    assert result["migrated"]
    assert store.get("files", "file-one")["path"] == str(attachment)
    assert not (old / ".restore.lock").exists()
    restored = Store(target)
    assert restored.get("customers", "one")["catalog"] == str(target / "uploads" / attachment.name)
    assert (target / "uploads" / attachment.name).read_text() == "sample attachment"
    assert restored.get("mail_drafts", "draft-one")["state"] == "draft"
    assert (target / "secrets" / "gmail-token.json").is_file()
    assert not (target / "secrets" / "gmail-oauth-flow.json").exists()
    assert not (target / ".app.pid").exists()


def test_migration_refuses_live_source_and_preserves_existing_target(tmp_path):
    old = tmp_path / "old"
    Store(old)
    target = tmp_path / "new"
    (old / ".app.pid").write_text(json.dumps({"pid": os.getpid()}))
    with pytest.raises(ValueError, match="运行"):
        migrate(old, target)
    assert not target.exists()
    (old / ".app.pid").unlink()
    target.mkdir()
    (target / "precious.txt").write_text("keep")
    with pytest.raises(ValueError, match="已有资料"):
        migrate(old, target)
    assert (target / "precious.txt").read_text() == "keep"


def test_migration_failure_does_not_leave_partial_database(tmp_path):
    old = tmp_path / "old"
    Store(old)
    (old / "uploads").mkdir()
    (old / "uploads" / "link").symlink_to(tmp_path / "outside")
    target = tmp_path / "new"
    with pytest.raises(ValueError, match="符号链接"):
        migrate(old, target)
    assert not (target / "trade.sqlite3").exists()
    assert not (old / ".restore.lock").exists()


def test_migration_closes_sqlite_handles_before_windows_file_moves(tmp_path, monkeypatch):
    old = tmp_path / "old"
    Store(old).put("customers", {"name": "test"}, "one")
    opened = []
    real_connect = sqlite3.connect
    real_replace = os.replace
    real_rename = Path.rename
    class TrackedConnection(sqlite3.Connection):
        closed = False
        def close(self):
            self.closed = True
            super().close()
    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackedConnection
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn
    def checked_replace(*args, **kwargs):
        assert all(conn.closed for conn in opened), "Windows forbids moving open databases"
        return real_replace(*args, **kwargs)
    def checked_rename(self, *args, **kwargs):
        assert all(conn.closed for conn in opened), "Windows forbids moving open directories"
        return real_rename(self, *args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    monkeypatch.setattr(os, "replace", checked_replace)
    monkeypatch.setattr(Path, "rename", checked_rename)
    assert migrate(old, tmp_path / "new")["migrated"]
    assert opened and all(conn.closed for conn in opened)


@pytest.fixture
def desktop(tmp_path):
    app = create_app(Config(tmp_path / "data", "a" * 48))
    secret = "b" * 64
    calls = []
    attach_desktop(app, secret, lambda: calls.append("stop"))
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 53110)) as client:
        yield app, client, secret, calls


def test_shutdown_is_private_and_health_contains_only_hashed_identity(desktop):
    app, client, secret, calls = desktop
    health = client.get("/health")
    assert secret not in health.text
    assert health.json()["desktop_instance"] == hashlib.sha256(secret.encode()).hexdigest()
    for endpoint in ("/openapi.json", "/openapi-actions.json"):
        assert "/local/desktop/shutdown" not in client.get(endpoint).json()["paths"]
    assert client.post("/local/desktop/shutdown").status_code == 403
    for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
        assert client.post("/local/desktop/shutdown", headers={"X-Desktop-Session": secret, **headers}).status_code == 403
    assert calls == []
    assert client.post("/local/desktop/shutdown", headers={"X-Desktop-Session": secret}).status_code == 200
    assert calls == ["stop"]
    with pytest.raises(ValueError, match="退出"):
        app.state.tasks.submit("noop", lambda: None)


def test_shutdown_waits_for_work_without_interrupting_it(desktop):
    app, client, secret, calls = desktop
    release, started, finished = threading.Event(), threading.Event(), threading.Event()
    def work():
        started.set()
        release.wait(3)
        finished.set()
    app.state.tasks.submit("test", work)
    assert started.wait(1)
    try:
        response = client.post("/local/desktop/shutdown", headers={"X-Desktop-Session": secret})
        assert response.status_code == 409
        assert calls == []
        assert not app.state.desktop_closing
    finally:
        release.set()
        assert finished.wait(2)
