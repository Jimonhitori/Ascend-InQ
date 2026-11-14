"""Data Dragon (champion / item names in Japanese). Cached under data/ddragon."""
import json

import requests

from . import config

BASE = "https://ddragon.leagueoflegends.com"
_cache = {}


def _fetch_json(name: str, lang: str = "ja_JP"):
    key = (name, lang)
    if key in _cache:
        return _cache[key]
    config.DDRAGON_DIR.mkdir(parents=True, exist_ok=True)
    data = None
    try:
        version = requests.get(f"{BASE}/api/versions.json", timeout=10).json()[0]
        path = config.DDRAGON_DIR / f"{version}_{lang}_{name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = requests.get(f"{BASE}/cdn/{version}/data/{lang}/{name}.json", timeout=20).json()["data"]
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except (requests.RequestException, ValueError, KeyError):
        cached = sorted(config.DDRAGON_DIR.glob(f"*_{lang}_{name}.json"))
        if cached:
            data = json.loads(cached[-1].read_text(encoding="utf-8"))
    _cache[key] = data or {}
    return _cache[key]


def champion_name(champ_id: str) -> str:
    data = _fetch_json("champion")
    if champ_id in data:
        return data[champ_id]["name"]
    for k, v in data.items():
        if k.lower() == champ_id.lower():
            return v["name"]
    return champ_id


def items() -> dict:
    return _fetch_json("item")


def item_name(item_id: int) -> str:
    it = items().get(str(item_id))
    return it["name"] if it else str(item_id)


def is_completed_item(item_id: int) -> str | None:
    """Return 'legendary' / 'boots' for completed items, else None."""
    it = items().get(str(item_id))
    if not it:
        return None
    gold = it.get("gold", {})
    if not gold.get("purchasable", False):
        return None
    tags = it.get("tags", [])
    if "Boots" in tags:
        return "boots" if it.get("from") and gold.get("total", 0) >= 900 else None
    if "Consumable" in tags or "Trinket" in tags:
        return None
    if not it.get("into") and it.get("from") and gold.get("total", 0) >= 2200:
        return "legendary"
    return None
