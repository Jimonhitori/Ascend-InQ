import html

import pytest

from ascendinq import analyze, config, report
from synthetic import ME_PUUID, build_match


@pytest.fixture
def a():
    m, t = build_match()
    return analyze.analyze(m, t, ME_PUUID)


def test_markdown_contains_focus_and_sections(a):
    md = report.to_markdown(a)
    assert a["focus"] in md
    assert "## 改善点トップ3" in md
    assert "## デス" in md
    assert "ヴォイドグラブ×3" in md
    assert a["issues"][0]["title"] in md


def test_html_contains_focus(a):
    out = report.to_html(a)
    assert out.startswith("<!doctype html>")
    assert html.escape(a["focus"]) in out
    assert out.count("<table>") == out.count("</table>")


def test_report_for_client_data_and_remake():
    m, t = build_match(wards=False, items=False)
    a = analyze.analyze(m, t, ME_PUUID)
    md = report.to_markdown(a)
    assert "最終ビルドのみ" in md
    assert "| - |" in md  # ward count shown as "-" when data is missing
    m, t = build_match(n_frames=5, duration=300)
    r = analyze.analyze(m, t, ME_PUUID)
    assert "リメイク" in report.to_markdown(r)
    assert "リメイク" in report.to_html(r)


def test_write_and_index(a):
    path = report.write(a)
    assert path.parent == config.REPORT_DIR
    assert path.exists() and path.with_suffix(".md").exists() and path.with_suffix(".json").exists()
    idx = report.write_index([a])
    assert idx.exists()
    assert a["match_id"] in idx.read_text(encoding="utf-8")


def test_markdown_links_clip_files(a):
    d = config.CLIP_DIR / a["match_id"]
    d.mkdir(parents=True)
    (d / "death1_5m30s.mp4").write_bytes(b"")
    (d / "death1_still1.jpg").write_bytes(b"")
    md = report.to_markdown(a)
    assert "death1_5m30s.mp4" in md
    assert "death1_still1.jpg" in md
    assert "開く" in report.to_html(a)
