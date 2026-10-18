from __future__ import annotations

import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    data_dir: Path
    api_key: str
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def load(cls) -> "Config":
        data_dir = Path(os.environ.get("TRADE_DATA_DIR", str(ROOT / ".runtime" / "data"))).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        key_file = Path(os.environ.get("TRADE_API_KEY_FILE", str(data_dir / "secrets" / "api-key.txt")))
        key_file.parent.mkdir(parents=True, exist_ok=True)
        if key_file.exists():
            key = key_file.read_text(encoding="utf-8").strip()
            if len(key) < 32:
                raise ValueError("本机接口密钥过短，请重新生成至少 32 个字符的密钥")
        else:
            key = secrets.token_urlsafe(48)
            fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(key)
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".runtime" / "browsers"))
        if shutil.which("chromium"):
            os.environ.setdefault("TRADE_BROWSER_EXECUTABLE", str(shutil.which("chromium")))
        return cls(data_dir, key, os.environ.get("TRADE_HOST", "127.0.0.1"), int(os.environ.get("TRADE_PORT", "8765")))
