import pytest

from ascendinq.analyze import zone


@pytest.mark.parametrize("team,expected", [(100, "自陣ベース"), (200, "敵陣ベース")])
def test_blue_base(team, expected):
    assert zone(500, 500, team) == expected


@pytest.mark.parametrize("team,expected", [(100, "敵陣ベース"), (200, "自陣ベース")])
def test_red_base(team, expected):
    assert zone(14300, 14300, team) == expected


def test_mid_center():
    assert zone(7400, 7400, 100) == "MIDレーン(中央)"
    assert zone(7400, 7400, 200) == "MIDレーン(中央)"


def test_mid_sides_flip_by_team():
    assert zone(9000, 9000, 100) == "MIDレーン(敵側)"
    assert zone(9000, 9000, 200) == "MIDレーン(自陣側)"


def test_river():
    assert zone(4500, 10000, 100) == "リバー(TOP側)"
    assert zone(10000, 4500, 100) == "リバー(BOT側)"


def test_lanes():
    assert zone(1200, 9000, 100).startswith("TOPレーン")
    assert zone(9000, 1200, 100).startswith("BOTレーン")


def test_jungles():
    assert zone(4000, 7000, 100) == "自陣ジャングル"
    assert zone(10500, 8000, 100) == "敵陣ジャングル"
    assert zone(10500, 8000, 200) == "自陣ジャングル"
