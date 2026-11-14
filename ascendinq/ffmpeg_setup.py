"""Download ffmpeg on first run so users don't have to install it themselves.

Uses the LGPL "shared" Windows build from BtbN/FFmpeg-Builds (GitHub), which
includes the Desktop Duplication capture filter and the NVENC/AMF/QSV encoders.
Only bin/*.exe and bin/*.dll are extracted into <app>/tools/.
"""
import shutil
import subprocess
import zipfile
from pathlib import Path

import requests

from . import config

URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl-shared.zip"
APPROX_MB = 85
NO_WINDOW = 0x08000000


def install_from_zip(zip_path: Path, dest: Path) -> Path:
    """Extract ffmpeg/ffprobe and their DLLs from a build zip. Returns the ffmpeg.exe path."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.namelist()
                   if "/bin/" in m and m.lower().endswith((".exe", ".dll")) and not m.endswith("/")]
        if not any(m.lower().endswith("/bin/ffmpeg.exe") for m in members):
            raise RuntimeError("ダウンロードしたファイルに ffmpeg.exe が含まれていません。")
        for m in members:
            target = dest / Path(m).name
            with z.open(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return dest / "ffmpeg.exe"


def verify(exe: Path) -> bool:
    try:
        out = subprocess.run([str(exe), "-hide_banner", "-filters"], capture_output=True, text=True,
                             timeout=30, creationflags=NO_WINDOW).stdout
        return "ddagrab" in out
    except (OSError, subprocess.SubprocessError):
        return False


def download(progress=lambda pct: None) -> Path:
    """Download and install ffmpeg into config.TOOLS_DIR. Raises RuntimeError on failure."""
    tools = config.TOOLS_DIR
    tools.mkdir(parents=True, exist_ok=True)
    tmp = tools / "ffmpeg-download.zip"
    try:
        with requests.get(URL, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0)) or APPROX_MB * 1_000_000
            done, last = 0, -1
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    pct = int(done * 100 / total)
                    if pct // 25 != last:
                        last = pct // 25
                        progress(pct)
        exe = install_from_zip(tmp, tools)
    except requests.RequestException as e:
        raise RuntimeError(f"ffmpeg のダウンロードに失敗しました: {e.__class__.__name__}") from None
    finally:
        tmp.unlink(missing_ok=True)
    if not verify(exe):
        raise RuntimeError("ダウンロードした ffmpeg が画面録画に対応していませんでした。")
    return exe
