"""In-app window for the viewer / game list (WebView2 via pywebview), instead of the browser.

The window runs in its own process (GUI loops need their own main thread, and the
tray already owns ours). Only one window exists: asking to open another page while
it is open just navigates the existing window and brings it to the front.
"""
import ctypes
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config

MUTEX = "AscendInQ_Viewer"
REQUEST = config.DATA_DIR / "viewer_request.txt"
NO_WINDOW = 0x08000000


def _uri(path) -> str:
    return Path(path).resolve().as_uri()


def _window_running() -> bool:
    if sys.platform != "win32":
        return False
    h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX)  # SYNCHRONIZE
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def open_in_app(path):
    """Show a report/viewer HTML page in the Ascend InQ window (starting it if needed)."""
    path = str(Path(path).resolve())
    if _window_running():
        REQUEST.parent.mkdir(parents=True, exist_ok=True)
        REQUEST.write_text(path, encoding="utf-8")
        return
    if config.FROZEN:
        cmd = [sys.executable, "--window", path]
    else:
        cmd = [str(Path(sys.executable).with_name("pythonw.exe")), str(config.ROOT / "app.py"), "--window", path]
    subprocess.Popen(cmd, cwd=str(config.ROOT), creationflags=NO_WINDOW if sys.platform == "win32" else 0)


def run_window(path):
    """Entry point of the window process."""
    import webview

    if sys.platform == "win32":
        ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX)
        if ctypes.windll.kernel32.GetLastError() == 183:  # another window started a moment ago
            REQUEST.parent.mkdir(parents=True, exist_ok=True)
            REQUEST.write_text(str(Path(path).resolve()), encoding="utf-8")
            return
    try:  # a request that arrived while we were starting wins over the start page
        pending = REQUEST.read_text(encoding="utf-8-sig").strip()
        if pending:
            path = pending
    except OSError:
        pass
    REQUEST.unlink(missing_ok=True)
    win = webview.create_window("Ascend InQ", _uri(path), width=1440, height=900, min_size=(960, 600),
                                background_color="#0e1115", text_select=True, maximized=True)

    loaded = threading.Event()
    win.events.loaded += lambda: loaded.set()

    def bring_to_front():
        """Plain async Win32 calls: never block on the GUI thread (cross-thread pywebview
        calls such as on_top during start-up froze the window once)."""
        if sys.platform != "win32":
            return
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW(None, "Ascend InQ")
        if hwnd:
            u32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
            u32.SetForegroundWindow(hwnd)

    def watch():
        # runs after the GUI loop is up (webview.start's func); never let one failure stop it
        loaded.wait(30)  # don't navigate while the first page is still loading
        while True:
            time.sleep(0.4)
            try:
                target = REQUEST.read_text(encoding="utf-8-sig").strip()
                REQUEST.unlink(missing_ok=True)
            except OSError:
                continue
            if not target:
                continue
            try:
                loaded.clear()
                win.load_url(_uri(target))
                (config.ROOT / "logs").mkdir(exist_ok=True)
                with open(config.ROOT / "logs" / "window.log", "a", encoding="utf-8") as f:
                    f.write(time.strftime("%H:%M:%S") + " open " + target + "\n")
                bring_to_front()
                loaded.wait(30)  # one navigation at a time
            except Exception:
                loaded.set()

    # private_mode=False keeps localStorage (per-game video sync offsets) between sessions
    webview.start(watch, private_mode=False, storage_path=str(config.DATA_DIR / "webview"))
