"""UI text in Japanese and English.

Language comes from settings ("auto" follows the Windows display language).
Match analysis / advice text is currently Japanese only.
"""
import sys

from . import config

T = {
    # ---- tray: states
    "state.starting": ("起動中…", "Starting…"),
    "state.waiting": ("待機中（試合が始まると自動で録画）", "Waiting (records automatically when a game starts)"),
    "state.recording": ("● 録画中", "● Recording"),
    "state.processing": ("試合データを分析中…", "Analyzing the game…"),
    "state.paused": ("録画オフ", "Recording off"),
    "state.error": ("エラー（ログを確認）", "Error (see log)"),
    "state.stopped": ("停止", "Stopped"),
    # ---- tray: menu
    "menu.latest": ("最新の試合を見る", "Open latest game"),
    "menu.index": ("試合一覧を開く", "Open game list"),
    "menu.import": ("直近の試合を取り込む", "Import recent games"),
    "menu.record": ("自動録画", "Auto recording"),
    "menu.open_viewer": ("試合後にビューアを開く", "Open viewer after games"),
    "menu.rec_folder": ("録画フォルダを開く", "Open recordings folder"),
    "menu.settings": ("設定…", "Settings…"),
    "menu.logs": ("ログを開く", "Open logs"),
    "menu.quit": ("終了", "Quit"),
    # ---- tray: notifications
    "n.started": ("起動しました。LoLの試合が始まると自動で録画します。", "Running. Games are recorded automatically."),
    "n.first_run": ("初期設定", "First-time setup"),
    "n.first_run_msg": ("設定画面を開きました。録画の保存先などを確認して保存してください。",
                        "Settings opened. Check the recording folder etc. and press Save."),
    "n.rec_started": ("録画を開始しました", "Recording started"),
    "n.rec_started_msg": ("試合が終わると自動で止まります。", "It stops automatically when the game ends."),
    "n.saved": ("録画を保存しました", "Recording saved"),
    "n.saved_msg": ("試合データを読み込んで分析します（1〜数分）。", "Loading the game data for analysis (1–few min)."),
    "n.ready": ("振り返りの準備ができました", "Your review is ready"),
    "n.focus": ("次の試合で意識すること: ", "Focus for next game: "),
    "n.no_games": ("まだ試合がありません", "No games yet"),
    "n.no_games_msg": ("「直近の試合を取り込む」を実行するか、1試合プレイしてください。",
                       "Use “Import recent games” or play a game first."),
    "n.importing": ("取り込み中", "Importing"),
    "n.importing_msg": ("直近5試合を読み込んでいます…", "Loading your last 5 games…"),
    "n.imported": ("取り込み完了", "Import finished"),
    "n.imported_msg": ("{rid}: 新しく {n} 試合を取り込みました。", "{rid}: imported {n} new game(s)."),
    "n.need_riot_id": ("設定画面で自分の Riot ID を入力してください。", "Enter your Riot ID in Settings."),
    "n.error": ("エラー", "Error"),
    "n.cannot_record": ("録画を開始できません", "Cannot start recording"),
    "n.quitting": ("終了中", "Quitting"),
    "n.quitting_msg": ("録画を保存してから終了します…", "Saving the recording before quitting…"),
    "n.already_running": ("Ascend InQ はすでに起動しています。画面右下のタスクトレイ（^ の中）を確認してください。",
                          "Ascend InQ is already running. Look in the system tray (bottom right, under ^)."),
    "n.fullscreen": ("LoL がフルスクリーン設定です", "LoL is set to fullscreen"),
    "n.fullscreen_msg": ("フルスクリーンだと録画が真っ黒になることがあります。LoLの設定 → ビデオ → ウィンドウモードを「ボーダーレス」にしてください。",
                         "Fullscreen may record a black screen. In LoL: Settings → Video → Window Mode → Borderless."),
    "n.black": ("録画が真っ黒です", "The recording is black"),
    "n.low_disk": ("録画できません", "Cannot record"),
    "n.low_disk_msg": ("保存先の空き容量が {free:.1f} GB しかありません（{need} GB 以上必要）。古い録画を消すか、設定で保存先を変えてください。",
                       "Only {free:.1f} GB free in the recording folder ({need} GB needed). Delete old recordings or change the folder in Settings."),
    "n.disk_stop": ("録画を停止しました", "Recording stopped"),
    "n.disk_stop_msg": ("保存先の空き容量が少なくなったため、録画を止めました。", "Stopped because the disk is almost full."),
    # ---- ffmpeg setup
    "ff.ask": ("録画に必要な ffmpeg（無料の動画ツール、約{mb}MB）が見つかりません。\n今ダウンロードしますか？\n\n入手元: github.com/BtbN/FFmpeg-Builds",
               "ffmpeg (free video tool, about {mb} MB) is required for recording but was not found.\nDownload it now?\n\nSource: github.com/BtbN/FFmpeg-Builds"),
    "ff.downloading": ("ffmpeg をダウンロード中", "Downloading ffmpeg"),
    "ff.progress": ("{pct}% 完了", "{pct}% done"),
    "ff.done": ("ffmpeg の準備ができました", "ffmpeg is ready"),
    "ff.skipped": ("ffmpeg が無いため録画はオフです。試合データの分析は使えます。",
                   "Recording is off because ffmpeg is missing. Game analysis still works."),
    # ---- settings window
    "s.title": ("Ascend InQ — 設定", "Ascend InQ — Settings"),
    "s.heading": ("設定", "Settings"),
    "s.save": ("保存", "Save"),
    "s.cancel": ("キャンセル", "Cancel"),
    "s.saved": ("保存しました", "Saved"),
    "s.language": ("言語 / Language", "Language / 言語"),
    "s.lang_auto": ("自動（Windowsに合わせる）", "Auto (follow Windows)"),
    "s.data": ("試合データ", "Game data"),
    "s.data_sub": ("試合後の分析に使うデータの取り方", "Where post-game data comes from"),
    "s.src_client": ("LoL クライアントから", "From the LoL client"),
    "s.src_client_sub": ("おすすめ。APIキー不要。ログイン中のアカウントの試合を読みます",
                         "Recommended. No API key. Reads games of the logged-in account"),
    "s.src_api": ("Riot APIキー", "Riot API key"),
    "s.src_api_sub": ("上級者向け。開発者サイトで発行したキーで、どのアカウントの試合も取得",
                      "Advanced. Use a developer key to fetch any account's games"),
    "s.api_key": ("Riot APIキー", "Riot API key"),
    "s.api_key_sub": ("開発用キーは24時間で失効します", "Development keys expire after 24 hours"),
    "s.show": ("表示", "Show"),
    "s.get_key": ("→ developer.riotgames.com でキーを発行する", "→ Get a key at developer.riotgames.com"),
    "s.riot_id_sub": ("例: Name#JP1（名前#タグ）", "e.g. Name#EUW (name#tag)"),
    "s.server": ("サーバー", "Server"),
    "s.rec": ("録画", "Recording"),
    "s.rec_sub": ("LoLの試合中だけ、GPUで軽く録画します。画面全体を録画するので、試合中に切り替えた他のウィンドウも映ります",
                  "Records only during LoL games, using the GPU. The whole screen is captured, including other windows you switch to"),
    "s.cap_match": ("試合全体", "Full match"),
    "s.cap_match_sub": ("試合が始まったら自動で録画し、終わったら止める", "Start when a game starts, stop when it ends"),
    "s.cap_off": ("録画しない", "Don't record"),
    "s.cap_off_sub": ("録画はせず、試合データの分析だけ行う", "No video, game analysis only"),
    "s.folder": ("保存先", "Save to"),
    "s.browse": ("参照…", "Browse…"),
    "s.keep": ("残す録画の数", "Recordings to keep"),
    "s.keep_sub": ("超えたら古い録画から自動で削除します（1試合 約1GB）", "Older recordings are deleted automatically (≈1 GB per game)"),
    "s.unlimited": ("無制限", "Unlimited"),
    "s.quality": ("画質", "Quality"),
    "s.quality_sub": ("高画質ほどファイルが大きくなります", "Higher quality means bigger files"),
    "q.high": ("高画質", "High"), "q.standard": ("標準", "Standard"), "q.light": ("軽量", "Light"),
    "s.fps": ("フレームレート", "Frame rate"),
    "s.monitor": ("録画するモニター", "Monitor"),
    "s.monitor_n": ("モニター{n}", "Monitor {n}"),
    "s.main": ("（メイン）", " (main)"),
    "s.cursor": ("マウスカーソルを録画", "Record mouse cursor"),
    "s.after": ("試合後", "After the game"),
    "s.auto_review": ("試合データを自動で分析", "Analyze games automatically"),
    "s.auto_review_sub": ("試合が終わったら試合データを読み込んで、解説を作ります", "Load the game data and build the review when a game ends"),
    "s.open_viewer": ("ビューアを自動で開く", "Open the viewer automatically"),
    "s.general": ("一般", "General"),
    "s.autostart": ("PC起動時に Ascend InQ を起動", "Start Ascend InQ with Windows"),
    "s.autostart_sub": ("オフのときは、LoLをやる前に自分で起動してください", "If off, start it yourself before playing"),
    "s.notify": ("通知を表示", "Show notifications"),
    "s.notify_sub": ("録画の開始・振り返りの準備完了などをお知らせします", "Recording started, review ready, etc."),
    "s.err_riot_id": ("Riot ID は「名前#タグ」の形で入力してください", "Enter the Riot ID as name#tag"),
    "s.err_autostart": ("自動起動の設定に失敗: {e}", "Could not change start-with-Windows: {e}"),
}


def lang() -> str:
    pref = config.settings().get("language", "auto")
    if pref in ("ja", "en"):
        return pref
    if sys.platform == "win32":
        try:
            import ctypes
            return "ja" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x11 else "en"
        except Exception:
            pass
    return "ja"


def t(key: str, **kw) -> str:
    ja, en = T.get(key, (key, key))
    s = en if lang() == "en" else ja
    return s.format(**kw) if kw else s
