import pytest

from ascendinq import analyze, lcu
from synthetic import ME_PID, build_client_game, pid_info

EXPECTED_ROLES = {pid: pid_info(pid)[1] for pid in range(1, 11)}


@pytest.fixture(autouse=True)
def no_replay(monkeypatch):
    monkeypatch.setattr(lcu, "rofl_positions", lambda platform, gid: {})


def test_infer_roles_from_positions():
    game, tl = build_client_game()
    frames = tl["frames"]
    for f in frames:
        f["participantFrames"] = {str(k): v for k, v in f["participantFrames"].items()}
    assert lcu.infer_roles(game["participants"], frames) == EXPECTED_ROLES


def test_to_v5_shape():
    game, tl = build_client_game()
    m, t = lcu.to_v5(game, tl, game_start_ms=123)
    assert m["metadata"]["matchId"] == "JP1_2000000002"
    assert m["metadata"]["source"] == "client"
    assert t["metadata"]["matchId"] == "JP1_2000000002"
    info = m["info"]
    assert info["gameStartTimestamp"] == 123
    assert len(info["participants"]) == 10
    p3 = next(p for p in info["participants"] if p["participantId"] == ME_PID)
    assert p3["championName"] == "Anivia"
    assert p3["puuid"] == "client-puuid-0003"
    assert p3["riotIdGameName"] == "Tester"
    assert p3["item0"] == 3089 and p3["item6"] == 3340
    assert {p["participantId"]: p["teamPosition"] for p in info["participants"]} == EXPECTED_ROLES
    # frame keys normalised to strings
    assert all(isinstance(k, str) for f in t["info"]["frames"] for k in f["participantFrames"])


def test_to_v5_fills_killer_team():
    game, tl = build_client_game()
    _m, t = lcu.to_v5(game, tl)
    elite = [e for f in t["info"]["frames"] for e in f["events"] if e["type"] == "ELITE_MONSTER_KILL"]
    assert {e["monsterType"]: e["killerTeamId"] for e in elite} == {"HORDE": 200, "DRAGON": 100}


def test_to_v5_default_start_and_platform():
    game, tl = build_client_game()
    game["platformId"] = "jp1"
    m, _ = lcu.to_v5(game, tl)
    assert m["metadata"]["matchId"] == "JP1_2000000002"
    assert m["info"]["gameStartTimestamp"] == game["gameCreation"]


def test_rofl_roles_override_inference(monkeypatch):
    monkeypatch.setattr(lcu, "rofl_positions",
                        lambda platform, gid: {"client-puuid-0001": "UTILITY", "client-puuid-0005": "TOP"})
    game, tl = build_client_game()
    m, _ = lcu.to_v5(game, tl)
    roles = {p["participantId"]: p["teamPosition"] for p in m["info"]["participants"]}
    assert roles[1] == "UTILITY"
    assert roles[5] == "TOP"
    assert roles[3] == "MIDDLE"  # untouched players keep the inferred role


def test_client_data_feeds_analyzer():
    """Client timelines have no ward/item events: analyzer must degrade gracefully."""
    game, tl = build_client_game()
    m, t = lcu.to_v5(game, tl)
    a = analyze.analyze(m, t, "client-puuid-0003")
    assert a["me"]["role"] == "MIDDLE"
    assert set(a["data_missing"]) == {"wards", "items", "plates"}
    assert all(i["t"] is None for i in a["items"])
    assert a["mid_plates"] is None
