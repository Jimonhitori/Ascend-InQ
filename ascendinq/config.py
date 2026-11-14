"""Paths and settings loaded from .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MATCH_DIR = DATA_DIR / "matches"
DDRAGON_DIR = DATA_DIR / "ddragon"
REPORT_DIR = ROOT / "reports"
CLIP_DIR = ROOT / "clips"

load_dotenv(ROOT / ".env")


class ConfigError(Exception):
    pass


def api_key() -> str:
    key = os.getenv("RIOT_API_KEY", "").strip()
    if not key or "xxxx" in key:
        raise ConfigError(
            ".env に RIOT_API_KEY が設定されていません。"
            ".env.example をコピーして .env を作り、developer.riotgames.com で発行したキーを貼ってください。"
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
