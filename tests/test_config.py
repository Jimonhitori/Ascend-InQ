import json
import os
from pathlib import Path

from ascendinq import config

_REAL_RELOAD = config.load_dotenv  # used to check reload() behaviour on a temp .env


def test_paths_are_redirected(tmp_path):
    # safety net: the autouse fixture must keep tests away from the real repo files
    assert config.ENV_PATH == tmp_path / ".env"
    assert config.SETTINGS_PATH == tmp_path / "settings.json"


def test_write_env_keeps_comments_and_other_keys():
    config.ENV_PATH.write_text(
        "# Riot API key\nRIOT_API_KEY=old\n# RIOT_ID=commented\nRIOT_ID=Tester#JP1\nPLATFORM=jp1\n",
        encoding="utf-8")
    config.write_env({"RIOT_ID": "Other#JP1", "VIDEO_DIR": "D:/rec"})
    lines = config.ENV_PATH.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "# Riot API key",
        "RIOT_API_KEY=old",
        "# RIOT_ID=commented",
        "RIOT_ID=Other#JP1",
        "PLATFORM=jp1",
        "VIDEO_DIR=D:/rec",
    ]


def test_write_env_creates_file_when_missing():
    assert not config.ENV_PATH.exists()
    config.write_env({"RIOT_ID": "Tester#JP1"})
    text = config.ENV_PATH.read_text(encoding="utf-8")
    assert "RIOT_ID=Tester#JP1" in text
    assert "PLATFORM=jp1" in text
    assert text.count("RIOT_ID=") == 1


def test_ensure_env_copies_template():
    (config.RESOURCES / ".env.example").write_text("# template\nRIOT_API_KEY=\n", encoding="utf-8")
    assert config.ensure_env() is True
    assert config.ENV_PATH.read_text(encoding="utf-8").startswith("# template")
    assert config.ensure_env() is False


def test_reload_reads_env(monkeypatch):
    monkeypatch.setenv("ASCENDINQ_TEST_VALUE", "before")
    config.ENV_PATH.write_text("ASCENDINQ_TEST_VALUE=after\n", encoding="utf-8")
    _REAL_RELOAD(config.ENV_PATH, override=True)
    assert os.environ["ASCENDINQ_TEST_VALUE"] == "after"


def test_settings_defaults_when_missing():
    assert config.settings() == config.DEFAULTS


def test_settings_merges_file():
    config.SETTINGS_PATH.write_text(json.dumps({"keep": 5, "source": "api"}), encoding="utf-8")
    s = config.settings()
    assert s["keep"] == 5 and s["source"] == "api"
    assert s["fps"] == config.DEFAULTS["fps"]


def test_settings_broken_json_falls_back():
    config.SETTINGS_PATH.write_text("{not json", encoding="utf-8")
    assert config.settings() == config.DEFAULTS


def test_save_settings_drops_unknown_keys():
    config.save_settings({"keep": 7, "bogus": 1})
    assert json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8")) == {"keep": 7}


def test_rec_dir_default_and_custom(tmp_path):
    assert config.rec_dir() == tmp_path / "recordings"
    custom = tmp_path / "my videos"
    config.SETTINGS_PATH.write_text(json.dumps({"save_dir": str(custom)}), encoding="utf-8")
    assert config.rec_dir() == Path(custom)


def test_api_key_missing(monkeypatch):
    import pytest
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-xxxx")
    with pytest.raises(config.ConfigError):
        config.api_key()
    monkeypatch.setenv("RIOT_API_KEY", "")
    with pytest.raises(config.ConfigError):
        config.api_key()


def test_account_region_sea(monkeypatch):
    monkeypatch.setenv("REGION", "sea")
    assert config.account_region() == "asia"
    monkeypatch.setenv("REGION", "europe")
    assert config.account_region() == "europe"
