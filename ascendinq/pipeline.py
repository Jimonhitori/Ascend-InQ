"""Shared steps used by both the CLI and the tray app."""
import json
import threading
import time

from . import analyze, clips, config, fetch, report, viewer
from .riot import RiotClient


def client():
    config.reload()
    return RiotClient(config.api_key(), config.region(), config.platform())


def puuid_for(riot_id):
    cache = config.DATA_DIR / "accounts.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if riot_id in data:
            return data[riot_id]
    return fetch.get_puuid(client(), riot_id)


def viewer_path(match_id):
    return config.REPORT_DIR / f"{match_id}_viewer.html"


def build(match_id, puuid, video=None, offset=None):
    m, t = fetch.load_match(match_id)
    a = analyze.analyze(m, t, puuid)
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
            if any(p["puuid"] == puuid for p in m["info"]["participants"]):
                analyses.append(analyze.analyze(m, t, puuid))
        except (ValueError, FileNotFoundError):
            continue
    if analyses:
        return report.write_index(analyses)
    return None


def review_after_game(video, info, default_id, log=print, stop: threading.Event | None = None):
    """Wait for the finished game to appear in the Riot API, then build its viewer.
    Returns (analysis, viewer_path) or (None, None)."""
    player = info.get("player") or ""
    riot_id = player if "#" in player else default_id
    if not riot_id:
        log(".env に RIOT_ID が無いため、試合データを取得できません。")
        return None, None
    cl = client()
    log(f"{riot_id} の試合データがAPIに出るのを待っています…")
    for attempt in range(12):
        wait = 30 if attempt == 0 else 60
        if stop is not None:
            if stop.wait(wait):
                return None, None
        else:
            time.sleep(wait)
        puuid, ids, _ = fetch.fetch_recent(cl, riot_id, 1)
        if not ids:
            continue
        m, _ = fetch.load_match(ids[0])
        start = m["info"].get("gameStartTimestamp", 0) / 1000
        if abs(start - info["start_epoch"]) < 600:
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
