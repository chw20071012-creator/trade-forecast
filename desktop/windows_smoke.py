#!/usr/bin/env python3
"""Windows-only integration smoke test, confined to a temporary test workspace.

Requires only the standard library in the driver interpreter. Executes the bundled
Windows runtime and GUI launcher; never sends mail or imports real user data.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8765"
WINDOW_CLASS = "TradeAgentDesktopControllerV1"
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OWNED: list[subprocess.Popen] = []
RESULTS: list[dict] = []
SECRET_VALUES: list[str] = []


def failure_annotation(error, output, workspace):
    """Expose bounded diagnostics through the permitted GitHub checks API."""
    sections = [error]
    paths = sorted(output.glob("*.log"))
    launcher_logs = workspace / "隔离 用户资料" / "TradeAgent" / "logs"
    paths.extend(sorted(launcher_logs.glob("*.log")))
    for path in paths:
        try:
            # Read a bounded suffix even if a child unexpectedly writes a large log.
            with path.open("rb") as source:
                source.seek(max(0, path.stat().st_size - 32768))
                tail = "\n".join(source.read().decode("utf-8", errors="replace").splitlines()[-30:])
            sections.append(f"\n--- {path.name}: last 30 lines ---\n{tail}")
        except OSError as exc:
            sections.append(f"\n--- {path.name}: unreadable ({type(exc).__name__}) ---")
    diagnostic = "\n".join(sections)
    for value in SECRET_VALUES:
        diagnostic = diagnostic.replace(value, "[redacted]")
    diagnostic = re.sub(r"(?i)(\b(?:TRADE_DESKTOP_SESSION|X-Desktop-Session|api[_-]?key|access_token|refresh_token|client_secret)\b[\s\"']*[:=][\s\"']*)[^\s\"',;}]+", r"\1[redacted]", diagnostic)
    # Both launcher and driver session secrets are hexadecimal. Redact unknown
    # long hexadecimal values too, including harmless hashes, for diagnostics.
    diagnostic = re.sub(r"(?<![0-9A-Za-z])[0-9a-fA-F]{32,}(?![0-9A-Za-z])", "[redacted]", diagnostic)
    escaped = diagnostic.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if len(escaped) > 11800:
        escaped = escaped[:11750] + "%0A[diagnostic truncated]"
    print("::error title=Desktop smoke failure::" + escaped, flush=True)


def wait_for(function, *, timeout=45, description="condition"):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        result = function()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {description}")


def request(path, *, method="GET", token=None):
    headers = {"X-Desktop-Session": token} if token else {}
    req = urllib.request.Request(BASE_URL + path, method=method, headers=headers)
    with HTTP.open(req, timeout=2) as response:
        return response.status, response.read()


def health(expected_hash=None):
    try:
        status, body = request("/health")
        result = json.loads(body)
        if status == 200 and result.get("application") == "trade_agent" and result.get("status") == "ok":
            if expected_hash is None or result.get("desktop_instance") == expected_hash:
                return result
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return None


def is_port_free():
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 8765))
        except OSError:
            return False
    return True


def listener_absent():
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.5):
            return False
    except OSError:
        return True


def note(name, detail=""):
    RESULTS.append({"test": name, "passed": True, "detail": detail})
    print(f"PASS: {name} {detail}", flush=True)


class Windows:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]
        self.user.EnumWindows.restype = wintypes.BOOL
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.SendMessageW.restype = wintypes.LPARAM
        self.user.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetDlgItem.restype = wintypes.HWND

    def windows(self, pid, class_name=None):
        matches = []

        @self.callback_type
        def callback(hwnd, _):
            found_pid = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))
            if found_pid.value == pid:
                name = ctypes.create_unicode_buffer(256)
                self.user.GetClassNameW(hwnd, name, len(name))
                if class_name is None or name.value == class_name:
                    matches.append(int(hwnd))
            return True

        self.user.EnumWindows(callback, 0)
        return matches

    def click_dialog(self, pid, button, timeout=10):
        dialog = wait_for(lambda: self.windows(pid, "#32770"), timeout=timeout, description="launcher message dialog")[0]
        handle = self.user.GetDlgItem(dialog, button)
        if not handle:
            raise AssertionError(f"Dialog does not contain expected button {button}")
        self.user.SendMessageW(handle, 0x00F5, 0, 0)  # BM_CLICK, this test's process only.

    def close(self, pid, *, confirm):
        window = wait_for(lambda: self.windows(pid, WINDOW_CLASS), description="controller window")[0]
        self.user.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE
        if confirm:
            self.click_dialog(pid, 6)  # IDYES


def clean_env(local_appdata, data, token):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("TRADE_", "PYTHON"))
           and key.upper() not in {"VIRTUAL_ENV", "PLAYWRIGHT_BROWSERS_PATH"}}
    env.update(LOCALAPPDATA=str(local_appdata), TRADE_DATA_DIR=str(data),
               TRADE_API_KEY_FILE=str(data / "secrets" / "api-key.txt"),
               TRADE_DESKTOP_SESSION=token, TRADE_HOST="127.0.0.1", TRADE_PORT="8765",
               PLAYWRIGHT_BROWSERS_PATH=str(local_appdata / "TradeAgent" / "browsers"))
    return env


def popen(command, *, cwd, env, log):
    with log.open("ab") as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    OWNED.append(process)
    return process


def run(command, *, cwd, env, log, timeout=60):
    process = popen(command, cwd=cwd, env=env, log=log)
    code = process.wait(timeout=timeout)
    if code != 0:
        raise AssertionError(f"Child process failed with exit code {code}; see {log.name}")


def capture_screen(output):
    script = output / "capture-screen.ps1"
    script.write_text(r'''param([string]$OutPath)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
  $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
  $bitmap.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally { $graphics.Dispose(); $bitmap.Dispose() }
''', encoding="utf-8-sig")
    try:
        with (output / "screenshot.log").open("ab") as log:
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-OutPath", str(output / "desktop.png")], stdout=log, stderr=subprocess.STDOUT, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def smoke(bundle, output, workspace):
    ui = Windows()
    assert is_port_free(), "Runner already has a listener on port 8765; refusing to touch it"
    python = bundle / "runtime" / "python.exe"
    executable = bundle / "TradeAgent.exe"
    application = bundle / "app"
    assert python.is_file() and executable.is_file()
    assert " " in str(bundle) and any(ord(c) > 127 for c in str(bundle)), "Build path must exercise Chinese and spaces"

    local = workspace / "隔离 用户资料"
    old_data = workspace / "旧版 空白测试资料"
    gui_data = local / "TradeAgent" / "data"
    local.mkdir(parents=True)
    token = secrets.token_hex(32)
    SECRET_VALUES.append(token)
    env = clean_env(local, old_data, token)
    prefix = [str(python), "-E", "-s", "-X", "utf8"]
    imports = r'''
import importlib, pathlib, sys
root = pathlib.Path(sys.executable).parent
count = 0
for base in (root / "DLLs", root / "Lib" / "site-packages"):
    for file in sorted(base.rglob("*.pyd")):
        path = file.relative_to(base)
        module = ".".join((*path.parts[:-1], path.name.split(".")[0]))
        importlib.import_module(module)
        print("Native import OK:", module, flush=True)
        count += 1
for module in ("fastapi", "uvicorn", "httpx", "openpyxl", "playwright.sync_api", "trade_agent.desktop_server", "trade_agent.desktop_migrate"):
    importlib.import_module(module)
    print("Import OK:", module, flush=True)
assert count >= 20, count
print("All native extensions imported:", count)
'''
    run(prefix + ["-c", imports], cwd=application, env=env, log=output / "native-imports.log")
    note("bundled native extensions import", "All bundled .pyd modules; Chinese and space-containing installation path")

    direct = popen(prefix + ["-m", "trade_agent.desktop_server", "--host", "127.0.0.1", "--port", "8765"], cwd=application, env=env, log=output / "direct-server.log")
    expected_hash = hashlib.sha256(token.encode()).hexdigest()
    wait_for(lambda: health(expected_hash), timeout=75, description="bundled desktop backend health")
    status, body = request("/")
    assert status == 200 and b"<!doctype html" in body[:100].lower(), "Business UI not served"
    assert request("/local/desktop/shutdown", method="POST", token=token)[0] == 200
    assert direct.wait(timeout=25) == 0
    wait_for(listener_absent, description="direct backend listener shutdown")
    note("bundled backend HTTP lifecycle", "Correct session identity, UI response and graceful shutdown")

    old_db = old_data / "trade.sqlite3"
    before = hashlib.sha256(old_db.read_bytes()).hexdigest()
    run(prefix + ["-m", "trade_agent.desktop_migrate", "--source", str(old_data), "--target", str(gui_data), "--report", str(output / "migration-report.json")], cwd=application, env=env, log=output / "migration.log")
    assert (gui_data / "trade.sqlite3").is_file()
    assert old_db.is_file() and hashlib.sha256(old_db.read_bytes()).hexdigest() == before
    note("Windows migration CLI", "Blank test database copied to isolated LOCALAPPDATA; source retained unchanged")

    desktop = popen([str(executable)], cwd=bundle, env=env, log=output / "launcher.log")
    wait_for(lambda: ui.windows(desktop.pid, WINDOW_CLASS), description="native Windows controller")
    first_health = wait_for(health, timeout=90, description="GUI launcher backend health")
    assert first_health.get("desktop_instance") and first_health["desktop_instance"] != expected_hash
    assert desktop.poll() is None
    note("native controller and backend start", f"Controller HWND found for launcher PID {desktop.pid}")

    duplicate = popen([str(executable)], cwd=bundle, env=env, log=output / "duplicate-launch.log")
    assert duplicate.wait(timeout=15) == 0
    assert desktop.poll() is None and len(ui.windows(desktop.pid, WINDOW_CLASS)) == 1
    assert health()["desktop_instance"] == first_health["desktop_instance"]
    note("single-instance relaunch", "Second EXE exits; original controller and backend session retained")

    capture_screen(output)
    ui.close(desktop.pid, confirm=True)
    assert desktop.wait(timeout=30) == 0
    wait_for(listener_absent, description="GUI backend listener shutdown")
    note("native GUI graceful exit", "WM_CLOSE plus test-only Yes click stops owned backend")

    occupied_code = r'''
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"occupied-port-test-sentinel")
HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
'''
    occupied = popen(prefix + ["-c", occupied_code], cwd=application, env=env, log=output / "occupied-server.log")

    def sentinel():
        try:
            return request("/")[1] == b"occupied-port-test-sentinel"
        except (OSError, urllib.error.URLError):
            return False

    wait_for(sentinel, description="occupied port test server")
    blocked = popen([str(executable)], cwd=bundle, env=env, log=output / "occupied-launch.log")
    wait_for(lambda: ui.windows(blocked.pid, WINDOW_CLASS), description="blocked launcher controller")
    ui.click_dialog(blocked.pid, 1, timeout=20)  # Port warning's IDOK.
    assert occupied.poll() is None and sentinel(), "Launcher interrupted the pre-existing process"
    ui.close(blocked.pid, confirm=False)
    assert blocked.wait(timeout=15) == 0
    assert occupied.poll() is None and sentinel()
    occupied.terminate()
    occupied.wait(timeout=10)
    note("occupied port protection", "Original process and sentinel response survive rejected desktop start")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This integration test must run on Windows")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    output = args.output.resolve()
    if not output.is_relative_to(runner_temp):
        parser.error("Smoke output must be inside RUNNER_TEMP")
    output.mkdir(parents=True, exist_ok=True)
    workspace = output / ("isolated-test-" + secrets.token_hex(6))
    workspace.mkdir()
    result = {"passed": False, "tests": RESULTS}
    try:
        smoke(args.bundle.resolve(), output, workspace)
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr, flush=True)
        failure_annotation(result["error"], output, workspace)
        capture_screen(output)
    finally:
        # Only the process IDs created by this test may be terminated. Never kill
        # an executable by name or a process discovered solely from port 8765.
        for process in reversed(OWNED):
            if process.poll() is None:
                try:
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        logs = workspace / "隔离 用户资料" / "TradeAgent" / "logs"
        if logs.is_dir():
            shutil.copytree(logs, output / "launcher-logs", dirs_exist_ok=True)
        # Test data contains transient local tokens and browser state; do not
        # upload it. Diagnostics above contain only synthetic test logs.
        shutil.rmtree(workspace, ignore_errors=True)
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
