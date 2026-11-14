import datetime as dt
import json
from pathlib import Path

from ascendinq import clips


def test_obs_filename():
    p = Path("2026-11-14 21-03-10.mkv")
    assert clips.video_start_epoch(p) == dt.datetime(2026, 11, 14, 21, 3, 10).timestamp()


def test_obs_filename_underscore_variant():
    p = Path("2026-11-14_21-03-10.mp4")
    assert clips.video_start_epoch(p) == dt.datetime(2026, 11, 14, 21, 3, 10).timestamp()


def test_outplayed_filename():
    p = Path("League of Legends_07-25-2026_20-8-21-0.mp4")
    assert clips.video_start_epoch(p) == dt.datetime(2026, 7, 25, 20, 8, 21).timestamp()


def test_unknown_name_uses_file_time(tmp_path):
    p = tmp_path / "game.mp4"
    p.write_bytes(b"")
    assert clips.video_start_epoch(p) == p.stat().st_ctime


def test_video_offset_from_name(tmp_path):
    v = tmp_path / "2026-11-14 21-03-10.mkv"
    v.write_bytes(b"")
    start = dt.datetime(2026, 11, 14, 21, 3, 10).timestamp()
    assert clips.video_offset(v, int((start + 42) * 1000)) == 42


def test_video_offset_prefers_sidecar(tmp_path):
    v = tmp_path / "2026-11-14 21-03-10.mkv"
    v.write_bytes(b"")
    v.with_suffix(".json").write_text(json.dumps({"offset": 12.5}), encoding="utf-8")
    assert clips.video_offset(v, 0) == 12.5


def test_video_offset_ignores_broken_sidecar(tmp_path):
    v = tmp_path / "2026-11-14 21-03-10.mkv"
    v.write_bytes(b"")
    v.with_suffix(".json").write_text("{broken", encoding="utf-8")
    start = dt.datetime(2026, 11, 14, 21, 3, 10).timestamp()
    assert clips.video_offset(v, int((start + 5) * 1000)) == 5


def test_find_video_in_folder(tmp_path):
    start = dt.datetime(2026, 11, 14, 21, 3, 10).timestamp()
    good = tmp_path / "2026-11-14 21-03-10.mkv"
    too_old = tmp_path / "2026-11-14 18-00-00.mkv"
    partial = tmp_path / "2026-11-14 21-03-11.part.mp4"
    for f in (good, too_old, partial):
        f.write_bytes(b"")
    hit = clips.find_video(int((start + 60) * 1000), tmp_path)
    assert hit == good
