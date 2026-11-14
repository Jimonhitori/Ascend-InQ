import pytest

from ascendinq import analyze
from synthetic import ME_PUUID, build_match


@pytest.fixture
def result():
    m, t = build_match()
    return analyze.analyze(m, t, ME_PUUID)


def test_basic_identity(result):
    assert result["match_id"] == "JP1_1000000001"
    assert result["me"]["role"] == "MIDDLE"
    assert result["me"]["champ_ja"] == "アニビア"
    assert result["opp"]["pid"] == 8
    assert result["enemy_jg"]["pid"] == 7
    assert result["remake"] is False
    assert result["duration"] == 28 * 60


def test_unknown_puuid_raises():
    m, t = build_match()
    with pytest.raises(ValueError):
        analyze.analyze(m, t, "puuid-not-in-match")


def test_deaths(result):
    deaths = result["deaths"]
    assert len(deaths) == 3
    assert [d["t"] for d in deaths] == [330, 720, 1320]
    gank, solo, late = deaths
    assert gank["jg_involved"] is True
    assert gank["n_enemies"] == 2
    assert gank["zone"] == "MIDレーン(敵側)"
    assert solo["jg_involved"] is False
    assert solo["killer_is_opp"] is True
    assert solo["n_enemies"] == 1
    assert late["n_enemies"] == 3
    assert late["allies_near"] == []
    assert late["zone"].startswith("リバー")
    # ward data is present in this timeline
    assert gank["my_wards_3min"] == 2
    assert isinstance(late["my_wards_3min"], int)


def test_grubs_merge_into_one_objective(result):
    grubs = [o for o in result["objectives"] if o["kind"] == "HORDE"]
    assert len(grubs) == 1
    assert grubs[0]["count"] == 3
    assert grubs[0]["name"] == "ヴォイドグラブ×3"
    assert grubs[0]["ours"] is False
    names = [o["name"] for o in result["objectives"]]
    assert "インファーナルドラゴン" in names
    assert "オーシャンドラゴン" in names


def test_grubs_far_apart_are_separate():
    m, t = build_match()
    # move the third grub 3 minutes later -> it must not merge into the first group
    for f in t["info"]["frames"]:
        for e in f["events"]:
            if e.get("monsterType") == "HORDE" and e["timestamp"] == 420_000:
                e["timestamp"] = 600_000
    a = analyze.analyze(m, t, ME_PUUID)
    grubs = [o for o in a["objectives"] if o["kind"] == "HORDE"]
    assert [g["count"] for g in grubs] == [2, 1]


def test_lane_rows(result):
    lane = {r["min"]: r for r in result["lane"]}
    assert set(lane) == {10, 15}
    assert lane[10]["cs"] == 60
    assert lane[10]["cs_opp"] == 70
    assert lane[15]["gold"] == 500 + 350 * 15
    assert lane[15]["gold_opp"] == 500 + 370 * 15
    assert lane[10]["level"] == 6


def test_towers_plates_items(result):
    assert len(result["towers"]) == 1
    tw = result["towers"][0]
    assert tw["ours"] is True and tw["lane"] == "MID" and tw["tier"] == "1st" and tw["involved"] is True
    assert result["mid_plates"] == {"ours": 1, "theirs": 0}
    # 3157 was undone, 1056 is not a completed item
    assert [(i["id"], i["kind"]) for i in result["items"]] == [(3020, "boots"), (3089, "legendary")]
    assert result["items"][1]["t"] == 900
    assert result["data_missing"] == []


def test_issues_sorted_and_focus(result):
    issues = result["issues"]
    assert issues
    scores = [i["score"] for i in issues]
    assert scores == sorted(scores, reverse=True)
    titles = [i["title"] for i in issues]
    assert "序盤の敵JGのガンクで倒されている" in titles
    assert "対面との1v1で倒されている" in titles
    assert any("CS" in t for t in titles)
    assert "コントロールワードを1つも買っていない" in titles
    assert result["focus"] == issues[0]["focus"]
    assert result["focus"]


def test_remake_by_duration():
    m, t = build_match(n_frames=5, duration=300)
    a = analyze.analyze(m, t, ME_PUUID)
    assert a["remake"] is True
    assert a["issues"] == [] and a["good"] == []
    assert "リメイク" in a["focus"]


def test_remake_by_flag():
    m, t = build_match(remake_flag=True)
    a = analyze.analyze(m, t, ME_PUUID)
    assert a["remake"] is True
    assert a["issues"] == []


def test_no_ward_events():
    m, t = build_match(wards=False)
    a = analyze.analyze(m, t, ME_PUUID)
    assert a["deaths"]
    assert all(d["my_wards_3min"] is None for d in a["deaths"])
    assert "wards" in a["data_missing"]


def test_no_item_events_uses_final_build():
    m, t = build_match(items=False)
    a = analyze.analyze(m, t, ME_PUUID)
    assert "items" in a["data_missing"]
    assert a["items"]
    assert all(i["t"] is None for i in a["items"])
    assert {i["id"] for i in a["items"]} == {3089, 3020}


def test_mmss():
    assert analyze.mmss(0) == "0:00"
    assert analyze.mmss(65.9) == "1:05"
    assert analyze.mmss(-3) == "0:00"
