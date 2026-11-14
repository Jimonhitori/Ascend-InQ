"""Step 3: cut death scenes from a recording with ffmpeg (run after the game).

Uses stream copy (no re-encode) for clips and fast seeking for stills, and runs
ffmpeg at below-normal priority so it never competes with the game.
"""
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import config
from .analyze import mmss

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".flv"}
OBS_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _](\d{2})[-_.](\d{2})[-_.](\d{2})")
OUTPLAYED_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})_(\d{1,2})-(\d{1,2})-(\d{1,2})")  # MM-DD-YYYY_H-M-S


def video_start_epoch(path: Path) -> float:
    """Recording start time: from OBS / Outplayed filename, else file creation time."""
    m = OBS_RE.search(path.name)
    if m:
        return dt.datetime(*map(int, m.groups())).timestamp()
    m = OUTPLAYED_RE.search(path.name)
    if m:
        mo, d, y, h, mi, s = map(int, m.groups())
        return dt.datetime(y, mo, d, h, mi, s).timestamp()
    return path.stat().st_ctime


def video_offset(video: Path, game_start_ms: int) -> float:
    """Seconds into the video where the in-game clock is 0:00.
    Exact when recorded by this tool (sidecar .json), else estimated from the start time."""
    side = video.with_suffix(".json")
    if side.exists():
        try:
            off = json.loads(side.read_text(encoding="utf-8")).get("offset")
            if off is not None:
                return float(off)
        except (ValueError, OSError):
            pass
    return game_start_ms / 1000 - video_start_epoch(video)


def default_video_dirs():
    dirs = [config.rec_dir()]
    folder = config.video_dir()
    if folder:
        return dirs + [folder]
    home = Path.home() / "Videos"
    return dirs + [home / "Overwolf" / "Outplayed", home / "OBS", home / "League of Legends", home]


def find_video(game_start_ms: int, folder: Path | None = None) -> Path | None:
    folders = [folder] if folder else default_video_dirs()
    for f in folders:
        if f.exists():
            hit = _find_in(game_start_ms, f, recursive=f != Path.home() / "Videos")
            if hit:
                return hit
    return None


def _find_in(game_start_ms: int, folder: Path, recursive: bool) -> Path | None:
    game_start = game_start_ms / 1000
    best, best_gap = None, None
    for p in (folder.rglob("*") if recursive else folder.iterdir()):
        if p.suffix.lower() not in VIDEO_EXT or not p.is_file() or ".part." in p.name:
            continue
        gap = game_start - video_start_epoch(p)  # recording should start a bit before the game
        if -300 <= gap <= 20 * 60 and (best_gap is None or gap < best_gap):
            best, best_gap = p, gap
    return best


def _ffmpeg(args):
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg が見つかりません。インストールして PATH を通してください。")
    flags = 0x00004000 | 0x08000000 if sys.platform == "win32" else 0  # below-normal priority, no console window
    r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, creationflags=flags)
    return r.returncode == 0, r.stderr.strip()


def cut_deaths(a: dict, video: Path, offset: float | None = None, before=20, after=5):
    """offset = seconds into the video where the in-game clock is 0:00."""
    if offset is None:
        offset = video_offset(video, a["game_start_ms"])
    print(f"  録画: {video.name}  （ゲーム内 0:00 = 動画の {offset:.1f} 秒）")
    out_dir = config.CLIP_DIR / a["match_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for n, d in enumerate(a["deaths"], 1):
        vt = d["t"] + offset
        start = max(0, vt - before)
        tag = mmss(d["t"]).replace(":", "m") + "s"
        clip = out_dir / f"death{n}_{tag}.mp4"
        ok, err = _ffmpeg(["-ss", f"{start:.2f}", "-i", str(video), "-t", f"{before + after}",
                           "-c", "copy", "-avoid_negative_ts", "make_zero", str(clip)])
        if not ok:
            clip.unlink(missing_ok=True)
            clip = clip.with_suffix(video.suffix)
            ok, err = _ffmpeg(["-ss", f"{start:.2f}", "-i", str(video), "-t", f"{before + after}",
                               "-c", "copy", str(clip)])
        if not ok:
            print(f"  デス{n} の切り出しに失敗: {err[:200]}")
            continue
        for k, rel in enumerate((-15, -8, -3, 0), 1):
            _ffmpeg(["-ss", f"{max(0, vt + rel):.2f}", "-i", str(video), "-frames:v", "1",
                     "-vf", "scale=960:-2", "-q:v", "4", str(out_dir / f"death{n}_still{k}.jpg")])
        made += 1
        print(f"  デス{n}（{mmss(d['t'])}）→ {clip.name}")
    return made
