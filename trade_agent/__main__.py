from __future__ import annotations
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="AI 外贸工作台（仅用户指令触发）")
    parser.add_argument("--host", default=os.environ.get("TRADE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("TRADE_PORT", "8765")))
    args = parser.parse_args()
    os.environ["TRADE_HOST"] = args.host
    os.environ["TRADE_PORT"] = str(args.port)
    import uvicorn
    from .app import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
