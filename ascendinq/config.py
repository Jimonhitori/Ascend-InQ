"""Paths and settings loaded from .env.

When packaged as an .exe, user files (.env, data, reports, recordings) live
next to the .exe so the app is portable.
"""
import json
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


def account_region() -> str:
    """Account-V1 has no 'sea' cluster; SEA accounts are served from asia."""
    r = region()
    return "asia" if r == "sea" else r


# ---------------------------------------------------------------- servers
SERVERS = {  # platform: (label, match-v5 region)
    "jp1": ("日本 (JP)", "asia"), "kr": ("韓国 (KR)", "asia"),
    "na1": ("北米 (NA)", "americas"), "br1": ("ブラジル (BR)", "americas"),
    "la1": ("ラテンアメリカ北 (LAN)", "americas"), "la2": ("ラテンアメリカ南 (LAS)", "americas"),
    "euw1": ("西ヨーロッパ (EUW)", "europe"), "eun1": ("北東ヨーロッパ (EUNE)", "europe"),
    "tr1": ("トルコ (TR)", "europe"), "ru": ("ロシア (RU)", "europe"), "me1": ("中東 (ME)", "europe"),
    "oc1": ("オセアニア (OCE)", "sea"), "sg2": ("シンガポール (SG)", "sea"), "tw2": ("台湾 (TW)", "sea"),
    "vn2": ("ベトナム (VN)", "sea"),
}


# ---------------------------------------------------------------- app settings (settings.json)
SETTINGS_PATH = ROOT / "settings.json"
QUALITY = {"high": ("高画質", 23), "standard": ("標準", 28), "light": ("軽量", 33)}
DEFAULTS = {
    "source": "client",      # "client" = read from the local League client (no key), "api" = Riot API key
    "capture": "match",      # "match" = record every game, "off" = analysis only
    "save_dir": "",          # empty = <app folder>/recordings
    "keep": 30,              # recordings to keep (0 = keep all)
    "quality": "standard",
    "fps": 30,
    "monitor": 0,
    "cursor": True,
    "auto_review": True,
    "open_viewer": True,
    "notify": True,
}


def settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict):
    SETTINGS_PATH.write_text(json.dumps({k: s[k] for k in DEFAULTS if k in s}, ensure_ascii=False, indent=1),
                             encoding="utf-8")


def rec_dir() -> Path:
    d = settings().get("save_dir") or ""
    return Path(d) if d else ROOT / "recordings"


def write_env(updates: dict):
    """Update KEY=value lines in .env (keeps comments and other keys)."""
    ensure_env()
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in updates and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reload()
