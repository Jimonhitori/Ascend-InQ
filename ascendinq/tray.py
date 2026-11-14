"""Ascend InQ tray app: sits in the notification area while you play LoL.

Start it when you want to play, quit it from the tray menu when you're done.
"""
import ctypes
import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading

import pystray

from . import config, fetch, pipeline, recorder
from .icon import make_icon

APP = "Ascend InQ"
STATE_LABEL = {
    "starting": "起動中…",
    "waiting": "待機中（試合が始まると自動で録画）",
    "recording": "● 録画中",
    "processing": "試合データを分析中…",
    "paused": "録画オフ",
    "error": "エラー（ログを確認）",
    "stopped": "停止",
}
SETTINGS = config.DATA_DIR / "app.json"


def _single_instance() -> bool:
    if sys.platform != "win32":
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "AscendInQ_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def _message(text):
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, APP, 0x40)


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
        self.settings = {"record": True, "open_viewer": True}
        try:
            self.settings.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.icon = pystray.Icon("AscendInQ", make_icon("starting"), APP, menu=self._menu())
        self.worker = None

    # ------------------------------------------------------------ helpers
    def log(self, msg):
        self.logger.info(msg)

    def notify(self, title, msg):
        self.log(f"{title}: {msg}")
        try:
            self.icon.notify(msg, title)
        except Exception:
            pass

    def save_settings(self):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(self.settings), encoding="utf-8")

    def set_state(self, s):
        if s == self.state:
            return
        self.state = s
        self.icon.icon = make_icon(s)
        self.icon.title = f"{APP} — {STATE_LABEL.get(s, s)}"
        self.icon.update_menu()
        if s == "recording":
            self.notify("録画を開始しました", "試合が終わると自動で止まります。")

    def background(self, fn):
        threading.Thread(target=self._guard(fn), daemon=True).start()

    def _guard(self, fn):
        def run():
            try:
                fn()
            except Exception as e:
                self.notify("エラー", str(e)[:200])
        return run

    # ------------------------------------------------------------ recorder
    def after_game(self, video, info):
        self.notify("録画を保存しました", "試合データがRiot APIに出たら分析します（1〜数分）。")
        a, path = pipeline.review_after_game(video, info, config.riot_id(), self.log, self.stop)
        if a:
            self.notify("振り返りの準備ができました", "次の試合で意識すること: " + a["focus"])
            if self.settings["open_viewer"]:
                os.startfile(path)

    def recorder_loop(self):
        try:
            recorder.run(self.after_game, stop=self.stop, enabled=lambda: self.settings["record"],
                         log=self.log, on_state=self.set_state)
        except RuntimeError as e:
            self.set_state("error")
            self.notify("録画を開始できません", str(e))

    # ------------------------------------------------------------ menu actions
    def toggle_record(self, icon, item):
        self.settings["record"] = not self.settings["record"]
        self.save_settings()
        icon.update_menu()

    def toggle_open(self, icon, item):
        self.settings["open_viewer"] = not self.settings["open_viewer"]
        self.save_settings()

    def open_latest(self, icon=None, item=None):
        p = pipeline.latest_viewer()
        if p:
            os.startfile(p)
        else:
            self.notify("まだ試合がありません", "「直近の試合を取り込む」を実行するか、1試合プレイしてください。")

    def open_index(self, icon=None, item=None):
        p = config.REPORT_DIR / "index.html"
        if p.exists():
            os.startfile(p)
        else:
            self.import_recent()

    def import_recent(self, icon=None, item=None):
        def work():
            riot_id = config.riot_id() if config.riot_id() != "Name#JP1" else ""
            if not riot_id:
                raise RuntimeError("設定（.env）の RIOT_ID に自分の Riot ID を書いてください。")
            self.notify("取り込み中", f"{riot_id} の直近5試合を取得しています…")
            puuid, ids, new = fetch.fetch_recent(pipeline.client(), riot_id, 5)
            for mid in ids:
                pipeline.build(mid, puuid)
            idx = pipeline.refresh_index(riot_id, puuid)
            self.notify("取り込み完了", f"新しく {len(new)} 試合を取り込みました。")
            if idx:
                os.startfile(idx)
        self.background(work)

    def open_folder(self, path):
        def action(icon=None, item=None):
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        return action

    def open_settings(self, icon=None, item=None):
        config.ensure_env()
        subprocess.Popen(["notepad.exe", str(config.ENV_PATH)])

    def quit(self, icon, item):
        self.stop.set()
        if self.state == "recording":
            self.notify("終了中", "録画を保存してから終了します…")
        if self.worker:
            self.worker.join(timeout=40)
        icon.stop()

    def _menu(self):
        Item, Menu = pystray.MenuItem, pystray.Menu
        return Menu(
            Item(lambda item: STATE_LABEL.get(self.state, self.state), None, enabled=False),
            Menu.SEPARATOR,
            Item("最新の試合を見る", self.open_latest, default=True),
            Item("試合一覧を開く", self.open_index),
            Item("直近の試合を取り込む", self.import_recent),
            Menu.SEPARATOR,
            Item("自動録画", self.toggle_record, checked=lambda item: self.settings["record"]),
            Item("試合後にビューアを開く", self.toggle_open, checked=lambda item: self.settings["open_viewer"]),
            Item("録画フォルダを開く", self.open_folder(config.REC_DIR)),
            Item("設定（APIキー・Riot ID）", self.open_settings),
            Item("ログを開く", self.open_folder(config.ROOT / "logs")),
            Menu.SEPARATOR,
            Item("終了", self.quit),
        )

    # ------------------------------------------------------------ start
    def setup(self, icon):
        icon.visible = True
        created = config.ensure_env()
        config.reload()
        try:
            config.api_key()
            first = created
        except config.ConfigError:
            first = True
        if first:
            self.notify("初期設定", "メモ帳で開いた設定に、Riot APIキーと自分のRiot IDを書いて保存してください。")
            self.open_settings()
        else:
            self.notify(APP, "起動しました。LoLの試合が始まると自動で録画します。")
        self.worker = threading.Thread(target=self.recorder_loop, daemon=True)
        self.worker.start()

    def run(self):
        self.icon.run(setup=self.setup)


def selftest() -> int:
    """Build the viewer for the newest cached match (used to check a packaged build)."""
    (config.ROOT / "logs").mkdir(exist_ok=True)
    out = config.ROOT / "logs" / "selftest.txt"
    try:
        recorder.check_ready()
        riot_id = config.riot_id()
        puuid = pipeline.puuid_for(riot_id)
        mid = next(m for m in fetch.cached_match_ids()
                   if any(p["puuid"] == puuid for p in fetch.load_match(m)[0]["info"]["participants"]))
        a, _ = pipeline.build(mid, puuid)
        out.write_text(f"OK {mid} {pipeline.viewer_path(mid).exists()} {a['focus']}", encoding="utf-8")
        return 0
    except Exception as e:
        out.write_text(f"FAIL {e!r}", encoding="utf-8")
        return 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if not _single_instance():
        _message("Ascend InQ はすでに起動しています。画面右下のタスクトレイ（^ の中）を確認してください。")
        return
    TrayApp().run()
