#!/usr/bin/env python3
"""GitHub Windows runner: execute the delivered CMD installer and verify it.

All application data and installed files are confined to RUNNER_TEMP. Existing
runner Desktop/Start Menu shortcuts are backed up and restored. No real account
is connected and no email is sent. This test refuses non-GitHub environments.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import traceback
import uuid

import windows_smoke as smoke


def read_unicode_shortcut(path):
    """Read a .lnk through IShellLinkW/IPersistFile, independently of WScript."""
    class GUID(ctypes.Structure):
        _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                    ("data3", wintypes.WORD), ("data4", wintypes.BYTE * 8)]

    def guid(value):
        return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    def checked(result, operation):
        if result < 0:
            raise OSError(f"{operation} failed: HRESULT 0x{result & 0xffffffff:08X}")

    def method(interface, slot, *argtypes):
        vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[slot])

    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    checked(ole.CoInitializeEx(None, 2), "CoInitializeEx")
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        clsid = guid("00021401-0000-0000-C000-000000000046")
        iid_link = guid("000214F9-0000-0000-C000-000000000046")
        iid_file = guid("0000010B-0000-0000-C000-000000000046")
        checked(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_link), ctypes.byref(link)), "CoCreateInstance(IShellLinkW)")
        checked(method(link, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(link, ctypes.byref(iid_file), ctypes.byref(persist)), "QueryInterface(IPersistFile)")
        checked(method(persist, 5, wintypes.LPCWSTR, wintypes.DWORD)(persist, str(path), 0), "IPersistFile.Load")
        target = ctypes.create_unicode_buffer(32768)
        directory = ctypes.create_unicode_buffer(32768)
        icon = ctypes.create_unicode_buffer(32768)
        icon_index = ctypes.c_int()
        checked(method(link, 3, wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)(link, target, len(target), None, 4), "IShellLinkW.GetPath")
        checked(method(link, 8, wintypes.LPWSTR, ctypes.c_int)(link, directory, len(directory)), "IShellLinkW.GetWorkingDirectory")
        checked(method(link, 16, wintypes.LPWSTR, ctypes.c_int, ctypes.POINTER(ctypes.c_int))(link, icon, len(icon), ctypes.byref(icon_index)), "IShellLinkW.GetIconLocation")
        return {"target": target.value, "directory": directory.value, "icon": icon.value, "icon_index": icon_index.value}
    finally:
        if persist.value:
            method(persist, 2)(persist)
        if link.value:
            method(link, 2)(link)
        ole.CoUninitialize()


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def processes_at(executable):
    """Find only processes whose queried full image path equals our exact file."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    matches = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            if entry.szExeFile.casefold() == executable.name.casefold():
                handle = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if handle:
                    try:
                        image = ctypes.create_unicode_buffer(32768)
                        length = wintypes.DWORD(len(image))
                        if kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
                            if os.path.normcase(image.value) == os.path.normcase(str(executable)):
                                matches.append(entry.th32ProcessID)
                    finally:
                        kernel.CloseHandle(handle)
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return matches


def powershell(code, arguments, *, workspace, env, log):
    script = workspace / ("check-" + secrets.token_hex(4) + ".ps1")
    script.write_text(code, encoding="utf-8-sig")
    smoke.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), *map(str, arguments)], cwd=workspace, env=env, log=log)


def exercise(bundle, output, workspace, shortcuts):
    assert smoke.is_port_free(), "Refusing to disturb a pre-existing listener on port 8765"
    local = workspace / "隔离 用户资料"
    data = local / "TradeAgent" / "data"
    env = smoke.clean_env(local, data, secrets.token_hex(32))
    smoke.SECRET_VALUES.append(env["TRADE_DESKTOP_SESSION"])
    local.mkdir(parents=True)

    metadata = workspace / "shell-folders.json"
    powershell(r'''param([string]$Output)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -lt 1) { throw 'Expected Windows PowerShell 5.1' }
$paths = @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs')) | ForEach-Object { Join-Path $_ '外贸工作台.lnk' }
@{ version = $PSVersionTable.PSVersion.ToString(); paths = @($paths) } | ConvertTo-Json | Set-Content -LiteralPath $Output -Encoding UTF8
''', [metadata], workspace=workspace, env=env, log=output / "powershell.log")
    shell_metadata = json.loads(metadata.read_text(encoding="utf-8-sig"))
    for index, value in enumerate(shell_metadata["paths"]):
        path = Path(value)
        backup = workspace / f"original-shortcut-{index}.lnk"
        existed = path.exists()
        if existed:
            shutil.copy2(path, backup)
        shortcuts.append((path, backup, existed))

    # A real but synthetic existing customer proves installation preserves data;
    # its database also avoids the first-run migration question.
    prefix = [str(bundle / "runtime" / "python.exe"), "-E", "-s", "-X", "utf8"]
    seed = "from trade_agent.config import Config; from trade_agent.store import Store; c=Config.load(); Store(c.data_dir).put('customers', {'name':'Installer preservation test', 'demo':True}, 'installer-sentinel')"
    smoke.run(prefix + ["-c", seed], cwd=bundle / "app", env=env, log=output / "seed-data.log")
    marker = data / "existing-business-file.txt"
    marker.write_text("Existing business file must survive installation.\n", encoding="utf-8")
    marker_hash = sha256(marker)
    key_hash = sha256(data / "secrets" / "api-key.txt")
    with closing(sqlite3.connect(data / "trade.sqlite3")) as database:
        before = database.execute("SELECT data FROM records WHERE kind='customers' AND id='installer-sentinel'").fetchone()[0]

    # Run the actual same CMD entry point the user double-clicks. Setting stdin
    # to DEVNULL prevents a failed install's Read-Host from hanging unattended CI.
    with (output / "installer.log").open("ab") as log:
        installer = subprocess.Popen([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "安装到桌面.cmd"], cwd=bundle, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    smoke.OWNED.append(installer)
    assert installer.wait(timeout=300) == 0, "Delivered CMD installer failed; see installer.log"

    destinations = list((local / "Programs" / "TradeAgent").glob("desktop-0.2.0-*"))
    assert len(destinations) == 1, f"Expected one installed version, got {len(destinations)}"
    destination = destinations[0].resolve()
    executable = destination / "TradeAgent.exe"
    manifest = json.loads((bundle / "bundle-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = destination / entry["path"]
        assert path.is_file() and sha256(path) == entry["sha256"], f"Installed file mismatch: {entry['path']}"
    smoke.note("PowerShell 5.1 CMD installation", f"Version {shell_metadata['version']}; all {len(manifest['files'])} installed files match pinned manifest")

    rows = []
    for location, value in zip(("DesktopDirectory", "Programs"), shell_metadata["paths"]):
        path = Path(value)
        assert path.is_file(), f"Missing shortcut: {location}"
        link = read_unicode_shortcut(path)
        assert os.path.normcase(link["target"]) == os.path.normcase(str(executable)), f"Incorrect Unicode shortcut target: {location}"
        assert os.path.normcase(link["directory"]) == os.path.normcase(str(destination)), f"Incorrect shortcut working directory: {location}"
        assert os.path.normcase(link["icon"]) == os.path.normcase(str(executable)) and link["icon_index"] == 0, f"Incorrect shortcut icon: {location}"
        rows.append({"location": location, "target_verified": True, "working_directory_verified": True, "icon_verified": True, "reader": "IShellLinkW"})
    (output / "shortcuts.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    smoke.note("Desktop and Start Menu shortcuts", "Both target the exact installed EXE and its working directory")

    ui = smoke.Windows()
    pid = smoke.wait_for(lambda: processes_at(executable), timeout=45, description="installer-started exact executable")[0]
    smoke.wait_for(lambda: ui.windows(pid, smoke.WINDOW_CLASS), description="installed controller window")
    smoke.wait_for(smoke.health, timeout=90, description="installed desktop backend health")
    smoke.note("Installer starts usable desktop", "Exact installed image path, native controller and healthy backend verified")
    smoke.capture_screen(output)
    ui.close(pid, confirm=True)
    smoke.wait_for(lambda: not processes_at(executable), timeout=30, description="installed GUI exit")
    smoke.wait_for(smoke.listener_absent, description="installed backend shutdown")

    with closing(sqlite3.connect(data / "trade.sqlite3")) as database:
        after = database.execute("SELECT data FROM records WHERE kind='customers' AND id='installer-sentinel'").fetchone()[0]
    assert before == after, "Installer changed or deleted existing customer data"
    assert sha256(marker) == marker_hash and sha256(data / "secrets" / "api-key.txt") == key_hash
    smoke.note("Existing user data retained", "Customer record, business attachment and API key unchanged after installation/start/exit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("This installer smoke test is restricted to an ephemeral GitHub Windows runner")
    output = args.output.resolve()
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    if not output.is_relative_to(runner_temp):
        parser.error("Output must be inside RUNNER_TEMP")
    output.mkdir(parents=True, exist_ok=True)
    workspace = runner_temp / ("installer-" + secrets.token_hex(6))
    workspace.mkdir()
    shortcuts = []
    result = {"passed": False, "tests": smoke.RESULTS}
    try:
        exercise(args.bundle.resolve(), output, workspace, shortcuts)
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        print(result["error"], file=sys.stderr, flush=True)
        smoke.failure_annotation(result["error"], output, workspace)
        smoke.capture_screen(output)
    finally:
        # Only exact executable paths inside our random isolated installation
        # directory are eligible for cleanup, never all processes with a name.
        cleanup_errors = []

        def cleanup(action):
            try:
                action()
            except Exception as exc:
                cleanup_errors.append(f"{type(exc).__name__}: {exc}")

        programs = workspace / "隔离 用户资料" / "Programs" / "TradeAgent"
        for executable in list(programs.glob("desktop-*/TradeAgent.exe")) + list(programs.glob("desktop-*/runtime/python.exe")):
            try:
                pids = processes_at(executable.resolve())
            except Exception as exc:
                cleanup_errors.append(f"Process query failed: {exc}")
                continue
            for pid in pids:
                cleanup(lambda: subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=20))
        for process in reversed(smoke.OWNED):
            if process.poll() is None:
                cleanup(lambda: subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=20))
        for path, backup, existed in shortcuts:
            if existed:
                cleanup(lambda: shutil.copy2(backup, path))
            else:
                cleanup(lambda: path.unlink(missing_ok=True))
        logs = workspace / "隔离 用户资料" / "TradeAgent" / "logs"
        if logs.is_dir():
            cleanup(lambda: shutil.copytree(logs, output / "launcher-logs", dirs_exist_ok=True))
        if cleanup_errors:
            result["passed"] = False
            result["cleanup_errors"] = cleanup_errors
            smoke.failure_annotation("Installer test cleanup failed: " + "; ".join(cleanup_errors), output, workspace)
        shutil.rmtree(workspace, ignore_errors=True)
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
