"""Lightweight auto-recorder.

Waits for a League game via the local Live Client Data API (one tiny localhost
request every few seconds), records the screen with ffmpeg using Desktop
Duplication + the GPU encoder (NVENC/AMF/QSV, no CPU encoding), stops when the
game ends, then (optionally) fetches the match and builds the viewer.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
import urllib3

from . import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIVE = "https://127.0.0.1:2999/liveclientdata"
REC_DIR = config.ROOT / "recordings"
BELOW_NORMAL = 0x00004000
MAX_MINUTES = 90


def _live(path):
    try:
        r = requests.get(f"{LIVE}/{path}", timeout=1.5, verify=False)
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def game_time():
    d = _live("gamestats")
    return d.get("gameTime") if isinstance(d, dict) else None


def player_name():
    d = _live("activeplayername")  # fails while spectating / watching a replay
    return d if isinstance(d, str) and d else None


def pick_encoder(exe):
    out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    for enc in ("h264_nvenc", "h264_amf", "h264_qsv"):
        if enc in out:
            return enc
    return None


def encoder_args(enc):
    quality = os.getenv("RECORD_QUALITY", "30")  # lower = better quality, bigger file
    if enc == "h264_nvenc":
        return ["-c:v", enc, "-preset", "p4", "-rc", "vbr", "-cq", quality, "-b:v", "0", "-maxrate", "8M", "-bufsize", "16M"]
    if enc == "h264_amf":
        return ["-c:v", enc, "-quality", "speed", "-rc", "qvbr", "-qvbr_quality_level", quality, "-maxrate", "8M"]
    return ["-c:v", enc, "-preset", "veryfast", "-global_quality", quality]


class Recording:
    def __init__(self, exe, enc):
        REC_DIR.mkdir(parents=True, exist_ok=True)
        self.start = time.time()
        stamp = dt.datetime.fromtimestamp(self.start).strftime("%Y-%m-%d %H-%M-%S")
        self.tmp = REC_DIR / f"{stamp}.part.mp4"
        self.path = REC_DIR / f"{stamp}.mp4"
        monitor = os.getenv("RECORD_MONITOR", "0")
        fps = os.getenv("RECORD_FPS", "30")
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", f"ddagrab=output_idx={monitor}:framerate={fps}:draw_mouse=1",
               *encoder_args(enc), "-g", str(int(fps) * 2),
               "-movflags", "+frag_keyframe+empty_moov",  # stays playable even if the PC crashes
               str(self.tmp)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=BELOW_NORMAL if sys.platform == "win32" else 0)
        self.offset = None

    def sync(self):
        """offset = seconds into the video where the in-game clock reads 0:00."""
        gt = game_time()
        if gt is not None:
            self.offset = round((time.time() - self.start) - gt, 2)

    def alive(self):
        return self.proc.poll() is None

    def stop(self):
        try:
            _, err = self.proc.communicate(b"q" if self.alive() else None, timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            _, err = self.proc.communicate()
        err = (err or b"").decode(errors="replace")
        if not self.tmp.exists() or self.tmp.stat().st_size < 100_000:
            self.tmp.unlink(missing_ok=True)
            return None, err.strip()
        # remux to a normal mp4 (fast, no re-encode) so browsers seek smoothly
        exe = shutil.which("ffmpeg")
        r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(self.tmp),
                            "-c", "copy", "-movflags", "+faststart", str(self.path)], capture_output=True)
        if r.returncode == 0:
            self.tmp.unlink(missing_ok=True)
        else:
            self.tmp.rename(self.path)
        return self.path, ""


def sidecar(video: Path) -> Path:
    return video.with_suffix(".json")


def cleanup(keep: int):
    if keep <= 0:
        return
    vids = sorted(REC_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in vids[keep:]:
        old.unlink(missing_ok=True)
        sidecar(old).unlink(missing_ok=True)
        print(f"  古い録画を削除: {old.name}")


def run(after_game=None, poll=4):
    """Main loop. after_game(video_path, info) is called after each recorded game."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg が見つかりません。")
    enc = pick_encoder(exe)
    if not enc:
        raise RuntimeError("GPUエンコーダー（NVENC/AMF/QSV）が使えないため、軽量録画ができません。")
    keep = int(os.getenv("RECORD_KEEP", "30"))
    print(f"Ascend InQ: 録画待機中（{enc}）。LoLの試合が始まると自動で録画します。止めるには Ctrl+C。")
    while True:
        if game_time() is None:
            time.sleep(poll)
            continue
        name = player_name()
        if not name:  # spectating / replay
            time.sleep(15)
            continue
        rec = Recording(exe, enc)
        time.sleep(1.5)
        rec.sync()
        print(f"[{dt.datetime.now():%H:%M}] 試合を検知 → 録画開始（{name}） {rec.path.name}")
        misses = 0
        while rec.alive() and time.time() - rec.start < MAX_MINUTES * 60:
            time.sleep(5)
            if game_time() is None:
                misses += 1
                if misses >= 3:
                    break
            else:
                misses = 0
                if rec.offset is None:
                    rec.sync()
        path, err = rec.stop()
        if not path:
            print(f"  録画に失敗しました: {err[:300]}")
            continue
        info = {"start_epoch": rec.start, "offset": rec.offset, "player": name}
        sidecar(path).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        size = path.stat().st_size / 1e9
        print(f"[{dt.datetime.now():%H:%M}] 録画終了: {path.name}（{size:.1f} GB）")
        cleanup(keep)
        if after_game:
            try:
                after_game(path, info)
            except Exception as e:  # keep recording future games whatever happens
                print(f"  試合後の処理でエラー: {e}")
