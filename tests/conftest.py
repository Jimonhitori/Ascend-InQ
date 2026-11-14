"""Shared fixtures: offline Data Dragon and redirected user-data paths.

Tests never touch the network, the League client, ffmpeg, or the real
.env / settings.json / data / reports folders of the repository.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
for p in (str(ROOT), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from ascendinq import config, ddragon  # noqa: E402
import synthetic  # noqa: E402

# ---------------------------------------------------------------- fake Data Dragon

FAKE_ITEMS = {
    # completed legendary: built from components, builds into nothing, >= 2200g
    "3089": {"name": "テスト帽子", "gold": {"purchasable": True, "total": 3600},
             "from": ["1058", "1026"], "tags": ["SpellDamage"]},
    "3157": {"name": "テスト砂時計", "gold": {"purchasable": True, "total": 3250},
             "from": ["3191", "1058"], "tags": ["SpellDamage", "Armor"]},
    # completed boots
    "3020": {"name": "テストシューズ", "gold": {"purchasable": True, "total": 1100},
             "from": ["1001"], "tags": ["Boots"]},
    # starter / component / consumable: not "completed"
    "1056": {"name": "テストリング", "gold": {"purchasable": True, "total": 400}, "tags": ["Lane"]},
    "1058": {"name": "テスト杖", "gold": {"purchasable": True, "total": 1250},
             "into": ["3089"], "tags": ["SpellDamage"]},
    "2055": {"name": "テストワード", "gold": {"purchasable": True, "total": 75}, "tags": ["Consumable"]},
}


def _fake_champions(lang):
    out = {}
    for champ_id, key, ja in synthetic.CHAMPIONS:
        out[champ_id] = {"key": str(key), "name": ja if lang == "ja_JP" else champ_id}
    return out


def fake_fetch_json(name, lang="ja_JP"):
    if name == "champion":
        return _fake_champions(lang)
    if name == "item":
        return FAKE_ITEMS
    return {}


@pytest.fixture(autouse=True)
def offline_ddragon(monkeypatch):
    monkeypatch.setattr(ddragon, "_cache", {})
    monkeypatch.setattr(ddragon, "_fetch_json", fake_fetch_json)


@pytest.fixture(autouse=True)
def isolated_paths(monkeypatch, tmp_path):
    """Point every user-data path at a temp dir so real files are never read or written."""
    data = tmp_path / "data"
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "RESOURCES", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MATCH_DIR", data / "matches")
    monkeypatch.setattr(config, "DDRAGON_DIR", data / "ddragon")
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(config, "CLIP_DIR", tmp_path / "clips")
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")
    # write_env() calls reload(), which would push .env keys into os.environ
    monkeypatch.setattr(config, "reload", lambda: None)
    return tmp_path
