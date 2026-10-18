"""Private desktop lifecycle endpoints; never exposed as GPT Actions."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import os
import secrets
from urllib.parse import urlparse

from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from .app import create_app
from .config import Config


def attach_desktop(app, session: str, shutdown):
    if len(session) < 32:
        raise ValueError("桌面会话标识缺失，请从 TradeAgent.exe 启动")
    # Identity is public; the secret used to request shutdown is never returned.
    app.state.desktop_instance = hashlib.sha256(session.encode()).hexdigest()
    app.state.desktop_closing = False

    @app.middleware("http")
    async def closing_guard(request, call_next):
        if app.state.desktop_closing and request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/"):
            return JSONResponse(status_code=503, content={"detail": "工作台正在退出，请重新打开后操作"})
        return await call_next(request)

    @app.post("/local/desktop/shutdown", include_in_schema=False)
    def stop(request: Request, background: BackgroundTasks):
        try:
            local = ipaddress.ip_address(request.client.host).is_loopback
        except (AttributeError, ValueError):
            local = False
        origin = request.headers.get("origin")
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        origin_ok = not origin or (urlparse(origin).hostname in {"localhost", "127.0.0.1"} and urlparse(origin).port in {None, app.state.config.port})
        if not local or host not in {"localhost", "127.0.0.1"} or not origin_ok or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "退出操作只能由本机桌面程序发起")
        if not secrets.compare_digest(request.headers.get("x-desktop-session", ""), session):
            raise HTTPException(403, "桌面会话不匹配")
        if not app.state.tasks.try_quiesce():
            raise HTTPException(409, "仍有任务执行中。请在邮件页暂停发送批次，并在任务记录中等待当前操作结束，再退出工作台。")
        app.state.desktop_closing = True
        background.add_task(shutdown)
        return {"stopping": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口须为1至65535")
    session = os.environ.pop("TRADE_DESKTOP_SESSION", "")
    if len(session) < 32:
        parser.error("请双击 TradeAgent.exe 启动桌面版")
    os.environ["TRADE_HOST"] = args.host
    os.environ["TRADE_PORT"] = str(args.port)
    import uvicorn
    app = create_app(Config.load())
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, proxy_headers=False, access_log=False))
    attach_desktop(app, session, lambda: setattr(server, "should_exit", True))
    server.run()


if __name__ == "__main__":
    main()
