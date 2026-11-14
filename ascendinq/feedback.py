"""Summarise exported viewer feedback ("合ってる / 違う") per rule, to see which rules to fix."""
import json
from collections import defaultdict
from pathlib import Path

from .deaths import GROUP_TITLE


def default_files():
    return sorted((Path.home() / "Downloads").glob("ascendinq-feedback-*.json"))


def summarize(files):
    stats = defaultdict(lambda: {"ok": 0, "ng": 0, "examples": []})
    matches = set()
    for f in files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        matches.add(d.get("matchId"))
        for it in d.get("items", []):
            s = stats[it.get("cause", "?")]
            s[it.get("verdict", "ng")] += 1
            if it.get("verdict") == "ng":
                s["examples"].append(f"{d.get('matchId')} {it.get('title', '')}")
    return matches, dict(stats)


def report(files) -> str:
    matches, stats = summarize(files)
    if not stats:
        return "評価ファイルが見つかりません（ビューアの「評価を書き出す」で保存したファイルを指定してください）。"
    lines = [f"{len(matches)}試合分の評価", "", f"{'ルール':<28}{'正解率':>8}{'件数':>6}"]
    for cause, s in sorted(stats.items(), key=lambda kv: (kv[1]['ok'] / max(1, kv[1]['ok'] + kv[1]['ng']))):
        n = s["ok"] + s["ng"]
        name = GROUP_TITLE.get(cause, cause)
        lines.append(f"{name:<28}{round(100 * s['ok'] / n):>7}%{n:>6}")
        for ex in s["examples"][:3]:
            lines.append(f"    違う: {ex}")
    return "\n".join(lines)
