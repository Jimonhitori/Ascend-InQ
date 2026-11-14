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
BELOW_NORMAL = 0x00004000
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no console flash from the tray app
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
    out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    for enc in ("h264_nvenc", "h264_amf", "h264_qsv"):
        if enc in out:
            return enc
    return None


def encoder_args(enc):
    quality = str(config.QUALITY.get(config.settings()["quality"], config.QUALITY["standard"])[1])
    if enc == "h264_nvenc":
        return ["-c:v", enc, "-preset", "p4", "-rc", "vbr", "-cq", quality, "-b:v", "0", "-maxrate", "8M", "-bufsize", "16M"]
    if enc == "h264_amf":
        return ["-c:v", enc, "-quality", "speed", "-rc", "qvbr", "-qvbr_quality_level", quality, "-maxrate", "8M"]
    return ["-c:v", enc, "-preset", "veryfast", "-global_quality", quality]


class Recording:
    def __init__(self, exe, enc):
        s = config.settings()
        rec_dir = config.rec_dir()
        rec_dir.mkdir(parents=True, exist_ok=True)
        self.start = time.time()
        stamp = dt.datetime.fromtimestamp(self.start).strftime("%Y-%m-%d %H-%M-%S")
        self.tmp = rec_dir / f"{stamp}.part.mp4"
        self.path = rec_dir / f"{stamp}.mp4"
        monitor, fps = int(s["monitor"]), int(s["fps"])
        cursor = 1 if s["cursor"] else 0
        cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", f"ddagrab=output_idx={monitor}:framerate={fps}:draw_mouse={cursor}",
               *encoder_args(enc), "-g", str(fps * 2),
               "-movflags", "+frag_keyframe+empty_moov",  # stays playable even if the PC crashes
               str(self.tmp)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=(BELOW_NORMAL | NO_WINDOW) if sys.platform == "win32" else 0)
        self.offset = None
        self.items = []  # [[game_time, [itemIDs]]] snapshots of my inventory (client data has no purchase log)

    def snapshot_items(self, player):
        """One small localhost request; records my inventory when it changes."""
        lst, gt = _live("playerlist"), game_time()
        if not isinstance(lst, list) or gt is None:
            return
        me = next((p for p in lst if p.get("riotId") == player or p.get("summonerName") == player
                   or f"{p.get('riotIdGameName')}#{p.get('riotIdTagLine')}" == player), None)
        if not me:
            return
        ids = sorted(i.get("itemID", 0) for i in me.get("items", []))
        if not self.items or self.items[-1][1] != ids:
            self.items.append([round(gt, 1), ids])

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
                            "-c", "copy", "-movflags", "+faststart", str(self.path)], capture_output=True,
                           creationflags=NO_WINDOW)
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
    vids = sorted(config.rec_dir().glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in vids[keep:]:
        old.unlink(missing_ok=True)
        sidecar(old).unlink(missing_ok=True)
        print(f"  古い録画を削除: {old.name}")


def check_ready():
    """Return (ffmpeg_path, encoder) or raise RuntimeError with a user-facing message."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg が見つかりません。コマンドプロンプトで「winget install Gyan.FFmpeg」を実行してから、アプリを起動し直してください。")
    enc = pick_encoder(exe)
    if not enc:
        raise RuntimeError("GPUエンコーダー（NVENC/AMF/QSV）が使えないため、軽量録画ができません。")
    return exe, enc


def run(after_game=None, poll=4, stop=None, enabled=lambda: True, log=print, on_state=lambda s: None):
    """Main loop. after_game(video_path, info) is called after each recorded game.

    stop: threading.Event to end the loop (an ongoing recording is finalized cleanly).
    enabled: callable; when it returns False no new recording starts.
    on_state: called with "waiting" / "recording" / "processing" / "paused".
    """
    import threading
    stop = stop or threading.Event()
    exe, enc = check_ready()
    log(f"録画待機中（{enc}）。LoLの試合が始まると自動で録画します。")
    on_state("waiting")
    while not stop.is_set():
        if not enabled():
            on_state("paused")
            stop.wait(poll)
            continue
        if game_time() is None:
            on_state("waiting")
            stop.wait(poll)
            continue
        name = player_name()
        if not name:  # spectating / replay
            stop.wait(15)
            continue
        rec = Recording(exe, enc)
        stop.wait(1.5)
        rec.sync()
        on_state("recording")
        log(f"[{dt.datetime.now():%H:%M}] 試合を検知 → 録画開始（{name}） {rec.path.name}")
        misses = 0
        tick = 0
        while rec.alive() and time.time() - rec.start < MAX_MINUTES * 60 and not stop.is_set():
            stop.wait(5)
            if game_time() is None:
                misses += 1
                if misses >= 3:
                    break
            else:
                misses = 0
                if rec.offset is None:
                    rec.sync()
                tick += 1
                if tick % 3 == 0:  # every ~15 s
                    rec.snapshot_items(name)
        on_state("processing")
        path, err = rec.stop()
        if not path:
            log(f"録画に失敗しました: {err[:300]}")
            continue
        info = {"start_epoch": rec.start, "offset": rec.offset, "player": name, "items": rec.items}
        sidecar(path).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        size = path.stat().st_size / 1e9
        log(f"[{dt.datetime.now():%H:%M}] 録画終了: {path.name}（{size:.1f} GB）")
        cleanup(int(config.settings()["keep"]))
        if after_game and not stop.is_set():
            try:
                after_game(path, info)
            except Exception as e:  # keep recording future games whatever happens
                log(f"試合後の処理でエラー: {e}")
    on_state("stopped")
