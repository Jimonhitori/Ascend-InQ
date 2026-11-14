"""Step 1: Riot ID -> PUUID -> recent solo-queue matches -> data/matches/*.json."""
import json

from . import config
from .riot import RiotClient


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def get_puuid(client: RiotClient, riot_id: str) -> str:
    if not riot_id:
        raise ValueError(".env の RIOT_ID に自分の Riot ID（例: Name#JP1）を書くか、--id で指定してください。")
    if "#" not in riot_id:
        raise ValueError(f"Riot ID は 名前#タグ の形で指定してください: {riot_id}")
    cache_path = config.DATA_DIR / "accounts.json"
    cache = _load(cache_path) if cache_path.exists() else {}
    if riot_id in cache:
        return cache[riot_id]
    name, tag = riot_id.split("#", 1)
    puuid = client.account_by_riot_id(name, tag)["puuid"]
    cache[riot_id] = puuid
    _save(cache_path, cache)
    return puuid


def match_paths(match_id: str):
    return (config.MATCH_DIR / f"{match_id}.json",
            config.MATCH_DIR / f"{match_id}_timeline.json")


def fetch_recent(client: RiotClient, riot_id: str, count: int = 5):
    """Download the latest `count` ranked solo matches. Returns (puuid, [match_id], [new ids])."""
    puuid = get_puuid(client, riot_id)
    ids = client.match_ids(puuid, queue=420, count=count)
    new = []
    for mid in ids:
        mpath, tpath = match_paths(mid)
        if mpath.exists() and tpath.exists():
            continue
        print(f"  取得中: {mid}")
        _save(mpath, client.match(mid))
        _save(tpath, client.timeline(mid))
        new.append(mid)
    return puuid, ids, new


def load_match(match_id: str):
    mpath, tpath = match_paths(match_id)
    if not mpath.exists() or not tpath.exists():
        raise FileNotFoundError(f"{match_id} のデータがありません。先に fetch してください。")
    return _load(mpath), _load(tpath)


def cached_match_ids():
    if not config.MATCH_DIR.exists():
        return []
    ids = [p.stem for p in config.MATCH_DIR.glob("*.json") if not p.stem.endswith("_timeline")]
    return sorted(ids, key=lambda m: int(m.split("_")[-1]), reverse=True)
