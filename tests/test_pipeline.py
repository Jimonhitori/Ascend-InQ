import json

from ascendinq import config, pipeline
from synthetic import ME_PUUID, ME_RIOT_ID, build_match


def test_my_puuid_direct_hit():
    m, _ = build_match(n_frames=3)
    assert pipeline.my_puuid(m, ME_PUUID, ME_RIOT_ID) == ME_PUUID


def test_my_puuid_falls_back_to_riot_id_name():
    m, _ = build_match(n_frames=3)
    assert pipeline.my_puuid(m, "api-encrypted-puuid", ME_RIOT_ID) == ME_PUUID


def test_my_puuid_uses_known_accounts_when_no_riot_id():
    m, _ = build_match(n_frames=3)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "accounts.json").write_text(
        json.dumps({"Someone#JP1": "x", ME_RIOT_ID: "y", "__last__": ME_RIOT_ID}), encoding="utf-8")
    assert pipeline.my_puuid(m, "api-encrypted-puuid") == ME_PUUID


def test_my_puuid_none_when_unknown():
    m, _ = build_match(n_frames=3)
    assert pipeline.my_puuid(m, "nope", "Nobody#JP1") is None
    assert pipeline.my_puuid(m, "nope") is None  # no accounts.json
