"""Death cause classification (deaths.py)."""
from ascendinq import deaths


def base(**kw):
    d = {"t": 20 * 60, "zone": "MIDレーン(中央)", "allies_near": [], "n_enemies": 1, "jg_involved": False,
         "ejg_zone_20s": "?", "killer": "敵", "killer_is_opp": False, "level": 10, "opp_level": 10,
         "killer_level": 10, "lane_gold_diff": 0, "killer_gold_diff": 0, "my_wards_3min": None,
         "lost_after": [], "bounty": 0, "fight": {"allies_dead_before": 0, "enemies_dead": 0, "first": True}}
    d.update(kw)
    return d


def primary(d, role="MIDDLE"):
    return deaths.classify(d, role, "敵JG")["primary"]["key"]


def test_gank_beats_everything_early():
    assert primary(base(t=300, jg_involved=True, n_enemies=2, zone="MIDレーン(敵側)")) == "gank"
    assert primary(base(t=300, jg_involved=True, n_enemies=2), role="JUNGLE") == "jg_duel"


def test_low_hp_needs_live_data():
    assert primary(base(hp_before=0.2)) == "low_hp"
    assert primary(base(hp_before=None)) != "low_hp"


def test_one_v_one_uses_killer_level():
    c = deaths.classify(base(killer_level=12, level=10), "MIDDLE", None)["primary"]
    assert c["key"] == "bad_trade" and "12" in c["why"]


def test_outnumbered_two_v_one():
    assert primary(base(n_enemies=2)) == "outnumbered"


def test_fight_subtypes():
    allies = ["a", "b"]
    assert primary(base(n_enemies=3, allies_near=allies)) == "died_first"
    assert primary(base(n_enemies=3, allies_near=allies,
                        fight={"allies_dead_before": 2, "enemies_dead": 0, "first": False})) == "stayed_lost"
    assert primary(base(n_enemies=3, allies_near=allies,
                        fight={"allies_dead_before": 0, "enemies_dead": 2, "first": False})) == "traded"


def test_traded_is_not_an_issue_and_objective_loss_is():
    d1 = base(n_enemies=3, allies_near=["a", "b"], fight={"allies_dead_before": 0, "enemies_dead": 2, "first": False})
    d2 = base(n_enemies=2, lost_after=["バロン"])
    for d in (d1, d2):
        d["cause"] = deaths.classify(d, "MIDDLE", None)
    titles = [i["title"] for i in deaths.group_issues([d1, d2])]
    assert deaths.GROUP_TITLE["traded"] not in titles
    assert "デスの直後にオブジェクトを取られている" in titles


def test_unspent_gold_impact():
    c = deaths.classify(base(gold_unspent=1800), "MIDDLE", None)
    assert any(i["key"] == "late_back" for i in c["impacts"])
