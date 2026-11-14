import copy

from ascendinq import analyze, teamrate
from synthetic import ME_PUUID, build_match


def test_every_player_gets_a_grade():
    m, t = build_match()
    rows = teamrate.rate_players(m, t, m["info"]["gameDuration"])
    assert len(rows) == 10
    assert {r["grade"] for r in rows} <= set("SABCDF")
    assert all(0 <= r["score"] <= 100 for r in rows)
    # allies (team 100) first, ordered by role
    assert [r["team"] for r in rows] == [100] * 5 + [200] * 5
    assert rows[0]["role"] == "TOP"


def test_grade_thresholds():
    assert teamrate.grade_of(95) == "S"
    assert teamrate.grade_of(70) == "A"
    assert teamrate.grade_of(41) == "D"
    assert teamrate.grade_of(10) == "F"


def test_afk_player_is_flagged_and_capped():
    m, t = build_match()
    frames = t["info"]["frames"]
    for f in frames[3:12]:  # player 1 stands still for 9 minutes
        f["participantFrames"]["1"]["position"] = {"x": 500, "y": 500}
    rows = teamrate.rate_players(m, t, m["info"]["gameDuration"])
    afk = next(r for r in rows if r["pid"] == 1)
    assert "放置（AFK）の疑い" in afk["flags"]
    assert afk["grade"] == "F"


def test_feeding_player_is_flagged():
    m, t = build_match()
    m = copy.deepcopy(m)
    p = next(p for p in m["info"]["participants"] if p["participantId"] == 2)
    p.update(kills=0, deaths=12, assists=2)
    rows = teamrate.rate_players(m, t, m["info"]["gameDuration"])
    assert "ほぼ一方的に倒されている" in next(r for r in rows if r["pid"] == 2)["flags"]


def test_analysis_includes_ratings():
    m, t = build_match()
    a = analyze.analyze(m, t, ME_PUUID)
    assert len(a["players"]) == 10
    assert any(r["pid"] == a["me"]["pid"] for r in a["players"])


def test_solo_kills_and_tags():
    m, t = build_match()
    frames = t["info"]["frames"]
    # player 3 (MID, team 100) solo-kills the enemy MID (8) twice during laning
    for minute in (5, 8):
        frames[minute]["events"].append({"type": "CHAMPION_KILL", "timestamp": minute * 60000 + 1000,
                                         "killerId": 3, "victimId": 8, "assistingParticipantIds": [],
                                         "position": {"x": 7400, "y": 7400}})
    rows = teamrate.rate_players(m, t, m["info"]["gameDuration"])
    me, opp = next(r for r in rows if r["pid"] == 3), next(r for r in rows if r["pid"] == 8)
    assert me["lane_solo_kills"] >= 2 and me["solo_kills"] >= 2
    assert any(tag["good"] and tag["text"].startswith("ソロキル") for tag in me["tags"])
    assert opp["lane_solo_deaths"] >= 2
    assert any(not tag["good"] and "ソロキルされた" in tag["text"] for tag in opp["tags"])
    for r in rows:  # at most 4 good + 3 bad tags
        assert sum(t["good"] for t in r["tags"]) <= 4 and sum(not t["good"] for t in r["tags"]) <= 3
