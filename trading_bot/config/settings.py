from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dependency added in requirements
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"


def _manual_load_env_file(path: Path) -> None:
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            cleaned = value.strip().strip('"').strip("'")
            os.environ[key] = cleaned
    except Exception:
        return


if ENV_PATH.exists():
    if load_dotenv:
        load_dotenv(ENV_PATH, override=False)
    else:
        _manual_load_env_file(ENV_PATH)


def get_env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default))


def get_env_bool(name: str, default: bool = False) -> bool:
    raw = get_env(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_env_int(name: str, default: int) -> int:
    raw = get_env(name, str(default)).strip()
    try:
        return int(raw)
    except Exception:
        return int(default)


APP_HOST = get_env("APP_HOST", "127.0.0.1")
APP_PORT = get_env_int("APP_PORT", 8008)
BUILD_ON_START = get_env_bool("BUILD_ON_START", True)
DATABASE_URL = get_env("DATABASE_URL", "")
DATABASE_CONNECT_TIMEOUT = get_env_int("DATABASE_CONNECT_TIMEOUT", 5)
SUPABASE_PROJECT_URL = get_env("SUPABASE_PROJECT_URL", "")
SUPABASE_PUBLISHABLE_KEY = get_env("SUPABASE_PUBLISHABLE_KEY", "")
RESEARCH_SOURCE_PATH = Path(get_env("RESEARCH_SOURCE_PATH", str(Path.home() / "Documents" / "ai-crypto-research.md"))).expanduser()
TESTNET_API_KEY = get_env("TESTNET_API_KEY", "")
TESTNET_SECRET = get_env("TESTNET_SECRET", "")
BINANCE_API_KEY = get_env("BINANCE_API_KEY", "")
BINANCE_SECRET = get_env("BINANCE_SECRET", "")
BLOCKED_COINS = get_env("BLOCKED_COINS", "")
BOT_DISABLE_NEW_BUYS = get_env_bool("BOT_DISABLE_NEW_BUYS", False)
