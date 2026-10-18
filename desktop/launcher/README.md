# Windows desktop controller

This is a native Windows x64 GUI executable written in Go. It starts the packaged
Python backend and opens Microsoft Edge or Google Chrome in an independent app
window. Browser downloads, OAuth popups, and external links retain the browser's
standard behavior. It does not embed WebView2, require an SDK, install a service,
or request administrator privileges.

## Layout and contract

```text
TradeAgent.exe
runtime/python.exe
app/trade_agent/desktop_server.py
app/trade_agent/desktop_migrate.py
app/static/...
```

User data is stored at `%LOCALAPPDATA%/TradeAgent/data`; logs are stored beside it
in `logs`. Backend invocation is:

```text
runtime/python.exe -E -s -X utf8 -m trade_agent.desktop_server --host 127.0.0.1 --port 8765
```

The working directory is `app`. The launcher supplies `TRADE_DATA_DIR`,
`TRADE_API_KEY_FILE`, and a random 256-bit `TRADE_DESKTOP_SESSION`. All inherited
`TRADE_*` and Python configuration variables are removed first.
The selected Edge/Chrome executable is supplied as `TRADE_BROWSER_EXECUTABLE`;
`PLAYWRIGHT_BROWSERS_PATH` points to `%LOCALAPPDATA%/TradeAgent/browsers`.
The independent browser window uses `%LOCALAPPDATA%/TradeAgent/browser-profile`
via `--user-data-dir`, keeping its browser profile separate from ordinary browsing.

`GET /health` must return `status=ok`, `application=trade_agent` and
`desktop_instance=SHA256(TRADE_DESKTOP_SESSION)` in hexadecimal. A successful
health response from another server is never reused. Port conflicts are reported
without killing the occupying process or changing the configured port.

An explicit user exit sends `POST /local/desktop/shutdown` with the
`X-Desktop-Session` header. A 409 response leaves the application running and
asks the user to pause pending work. No forced shutdown follows a 409, a network
error, or a delayed normal shutdown. Only a newly spawned child that fails its
initial health check within 75 seconds is terminated by its owned process handle.
Closing an Edge/Chrome window does not stop the backend. A named Windows mutex
prevents multiple desktop controllers in the same login session.

When `data/trade.sqlite3` does not exist, the controller asks whether to import
an existing installation. The native Windows folder picker selects the old
installation root, and the following command must succeed before service start:

```text
python.exe -E -s -X utf8 -m trade_agent.desktop_migrate --source OLD_ROOT --target DATA --report LOGS/migration-report.json
```

Cancel exits. Migration errors do not silently create a blank new workspace.

## Rebuild

Requires Go 1.22 or later. The launcher has no third-party runtime modules.
`resource_windows_amd64.syso` embeds the checked-in original icon and application
manifest. To regenerate resources, use the pinned build-only tool:

```sh
go install github.com/akavel/rsrc@v0.10.2
rsrc -arch amd64 -ico TradeAgent.ico -manifest TradeAgent.manifest -o resource_windows_amd64.syso
go test ./...
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags='-s -w -H=windowsgui' -o TradeAgent.exe .
```

The binary is unsigned. Linux cross-compilation and unit tests do not substitute
for a real Windows interactive smoke test (first-run import, Unicode paths,
downloads, OAuth popups, repeated launch, occupied port, and safe exit).
