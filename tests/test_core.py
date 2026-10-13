"""Integration checks for local trust, durable tasks and offline business backups."""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from trade_agent.app import create_app
from trade_agent.config import Config
from trade_agent.restore import restore_backup
from trade_agent.store import Store
from trade_agent.tasks import TaskManager
from trade_agent import restore as restore_module


@pytest.fixture
def workbench(tmp_path):
    key = "test-only-interface-key-with-at-least-32-characters"
    app = create_app(Config(tmp_path / "source-data", key))
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 52100)) as client:
        yield app, client, {"Authorization": f"Bearer {key}"}


def test_health_and_public_schemas_never_expose_local_key(workbench):
    app, client, headers = workbench
    for endpoint in ("/health", "/openapi.json", "/openapi-actions.json"):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert app.state.config.api_key not in response.text
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer wrong-key"}).status_code == 401
    assert client.get("/api/status", headers=headers).status_code == 200


def test_local_bootstrap_requires_actual_loopback_client(workbench):
    app, client, headers = workbench
    response = client.get("/local/bootstrap")
    assert response.status_code == 200
    assert response.json()["api_key"] == app.state.config.api_key
    with TestClient(app, base_url="http://localhost:8765", client=("203.0.113.2", 53100)) as remote:
        denied = remote.get("/local/bootstrap", headers=headers)
        assert denied.status_code == 403
        assert app.state.config.api_key not in denied.text


@pytest.mark.parametrize("unsafe_headers", [
    {"Host": "attacker.example:8765"},
    {"Host": "localhost.attacker.example:8765"},
    {"Origin": "https://attacker.example"},
    {"Origin": "http://127.0.0.1:8888"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_bootstrap_refuses_host_and_origin_confusion(workbench, unsafe_headers):
    app, client, _ = workbench
    response = client.get("/local/bootstrap", headers=unsafe_headers)
    assert response.status_code == 403
    assert app.state.config.api_key not in response.text


def test_actions_schema_protects_calls_and_omits_local_configuration(workbench):
    _, client, _ = workbench
    schema = client.get("/openapi-actions.json").json()
    assert "/local/bootstrap" not in schema["paths"]
    assert "/api/mail/oauth/start" not in schema["paths"]
    assert "/api/backup" not in schema["paths"]
    assert "patch" not in schema["paths"]["/api/settings"]
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                assert operation["security"], path
                assert operation["x-openai-isConsequential"] is (method != "get")


@pytest.mark.parametrize("kind", ["profit_rules", "mail_drafts", "mail_batches", "orders", "order_updates", "settings", "files", "tasks"])
def test_generic_record_write_cannot_bypass_review_or_file_registration(workbench, kind):
    app, client, headers = workbench
    before = app.state.store.list(kind)
    response = client.post(f"/api/entities/{kind}", headers=headers, json={"name": "attempted direct write", "confirmed": True, "state": "approved", "path": "/etc/passwd"})
    assert response.status_code in {403, 404, 422}
    assert app.state.store.list(kind) == before


def test_only_customer_and_product_generic_writes_are_allowed(workbench):
    _, client, headers = workbench
    assert client.post("/api/entities/customers", json={"name": "Unauthorized"}).status_code == 401
    for kind in ("customers", "products"):
        response = client.post(f"/api/entities/{kind}", headers=headers, json={"name": f"Demo {kind}", "demo": True})
        assert response.status_code == 200
        assert client.get(f"/api/entities/{kind}/{response.json()['id']}", headers=headers).json()["name"] == f"Demo {kind}"


@pytest.mark.parametrize("secret_name", ["secrets/api-key.txt", "secrets/gmail-token.json", "trade.sqlite3"])
def test_registered_file_record_cannot_download_credentials_or_database(workbench, secret_name):
    app, client, headers = workbench
    path = app.state.config.data_dir / secret_name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DO-NOT-EXPOSE", encoding="utf-8")
    record = app.state.store.put("files", {"name": path.name, "path": str(path)})
    denied = client.get(f"/api/files/{record['id']}", headers=headers)
    assert denied.status_code == 422
    assert "DO-NOT-EXPOSE" not in denied.text


def test_registered_symlink_cannot_escape_attachment_directory(workbench, tmp_path):
    app, client, headers = workbench
    outside = tmp_path / "not-business.txt"
    outside.write_text("outside-private-content", encoding="utf-8")
    path = app.state.config.data_dir / "uploads" / "escape.txt"
    path.parent.mkdir(exist_ok=True)
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("This platform does not permit unprivileged symbolic links")
    record = app.state.store.put("files", {"name": path.name, "path": str(path)})
    denied = client.get(f"/api/files/{record['id']}", headers=headers)
    assert denied.status_code == 422
    assert outside.read_text() not in denied.text


def test_business_file_download_requires_authentication(workbench):
    app, client, headers = workbench
    path = app.state.config.data_dir / "uploads" / "catalog.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text("demo catalog", encoding="utf-8")
    record = app.state.store.put("files", {"name": path.name, "path": str(path)})
    endpoint = f"/api/files/{record['id']}"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=headers).text == "demo catalog"


def _populate_business_data(app):
    root, store = app.state.config.data_dir, app.state.store
    catalog = root / "uploads" / "catalog.txt"
    catalog.parent.mkdir(exist_ok=True)
    catalog.write_text("demo catalog", encoding="utf-8")
    attachment = root / "mail_attachments" / "draft-one" / "1" / "catalog.txt"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("reviewed catalog version", encoding="utf-8")
    for folder in ("documents", "imports", "mail_inbound"):
        path = root / folder / "example.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"{folder} demo", encoding="utf-8")
    store.put("customers", {"name": "Fictional small tea merchant", "import_source": str(catalog)}, "customer-one")
    store.put("files", {"name": catalog.name, "path": str(catalog)}, "file-one")
    store.put("mail_drafts", {"state": "approved", "batch_id": "batch-one", "attachments": [{"path": str(attachment)}]}, "draft-one")
    store.put("mail_batches", {"state": "sending", "items": [{"draft_id": "draft-one", "state": "sending", "snapshot": {"attachments": [{"path": str(attachment)}]}}]}, "batch-one")
    store.put("tasks", {"state": "running", "kind": "mail_send"}, "task-one")
    (root / "secrets" / "api-key.txt").write_text("local-api-secret", encoding="utf-8")
    (root / "secrets" / "gmail-token.json").write_text('{"refresh_token":"private-oauth-secret"}', encoding="utf-8")
    return catalog


def _make_backup(workbench):
    app, client, headers = workbench
    _populate_business_data(app)
    result = client.post("/api/backup", headers=headers)
    assert result.status_code == 200
    assert result.json()["includes_credentials"] is False
    file_id = result.json()["files"][0]["file_id"]
    return Path(app.state.store.get("files", file_id)["path"])


def test_backup_includes_business_files_and_excludes_all_credentials(workbench):
    path = _make_backup(workbench)
    with zipfile.ZipFile(path) as backup:
        names = set(backup.namelist())
        assert {"manifest.json", "trade.sqlite3", "uploads/catalog.txt", "documents/example.txt", "imports/example.txt", "mail_inbound/example.txt", "mail_attachments/draft-one/1/catalog.txt"}.issubset(names)
        assert not any(name.startswith(("secrets/", "backups/")) for name in names)
        assert not any(secret in backup.read(name) for name in names for secret in (b"local-api-secret", b"private-oauth-secret"))


def test_backup_restore_rebases_files_keeps_target_keys_and_requires_email_rereview(workbench, tmp_path):
    path = _make_backup(workbench)
    target = tmp_path / "restored-data"
    (target / "secrets").mkdir(parents=True)
    local_key = target / "secrets" / "api-key.txt"
    local_key.write_text("keep-this-target-key", encoding="utf-8")
    outcome = restore_backup(path, target)
    assert outcome["credentials_restored"] is False
    assert outcome["rebased_paths"] >= 3
    assert local_key.read_text() == "keep-this-target-key"
    assert not (target / "secrets" / "gmail-token.json").exists()
    restored = Store(target)
    assert restored.get("customers", "customer-one")["import_source"] == str(target / "uploads" / "catalog.txt")
    assert restored.get("files", "file-one")["path"] == str(target / "uploads" / "catalog.txt")
    assert (target / "mail_attachments" / "draft-one" / "1" / "catalog.txt").read_text() == "reviewed catalog version"
    assert restored.get("tasks", "task-one")["state"] == "interrupted"
    assert restored.get("mail_drafts", "draft-one")["state"] == "draft"
    batch = restored.get("mail_batches", "batch-one")
    assert batch["state"] == "restore_review_required"
    assert batch["items"][0]["state"] == "unknown"


def test_restore_refuses_existing_database_and_replace_preserves_snapshot(workbench, tmp_path):
    backup = _make_backup(workbench)
    target = tmp_path / "existing"
    existing = Store(target)
    existing.put("customers", {"name": "Original customer before restore"}, "original")
    with pytest.raises(ValueError, match="--replace"):
        restore_backup(backup, target)
    assert existing.get("customers", "original")["name"] == "Original customer before restore"
    result = restore_backup(backup, target, replace=True)
    snapshot = Path(result["pre_restore_snapshot"])
    assert snapshot.is_file()
    saved_db = tmp_path / "snapshot.sqlite3"
    with zipfile.ZipFile(snapshot) as archive:
        saved_db.write_bytes(archive.read("trade.sqlite3"))
        assert "secrets/api-key.txt" not in archive.namelist()
    with sqlite3.connect(saved_db) as conn:
        original = json.loads(conn.execute("SELECT data FROM records WHERE kind='customers' AND id='original'").fetchone()[0])
    assert original["name"] == "Original customer before restore"
    assert Store(target).get("customers", "customer-one")["name"] == "Fictional small tea merchant"


@pytest.mark.parametrize("unsafe_name", ["../escaped.txt", "/absolute.txt", "uploads/../../secrets/api-key.txt", "uploads\\escape.txt", "secrets/api-key.txt", "C:/escape.txt"])
def test_restore_rejects_archive_paths_before_writing_target(tmp_path, unsafe_name):
    backup = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(backup, "w") as archive:
        archive.writestr("manifest.json", '{"version":1,"original_data_dir":"/previous"}')
        archive.writestr("trade.sqlite3", b"unused invalid database")
        archive.writestr(unsafe_name, "must not extract")
    target = tmp_path / "destination"
    with pytest.raises(ValueError):
        restore_backup(backup, target)
    assert not target.exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_restore_rejects_symlinks_even_when_the_name_is_safe(tmp_path):
    backup = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("uploads/catalog.txt")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(backup, "w") as archive:
        archive.writestr("manifest.json", '{"version":1,"original_data_dir":"/previous"}')
        archive.writestr("trade.sqlite3", b"unused invalid database")
        archive.writestr(info, "../../secrets/api-key.txt")
    with pytest.raises(ValueError, match="符号链接"):
        restore_backup(backup, tmp_path / "target")


def test_restore_refuses_a_running_workbench(workbench, tmp_path):
    backup = _make_backup(workbench)
    target = tmp_path / "running"
    target.mkdir()
    (target / ".app.pid").write_text(str(os.getpid()), encoding="utf-8")
    with pytest.raises(ValueError, match="仍在运行"):
        restore_backup(backup, target)
    assert not (target / "trade.sqlite3").exists()


def test_restore_refuses_database_with_active_writer(workbench, tmp_path):
    backup = _make_backup(workbench)
    target = tmp_path / "locked"
    existing = Store(target)
    with existing.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="仍被使用"):
            restore_backup(backup, target, replace=True)
        connection.rollback()


def test_restore_rebases_a_windows_backup_on_a_different_computer(tmp_path):
    original = r"C:\Users\Trader\TradeData"
    source_store = Store(tmp_path / "windows-fixture")
    source_store.put("files", {"name": "catalog.txt", "path": original + r"\uploads\catalog.txt"}, "catalog-file")
    source_store.put("documents", {"files": [{"path": original + r"\documents\invoice.txt"}]}, "invoice")
    database = tmp_path / "portable.sqlite3"
    source_store.backup_database(database)
    archive_path = tmp_path / "windows-backup.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"version": 1, "original_data_dir": original}))
        archive.write(database, "trade.sqlite3")
        archive.writestr("uploads/catalog.txt", "customer catalog")
        archive.writestr("documents/invoice.txt", "draft invoice")
    target = tmp_path / "new-computer"
    restore_backup(archive_path, target)
    restored = Store(target)
    assert restored.get("files", "catalog-file")["path"] == str(target / "uploads" / "catalog.txt")
    assert restored.get("documents", "invoice")["files"][0]["path"] == str(target / "documents" / "invoice.txt")


def test_restore_will_not_override_another_restore_lock(workbench, tmp_path):
    backup = _make_backup(workbench)
    target = tmp_path / "restore-in-progress"
    target.mkdir()
    lock = target / ".restore.lock"
    lock.write_text("existing restore ownership", encoding="utf-8")
    with pytest.raises(ValueError, match="已有恢复任务"):
        restore_backup(backup, target)
    assert lock.read_text() == "existing restore ownership"
    assert not (target / "trade.sqlite3").exists()


@pytest.mark.parametrize("error,expected_alive", [(87, False), (5, True), (0, True), (6, True), (31, True)])
def test_windows_process_probe_only_accepts_proven_missing_pid(monkeypatch, error, expected_alive):
    import ctypes
    kernel = SimpleNamespace(OpenProcess=Mock(return_value=None), GetExitCodeProcess=Mock(), CloseHandle=Mock())
    monkeypatch.setattr(restore_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", Mock(return_value=error), raising=False)
    assert restore_module._process_alive(12345) is expected_alive
    kernel.GetExitCodeProcess.assert_not_called()
    kernel.CloseHandle.assert_not_called()


@pytest.mark.parametrize("query_succeeds,exit_code,expected_alive", [(False, 0, True), (True, 259, True), (True, 0, False)])
def test_windows_process_probe_preserves_unknown_status_and_closes_handle(monkeypatch, query_succeeds, exit_code, expected_alive):
    import ctypes
    def query(handle, pointer):
        pointer._obj.value = exit_code
        return query_succeeds
    kernel = SimpleNamespace(OpenProcess=Mock(return_value=2468), GetExitCodeProcess=Mock(side_effect=query), CloseHandle=Mock())
    monkeypatch.setattr(restore_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    assert restore_module._process_alive(12345) is expected_alive
    kernel.CloseHandle.assert_called_once_with(2468)


def test_restart_interrupts_pending_tasks_without_reexecuting_them(tmp_path):
    store = Store(tmp_path / "tasks")
    for state in ("queued", "running", "completed", "failed"):
        store.put("tasks", {"state": state, "kind": "mail_send", "result": {"actual_sent": state == "completed"}}, f"task-{state}")
    manager = TaskManager(store)
    try:
        assert store.get("tasks", "task-queued")["state"] == "interrupted"
        assert store.get("tasks", "task-running")["state"] == "interrupted"
        assert store.get("tasks", "task-completed")["state"] == "completed"
        assert store.get("tasks", "task-failed")["state"] == "failed"
        assert len(store.list("tasks")) == 4
        assert store.get("tasks", "task-completed")["result"] == {"actual_sent": True}
    finally:
        manager.close()
