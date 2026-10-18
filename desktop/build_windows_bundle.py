#!/usr/bin/env python3
"""Assemble an offline Windows x64 distribution from pinned official artifacts.

Works on Linux or Windows with Python 3.10+ and the standard library only.
It does not execute downloaded code, fetch a browser, access user data or publish.
Example (run from the repository):
  python desktop/build_windows_bundle.py --cache /tmp/trade-cache \
    --output /tmp/TradeAgent --launcher desktop/build/TradeAgent.exe \
    --extra-root desktop/distribution --zip /tmp/TradeAgent-windows-x64.zip

The first invocation downloads CPython from NuGet and wheels from PyPI. Subsequent
invocations can use --offline. Hashes are pinned in requirements-windows.lock.json;
the runtime hash was cross-checked with the PSF NuGet catalog and wheel hashes with
their individual PyPI release JSON documents, linked in that lock file.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import urllib.parse
import urllib.request
import zipfile


REPOSITORY = Path(__file__).resolve().parents[1]
LOCK_PATH = Path(__file__).with_name("requirements-windows.lock.json")
SOURCE_DIRECTORIES = ("trade_agent", "static", "templates", "demo", "scripts", "docs", ".agents/skills")
SOURCE_FILES = ("requirements.txt", "requirements-lock.txt", "skills.lock.json")
SKIP_NAMES = {"__pycache__", ".git", ".runtime", ".venv", ".pytest_cache", "tests", ".DS_Store"}
MARKER_NAME = ".trade-agent-generated-bundle"
METADATA_FILES = {"bundle-manifest.json", "SHA256SUMS.txt"}
ZIP_DATE = (2026, 10, 18, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def validate_requirements(lock: dict, repository: Path) -> None:
    """Prevent unnoticed dependency drift between the app and desktop package."""
    expected = {}
    for line in (repository / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if not match:
            raise ValueError(f"Unsupported runtime requirement: {line}")
        expected[canonical(match[1])] = match[2]
    actual = {canonical(item["name"]): item["version"] for item in lock["wheels"]}
    if expected != actual:
        raise ValueError("Desktop artifact lock and requirements-lock.txt differ; review and re-pin official artifacts first.")


def verify_artifact(path: Path, item: dict) -> bool:
    if not path.is_file() or path.stat().st_size != item["size"]:
        return False
    if sha256(path) != item["sha256"]:
        return False
    if "sha512_base64" in item:
        actual = base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode("ascii")
        if actual != item["sha512_base64"]:
            return False
    return True


def obtain(item: dict, directory: Path, offline: bool) -> Path:
    path = directory / item["filename"]
    if verify_artifact(path, item):
        print(f"Verified cache: {path.name}", flush=True)
        return path
    if offline:
        raise ValueError(f"Missing or hash-mismatched cached artifact: {path.name}")
    parsed = urllib.parse.urlparse(item["url"])
    if parsed.scheme != "https" or parsed.hostname not in {"api.nuget.org", "files.pythonhosted.org"}:
        raise ValueError("Artifact URL must be an official HTTPS NuGet or PyPI download URL")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    print(f"Downloading: {path.name}", flush=True)
    # urllib keeps inherited HTTP(S)_PROXY and platform CA validation intact.
    try:
        with urllib.request.urlopen(item["url"], timeout=120) as response, temporary.open("wb") as target:
            shutil.copyfileobj(response, target, 1024 * 1024)
        if not verify_artifact(temporary, item):
            raise ValueError(f"Official artifact hash verification failed: {path.name}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def safe_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts or "\\" in info.filename or ":" in info.filename:
        raise ValueError(f"Unsafe archive path: {info.filename}")
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise ValueError(f"Archive symlinks are not supported: {info.filename}")
    return path.parts


def unpack_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    if info.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def extract_runtime(archive_path: Path, runtime: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            parts = safe_parts(info)
            if not parts or parts[0] != "tools" or len(parts) < 2:
                continue
            unpack_member(archive, info, runtime.joinpath(*parts[1:]))
    # NuGet's tools tree is a full relocatable Python layout, not the embeddable
    # ._pth distribution. Its normal sys.path discovers Lib/site-packages and
    # the -m invocation's working directory (app/), even with -E -s.
    if list(runtime.glob("*._pth")):
        raise ValueError("Unexpected restricted Python ._pth layout; validate module discovery before release")
    verify_pe_x64(runtime / "python.exe")


def verify_pe_x64(path: Path) -> None:
    with path.open("rb") as source:
        if source.read(2) != b"MZ":
            raise ValueError(f"Expected a Windows executable: {path.name}")
        source.seek(0x3C)
        offset = struct.unpack("<I", source.read(4))[0]
        source.seek(offset)
        if source.read(4) != b"PE\x00\x00" or struct.unpack("<H", source.read(2))[0] != 0x8664:
            raise ValueError(f"Expected an x64 PE executable: {path.name}")


def install_wheel(archive_path: Path, runtime: Path) -> None:
    """Wheel spread step, without running host-platform pip console generators."""
    site = runtime / "Lib" / "site-packages"
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            parts = safe_parts(info)
            if not parts:
                continue
            target = site.joinpath(*parts)
            if parts[0].endswith(".data"):
                if len(parts) < 2:
                    continue
                kind, relative = parts[1], parts[2:]
                roots = {"purelib": site, "platlib": site, "scripts": runtime / "Scripts",
                         "headers": runtime / "include", "data": runtime}
                if kind not in roots:
                    raise ValueError(f"Unknown wheel spread category: {kind}")
                target = roots[kind].joinpath(*relative)
            unpack_member(archive, info, target)


def copy_source(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"Source symlinks are not supported: {source.name}")
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir()):
            if child.name in SKIP_NAMES or child.suffix in {".pyc", ".pyo", ".log"}:
                continue
            copy_source(child, destination / child.name)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def licenses_index(root: Path, lock: dict) -> None:
    rows = ["THIRD-PARTY SOFTWARE IN THIS WINDOWS DISTRIBUTION", "",
            "CPython 3.12.10 — Python Software Foundation", "License: runtime/LICENSE.txt", "",
            "Python dependency licenses remain inside each package's .dist-info directory.",
            "Playwright includes its own Node runtime and third-party notices; all are retained.", ""]
    site = root / "runtime" / "Lib" / "site-packages"
    for wheel in lock["wheels"]:
        rows.extend([f"{wheel['name']} {wheel['version']}", f"License metadata: {wheel['license']}"])
        prefix = canonical(wheel["name"])
        matches = [p for p in site.glob("*.dist-info")
                   if canonical(p.name.removesuffix(".dist-info").rsplit("-", 1)[0]) == prefix]
        for package in sorted(matches):
            for path in sorted(package.rglob("*")):
                if path.is_file() and any(term in path.name.lower() for term in ("license", "copying", "notice")):
                    rows.append("  " + path.relative_to(root).as_posix())
        rows.append("")
    (root / "THIRD-PARTY-LICENSES.txt").write_text("\n".join(rows), encoding="utf-8")


def manifest(root: Path, lock: dict) -> None:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in METADATA_FILES:
            files.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size,
                          "sha256": sha256(path)})
    data = {"format_version": 1, "product": "Trade Agent Desktop", "target": "Windows x64",
            "runtime": lock["runtime"], "dependencies": lock["wheels"],
            "browser": "Uses installed Microsoft Edge or Google Chrome; no Chromium download is bundled.",
            "user_data": "%LOCALAPPDATA%/TradeAgent/data (created at first run, never copied from the build machine)",
            "omitted": [".runtime", ".git", "tests", "credentials", "user databases", "browser profiles"],
            "files": files}
    (root / "bundle-manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"{sha256(path)}  {path.relative_to(root).as_posix()}"
             for path in sorted(root.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.txt"]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_zip(root: Path, destination: Path) -> None:
    if not (root / "TradeAgent.exe").is_file():
        raise ValueError("Refusing to create a distributable ZIP without TradeAgent.exe; pass --launcher")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    name = (Path("TradeAgent") / path.relative_to(root)).as_posix()
                    info = zipfile.ZipInfo(name, ZIP_DATE)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    with path.open("rb") as source, archive.open(info, "w") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    destination.with_name(destination.name + ".sha256").write_text(
        f"{sha256(destination)}  {destination.name}\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, default=REPOSITORY / ".desktop-cache")
    parser.add_argument("--output", type=Path, default=REPOSITORY / "dist" / "TradeAgent-windows-x64")
    parser.add_argument("--launcher", type=Path, help="Compiled Windows x64 launcher to copy as TradeAgent.exe")
    parser.add_argument("--extra-root", type=Path, action="append", default=[], help="Add distribution text/install scripts from this directory")
    parser.add_argument("--zip", type=Path, dest="zip_path", help="Optional final distribution ZIP; requires --launcher")
    parser.add_argument("--offline", action="store_true", help="Use already downloaded and verified artifacts only")
    args = parser.parse_args()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    validate_requirements(lock, REPOSITORY)
    output = args.output.resolve()
    if output == REPOSITORY or REPOSITORY.is_relative_to(output):
        raise ValueError("Output must not contain the source repository")
    if output.exists() and not (output / MARKER_NAME).is_file():
        raise ValueError("Refusing to replace a directory not created by this builder")
    cache = args.cache.resolve()
    if cache == output or cache.is_relative_to(output):
        raise ValueError("Artifact cache must be outside the generated output")
    if args.launcher:
        verify_pe_x64(args.launcher)
    runtime_archive = obtain(lock["runtime"], cache, args.offline)
    with ThreadPoolExecutor(max_workers=4) as pool:
        wheels = list(pool.map(lambda item: obtain(item, cache / "wheels", args.offline), lock["wheels"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="trade-desktop-build-", dir=output.parent))
    try:
        (temporary / MARKER_NAME).write_text("Generated output of desktop/build_windows_bundle.py\n", encoding="ascii")
        extract_runtime(runtime_archive, temporary / "runtime")
        for wheel in wheels:
            install_wheel(wheel, temporary / "runtime")
        for name in SOURCE_DIRECTORIES + SOURCE_FILES:
            copy_source(REPOSITORY / name, temporary / "app" / name)
        if args.launcher:
            shutil.copyfile(args.launcher, temporary / "TradeAgent.exe")
        for extra in args.extra_root:
            for path in sorted(extra.iterdir()):
                if path.name in {"runtime", "app", "TradeAgent.exe", MARKER_NAME} | METADATA_FILES:
                    raise ValueError(f"Extra distribution file conflicts with bundle content: {path.name}")
                copy_source(path, temporary / path.name)
        licenses_index(temporary, lock)
        manifest(temporary, lock)
        if output.exists():
            shutil.rmtree(output)
        temporary.replace(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    if args.zip_path:
        make_zip(output, args.zip_path.resolve())
    print(json.dumps({"bundle": str(output), "files": sum(p.is_file() for p in output.rglob("*")),
                      "uncompressed_bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
                      "zip": str(args.zip_path) if args.zip_path else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
