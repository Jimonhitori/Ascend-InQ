"""Paths and settings loaded from .env.

When packaged as an .exe, user files (.env, data, reports, recordings) live
next to the .exe so the app is portable.
"""
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
RESOURCES = Path(getattr(sys, "_MEIPASS", ROOT))  # bundled read-only files
DATA_DIR = ROOT / "data"
MATCH_DIR = DATA_DIR / "matches"
DDRAGON_DIR = DATA_DIR / "ddragon"
REPORT_DIR = ROOT / "reports"
CLIP_DIR = ROOT / "clips"
REC_DIR = ROOT / "recordings"
ENV_PATH = ROOT / ".env"


class ConfigError(Exception):
    pass


def reload():
    load_dotenv(ENV_PATH, override=True)


def ensure_env() -> bool:
    """Create .env from the template if missing. Returns True if it was just created."""
    if ENV_PATH.exists():
        return False
    template = RESOURCES / ".env.example"
    if template.exists():
        shutil.copyfile(template, ENV_PATH)
    else:
        ENV_PATH.write_text("RIOT_API_KEY=\nRIOT_ID=\nPLATFORM=jp1\nREGION=asia\n", encoding="utf-8")
    return True


reload()


def api_key() -> str:
    key = os.getenv("RIOT_API_KEY", "").strip()
    if not key or "xxxx" in key:
        raise ConfigError(
            ".env に RIOT_API_KEY が設定されていません。"
            "developer.riotgames.com で発行したキーを .env に貼ってください。"
        )
    return key


def riot_id() -> str:
    return os.getenv("RIOT_ID", "").strip()


def platform() -> str:
    return os.getenv("PLATFORM", "jp1")


def region() -> str:
    return os.getenv("REGION", "asia")


def video_dir() -> Path | None:
    v = os.getenv("VIDEO_DIR", "").strip()
    return Path(v) if v else None
