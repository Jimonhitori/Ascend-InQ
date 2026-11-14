"""Shared steps used by both the CLI and the tray app."""
import json
import threading
import time

from . import analyze, clips, config, fetch, report, viewer
from .riot import RiotClient


def client():
    config.reload()
    return RiotClient(config.api_key(), config.region(), config.platform(), config.account_region())


def puuid_for(riot_id):
    cache = config.DATA_DIR / "accounts.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if riot_id in data:
            return data[riot_id]
    return fetch.get_puuid(client(), riot_id)


def viewer_path(match_id):
    return config.REPORT_DIR / f"{match_id}_viewer.html"


def my_puuid(match, puuid, riot_id=None):
    """The same account has different PUUIDs in Riot API data (encrypted per key) and client data.
    Fall back to the Riot ID name when the given PUUID is not in this match."""
    parts = match["info"]["participants"]
    if any(p["puuid"] == puuid for p in parts):
        return puuid
    names = [riot_id.split("#")[0]] if riot_id else []
    if not names:  # unknown account: try every account this app has seen
        try:
            cache = json.loads((config.DATA_DIR / "accounts.json").read_text(encoding="utf-8"))
            names = [k.split("#")[0] for k in cache if not k.startswith("__")]
        except (OSError, ValueError):
            pass
    for n in names:
        hit = next((p["puuid"] for p in parts if p.get("riotIdGameName") == n), None)
        if hit:
            return hit
    return None


def build(match_id, puuid, video=None, offset=None, riot_id=None):
    m, t = fetch.load_match(match_id)
    a = analyze.analyze(m, t, my_puuid(m, puuid, riot_id) or puuid)
    if video is None:
        video = clips.find_video(a["game_start_ms"])
    viewer.build(a, m, t, video, offset)
    return a, report.write(a)


def refresh_index(riot_id, puuid):
    """Rebuild reports/index.html from all cached matches of this account."""
    analyses = []
    for mid in fetch.cached_match_ids()[:30]:
        try:
            m, t = fetch.load_match(mid)
            mine = my_puuid(m, puuid, riot_id)
            if mine:
                analyses.append(analyze.analyze(m, t, mine))
        except (ValueError, FileNotFoundError):
            continue
    if analyses:
        return report.write_index(analyses)
    return None


def _remember(riot_id, puuid):
    cache_path = config.DATA_DIR / "accounts.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    cache[riot_id] = puuid
    cache["__last__"] = riot_id
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def last_account():
    """(riot_id, puuid) of the account used most recently, if known."""
    try:
        cache = json.loads((config.DATA_DIR / "accounts.json").read_text(encoding="utf-8"))
        rid = cache.get("__last__") or config.riot_id()
        if rid not in cache:  # fall back to any known account
            rid = next((k for k in cache if not k.startswith("__")), rid)
        return rid, cache.get(rid)
    except (OSError, ValueError):
        return config.riot_id(), None


def _inject_items(m, t, puuid, snapshots):
    """Turn live inventory snapshots into ITEM_PURCHASED events (first time each item appears)."""
    me = next((p for p in m["info"]["participants"] if p["puuid"] == puuid), None)
    frames = t["info"]["frames"]
    if not me or not snapshots or not frames:
        return
    seen = set()
    for gt, ids in snapshots:
        for iid in ids:
            if iid and iid not in seen:
                seen.add(iid)
                ms = int(gt * 1000)
                idx = min(int(ms // 60000), len(frames) - 1)
                frames[idx]["events"].append({"type": "ITEM_PURCHASED", "timestamp": ms,
                                              "participantId": me["participantId"], "itemId": iid})


def _save_client_game(lcu_conn, game_id, game_start_ms=None, puuid=None, live_items=None):
    from .lcu import to_v5
    m, t = to_v5(lcu_conn.game(game_id), lcu_conn.timeline(game_id), game_start_ms)
    if live_items:
        _inject_items(m, t, puuid, live_items)
    mpath, tpath = fetch.match_paths(m["metadata"]["matchId"])
    fetch._save(mpath, m)
    fetch._save(tpath, t)
    return m["metadata"]["matchId"]


def import_recent(n=5, log=print):
    """Fetch the latest games from the configured source. Returns (riot_id, puuid, ids, new_ids)."""
    if config.settings()["source"] == "api":
        riot_id = config.riot_id()
        puuid, ids, new = fetch.fetch_recent(client(), riot_id, n)
        _remember(riot_id, puuid)
        return riot_id, puuid, ids, new
    from .lcu import LCU
    conn = LCU.connect()
    me = conn.me()
    _remember(me["riot_id"], me["puuid"])
    ids, new = [], []
    platform = conn.platform().upper()
    for g in conn.recent_games(me["puuid"], max(20, n))[:n]:
        mid = f"{(g.get('platformId') or platform).upper()}_{g['gameId']}"
        mpath, tpath = fetch.match_paths(mid)
        if not (mpath.exists() and tpath.exists()):
            log(f"取得中: {mid}")
            mid = _save_client_game(conn, g["gameId"])
            new.append(mid)
        ids.append(mid)
    return me["riot_id"], me["puuid"], ids, new


def review_after_game(video, info, default_id, log=print, stop: threading.Event | None = None):
    """Wait for the finished game to appear in the data source, then build its viewer.
    Returns (analysis, viewer_path) or (None, None)."""
    def wait(sec):
        if stop is not None:
            return stop.wait(sec)
        time.sleep(sec)
        return False

    start = info["start_epoch"]
    clock_zero_ms = int((start - (info.get("offset") or 0)) * 1000)

    if config.settings()["source"] != "api":
        from .lcu import LCU, ClientNotRunning
        log("LoL クライアントから試合データを読み込みます…")
        for attempt in range(20):
            if wait(15 if attempt == 0 else 30):
                return None, None
            try:
                conn = LCU.connect()
                me = conn.me()
                game = next((g for g in conn.recent_games(me["puuid"], 5)
                             if start - 1800 <= g.get("gameCreation", 0) / 1000 <= start + 60), None)
                if not game:
                    continue
                mid = _save_client_game(conn, game["gameId"], clock_zero_ms, me["puuid"], info.get("items"))
            except ClientNotRunning as e:
                log(str(e))
                continue
            _remember(me["riot_id"], me["puuid"])
            a, _ = build(mid, me["puuid"], video)
            refresh_index(me["riot_id"], me["puuid"])
            return a, viewer_path(mid)
        log("クライアントに試合が見つかりませんでした（サモナーズリフト以外の試合は録画だけ残します）。")
        return None, None

    player = info.get("player") or ""
    riot_id = player if "#" in player else default_id
    if not riot_id:
        log("設定に Riot ID が無いため、試合データを取得できません。")
        return None, None
    cl = client()
    log(f"{riot_id} の試合データがAPIに出るのを待っています…")
    for attempt in range(12):
        if wait(30 if attempt == 0 else 60):
            return None, None
        puuid, ids, _ = fetch.fetch_recent(cl, riot_id, 1)
        if not ids:
            continue
        m, _ = fetch.load_match(ids[0])
        gstart = m["info"].get("gameStartTimestamp", 0) / 1000
        if abs(gstart - start) < 600:
            _remember(riot_id, puuid)
            a, _ = build(ids[0], puuid, video)
            refresh_index(riot_id, puuid)
            return a, viewer_path(ids[0])
    log("ソロランクの試合が見つかりませんでした（ノーマル等の試合は録画だけ残します）。")
    return None, None


def latest_viewer():
    for mid in fetch.cached_match_ids():
        p = viewer_path(mid)
        if p.exists():
            return p
    return None
