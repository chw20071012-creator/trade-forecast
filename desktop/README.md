# Windows desktop distribution

The distribution embeds official CPython 3.12 x64 and pinned Windows wheels. A
Windows GUI launcher starts the loopback server and opens Edge/Chrome in app mode.
The separate control window owns the Python process and handles explicit exit.
Business data lives in `%LOCALAPPDATA%\TradeAgent\data`, outside the versioned app.

Build the launcher following `launcher/README.md`, then run:

```sh
python desktop/build_windows_bundle.py \
  --cache /workspace/scratch/desktop-build/cache \
  --output /workspace/scratch/desktop-build/TradeAgent \
  --launcher /workspace/scratch/desktop-build/TradeAgent.exe \
  --extra-root desktop/distribution \
  --zip dist/TradeAgent-Desktop-0.2.0-Windows-x64.zip
```

The installer is saved with a UTF-8 BOM for Windows PowerShell 5.1. It verifies all
manifest entries, installs a new version directory without replacing data, and
creates current-user Desktop and Start Menu shortcuts. An existing running
desktop instance is activated rather than duplicated. Restart it after updating.

First-run migration accepts an old installation or data directory only when the
destination is empty. It snapshots SQLite, stages the restoration, rebases file
references, copies only named local account files, and commits via rename. It
does not delete the original or resume delivery approvals. Normal backup archives
still exclude credentials.

The private shutdown endpoint requires a process-specific secret, loopback
origin/host checks, and idle task workers. Health exposes only its hash for process
identity. No desktop lifecycle routes appear in public Actions schemas.

The package contains no live credentials or customer database. Windows GUI,
shortcut creation and real account connectivity require target-machine testing;
Linux tests do not substitute for those checks.
