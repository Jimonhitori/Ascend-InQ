"""Ascend InQ tray app: sits in the notification area while you play LoL.

Start it when you want to play, quit it from the tray menu when you're done.
"""
import ctypes
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
from pathlib import Path

import pystray

from . import config
from .i18n import t
from .icon import make_icon
from .window import open_in_app

APP = "Ascend InQ"


def _single_instance() -> bool:
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "AscendInQ_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def _message(text):
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, APP, 0x40)


def _ask_yes_no(text) -> bool:
    if sys.platform != "win32":
        return False
    return ctypes.windll.user32.MessageBoxW(None, text, APP, 0x04 | 0x20 | 0x40000) == 6  # YESNO|QUESTION|TOPMOST


class TrayApp:
    def __init__(self):
        (config.ROOT / "logs").mkdir(exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(config.ROOT / "logs" / "app.log", maxBytes=1_000_000,
                                                       backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger = logging.getLogger("ascendinq")
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        self.stop = threading.Event()
        self.state = "starting"
        self.icon = pystray.Icon("AscendInQ", make_icon("starting"), APP, menu=self._menu())
        self.worker = None

    # ------------------------------------------------------------ helpers
    def log(self, msg):
        self.logger.info(msg)

    def notify(self, title, msg, important=False):
        self.log(f"{title}: {msg}")
        if not important and not config.settings()["notify"]:
            return
        try:
            self.icon.notify(msg, title)
        except Exception:
            pass

    def alert(self, title, msg):
        self.notify(title, msg, important=True)

    def set_setting(self, key, value):
        s = config.settings()
        s[key] = value
        config.save_settings(s)
        self.icon.update_menu()

    def set_state(self, s):
        if s == self.state:
            return
        self.state = s
        self.icon.icon = make_icon(s)
        self.icon.title = f"{APP} — {t('state.' + s)}"
        self.icon.update_menu()
        if s == "recording":
            self.notify(t("n.rec_started"), t("n.rec_started_msg"))

    def background(self, fn):
        threading.Thread(target=self._guard(fn), daemon=True).start()

    def _guard(self, fn):
        def run():
            try:
                fn()
            except Exception as e:
                self.notify(t("n.error"), str(e)[:200], important=True)
        return run

    # ------------------------------------------------------------ recorder
    def after_game(self, video, info):
        from . import pipeline
        if not config.settings()["auto_review"]:
            self.notify(t("n.saved"), video.name)
            return
        self.notify(t("n.saved"), t("n.saved_msg"))
        a, path = pipeline.review_after_game(video, info, config.riot_id(), self.log, self.stop)
        if a:
            self.notify(t("n.ready"), t("n.focus") + a["focus"])
            if config.settings()["open_viewer"]:
                open_in_app(path, front=False, start_if_closed=False)  # never pop up after a game

    def ensure_ffmpeg(self) -> bool:
        if config.ffmpeg_path():
            return True
        from . import ffmpeg_setup
        if not _ask_yes_no(t("ff.ask", mb=ffmpeg_setup.APPROX_MB)):
            self.alert(APP, t("ff.skipped"))
            return False
        self.notify(t("ff.downloading"), t("ff.progress", pct=0), important=True)
        try:
            ffmpeg_setup.download(lambda pct: self.log(t("ff.progress", pct=pct)))
        except RuntimeError as e:
            self.alert(t("n.error"), str(e))
            return False
        self.notify(t("ff.done"), "", important=True)
        return True

    def recorder_loop(self):
        # heavy imports (requests etc.) happen here, after the tray icon is already visible
        from . import recorder
        if recorder.league_window_mode() == 0 and config.settings()["capture"] != "off":
            self.alert(t("n.fullscreen"), t("n.fullscreen_msg"))
        if not self.ensure_ffmpeg():
            self.set_state("error")
            return
        try:
            recorder.run(self.after_game, stop=self.stop, enabled=lambda: config.settings()["capture"] != "off",
                         log=self.log, on_state=self.set_state, alert=self.alert)
        except RuntimeError as e:
            self.set_state("error")
            self.alert(t("n.cannot_record"), str(e))

    # ------------------------------------------------------------ menu actions
    def toggle_record(self, icon, item):
        self.set_setting("capture", "off" if config.settings()["capture"] != "off" else "match")

    def toggle_open(self, icon, item):
        self.set_setting("open_viewer", not config.settings()["open_viewer"])

    def open_latest(self, icon=None, item=None):
        from . import pipeline
        p = pipeline.latest_viewer()
        if p:
            open_in_app(p)
        else:
            self.notify(t("n.no_games"), t("n.no_games_msg"), important=True)

    def open_index(self, icon=None, item=None):
        p = config.REPORT_DIR / "index.html"
        if p.exists():
            open_in_app(p)
        else:
            self.import_recent()

    def import_recent(self, icon=None, item=None):
        def work():
            from . import pipeline
            if config.settings()["source"] == "api" and not config.riot_id():
                raise RuntimeError(t("n.need_riot_id"))
            self.notify(t("n.importing"), t("n.importing_msg"))
            riot_id, puuid, ids, new = pipeline.import_recent(5, self.log)
            for mid in ids:
                pipeline.build(mid, puuid)
            idx = pipeline.refresh_index(riot_id, puuid)
            self.notify(t("n.imported"), t("n.imported_msg", rid=riot_id, n=len(new)))
            if idx:
                open_in_app(idx)
        self.background(work)

    def open_folder(self, target):
        def action(icon=None, item=None):
            path = target() if callable(target) else target
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        return action

    def open_settings(self, icon=None, item=None):
        """The settings window runs as its own process so Tk never shares a thread with the tray."""
        config.ensure_env()
        if config.FROZEN:
            cmd = [sys.executable, "--settings"]
        else:
            cmd = [str(Path(sys.executable).with_name("pythonw.exe")), str(config.ROOT / "app.py"), "--settings"]
        subprocess.Popen(cmd, cwd=str(config.ROOT))

    def quit(self, icon, item):
        self.stop.set()
        if self.state == "recording":
            self.notify(t("n.quitting"), t("n.quitting_msg"))
        if self.worker:
            self.worker.join(timeout=40)
        icon.stop()

    def _menu(self):
        Item, Menu = pystray.MenuItem, pystray.Menu
        return Menu(
            Item(lambda item: t("state." + self.state), None, enabled=False),
            Menu.SEPARATOR,
            Item(lambda item: t("menu.latest"), self.open_latest, default=True),
            Item(lambda item: t("menu.index"), self.open_index),
            Item(lambda item: t("menu.import"), self.import_recent),
            Menu.SEPARATOR,
            Item(lambda item: t("menu.record"), self.toggle_record,
                 checked=lambda item: config.settings()["capture"] != "off"),
            Item(lambda item: t("menu.open_viewer"), self.toggle_open,
                 checked=lambda item: config.settings()["open_viewer"]),
            Item(lambda item: t("menu.rec_folder"), self.open_folder(config.rec_dir)),
            Item(lambda item: t("menu.settings"), self.open_settings),
            Item(lambda item: t("menu.logs"), self.open_folder(config.ROOT / "logs")),
            Menu.SEPARATOR,
            Item(lambda item: t("menu.quit"), self.quit),
        )

    # ------------------------------------------------------------ start
    def setup(self, icon):
        icon.visible = True
        created = config.ensure_env()
        config.reload()
        first = created
        if config.settings()["source"] == "api":
            try:
                config.api_key()
            except config.ConfigError:
                first = True
        if first:
            self.notify(t("n.first_run"), t("n.first_run_msg"), important=True)
            self.open_settings()
        else:
            self.notify(APP, t("n.started"))
        self.worker = threading.Thread(target=self.recorder_loop, daemon=True)
        self.worker.start()

    def run(self):
        self.icon.run(setup=self.setup)


def selftest() -> int:
    """Build the viewer for the newest cached match (used to check a packaged build)."""
    from . import fetch, pipeline, recorder
    (config.ROOT / "logs").mkdir(exist_ok=True)
    out = config.ROOT / "logs" / "selftest.txt"
    try:
        recorder.check_ready()
        riot_id, puuid = pipeline.last_account()
        puuid = puuid or pipeline.puuid_for(riot_id)
        mid = next(m for m in fetch.cached_match_ids()
                   if pipeline.my_puuid(fetch.load_match(m)[0], puuid, riot_id))
        a, _ = pipeline.build(mid, puuid, riot_id=riot_id)
        out.write_text(f"OK {mid} {pipeline.viewer_path(mid).exists()} {a['focus']}", encoding="utf-8")
        return 0
    except Exception as e:
        out.write_text(f"FAIL {e!r}", encoding="utf-8")
        return 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--window" in sys.argv:
        from .window import run_window
        run_window(sys.argv[sys.argv.index("--window") + 1])
        return
    if "--settings" in sys.argv:
        from .settings_window import open_window
        open_window()
        return
    if not _single_instance():
        _message(t("n.already_running"))
        return
    TrayApp().run()
