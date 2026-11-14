"""Step 4: write reports/<match_id>.md and .html (+ analysis .json)."""
import datetime as dt
import html
import json
from pathlib import Path

from . import config
from .analyze import mmss, ROLE_JA


def _clip_files(match_id, idx):
    d = config.CLIP_DIR / match_id
    if not d.exists():
        return None, []
    video = next(iter(sorted(d.glob(f"death{idx}_*.mp4")) + sorted(d.glob(f"death{idx}_*.mkv"))), None)
    stills = sorted(d.glob(f"death{idx}_still*.jpg"))
    return video, stills


def _header(a):
    me, opp = a["me"], a["opp"]
    start = dt.datetime.fromtimestamp(a["game_start_ms"] / 1000).strftime("%Y-%m-%d %H:%M")
    result = "リメイク" if a["remake"] else ("勝ち" if a["win"] else "負け")
    vs = f" vs {opp['champ_ja']}" if opp else ""
    s = a["stats"]
    return (start, result,
            f"{me['champ_ja']}（{ROLE_JA.get(me['role'], me['role'])}）{vs}",
            f"{s['kills']}/{s['deaths']}/{s['assists']}  CS {s['cs']}（{s['cs_min']}/分）  "
            f"KP {s['kp']}%  視界 {s['vision_score']}  試合時間 {mmss(a['duration'])}")


def to_markdown(a) -> str:
    start, result, title, line = _header(a)
    L = [f"# {start} {result} — {title}", "", line, ""]

    L += ["## 次の試合で意識すること", "", f"> **{a['focus']}**", ""]
    L += ["## 改善点トップ3", ""]
    if not a["issues"]:
        L.append("目立った問題は見つかりませんでした。")
    for i, iss in enumerate(a["issues"][:3], 1):
        L += [f"{i}. **{iss['title']}**", f"   - {iss['detail']}", f"   - 対策: {iss['focus']}"]
    if a["good"]:
        L += ["", "## 良かった点", ""] + [f"- {g}" for g in a["good"]]

    if a["lane"]:
        L += ["", "## レーン（対面差）", "", "| 時間 | CS | ゴールド | 経験値 | レベル |", "|---|---|---|---|---|"]
        for r in a["lane"]:
            if "cs_opp" in r:
                L.append(f"| {r['min']}分 | {r['cs']} ({r['cs'] - r['cs_opp']:+}) | {r['gold']} ({r['gold'] - r['gold_opp']:+}) "
                         f"| {r['xp']} ({r['xp'] - r['xp_opp']:+}) | {r['level']} vs {r['level_opp']} |")
            else:
                L.append(f"| {r['min']}分 | {r['cs']} | {r['gold']} | {r['xp']} | {r['level']} |")

    L += ["", "## デス", ""]
    if not a["deaths"]:
        L.append("なし")
    else:
        L += ["| # | 時刻 | 場所 | 倒した敵 | 人数 | 敵JG(20秒前) | 3分内の自ワード | 近くの味方 | 直後に失ったもの |",
              "|---|---|---|---|---|---|---|---|---|"]
        for n, d in enumerate(a["deaths"], 1):
            jg = "**本人が参加**" if d["jg_involved"] else f"{d['ejg_zone_20s']} (距離{d['ejg_dist_20s']})"
            L.append(f"| {n} | {mmss(d['t'])} | {d['zone']} | {d['killer']}"
                     f"{' + ' + '/'.join(d['assists']) if d['assists'] else ''} | {d['n_enemies']} | {jg} "
                     f"| {'-' if d['my_wards_3min'] is None else d['my_wards_3min']} | {'/'.join(d['allies_near']) or 'なし'} | {'/'.join(d['lost_after']) or '-'} |")
        for n, d in enumerate(a["deaths"], 1):
            video, stills = _clip_files(a["match_id"], n)
            if video or stills:
                L += ["", f"### デス{n}（{mmss(d['t'])}）の場面"]
                if video:
                    L.append(f"- 動画: [../clips/{a['match_id']}/{video.name}](../clips/{a['match_id']}/{video.name})")
                L += [f"![](../clips/{a['match_id']}/{s.name})" for s in stills]

    L += ["", "## オブジェクト", ""]
    if a["objectives"]:
        L += ["| 時刻 | 種類 | 取ったチーム | 自分の関与 | 自分の距離 | 30秒前の自分 | 30秒前の相手MID |", "|---|---|---|---|---|---|---|"]
        for o in a["objectives"]:
            me_s = "参加" if o["involved"] else ("デス中" if o["my_dead"] else "-")
            L.append(f"| {mmss(o['t'])} | {o['name']} | {'味方' if o['ours'] else '**敵**'} | {me_s} "
                     f"| {o['my_dist']} | {o['my_zone_before']} | {o['emid_zone_before']} |")
    else:
        L.append("なし")
    if a["towers"]:
        L += ["", "タワー: " + "、".join(
            f"{mmss(t['t'])} {'敵' if t['ours'] else '味方'}{t['lane']}{t['tier']}{'(関与)' if t['involved'] else ''}"
            for t in a["towers"])]
    if a.get("mid_plates"):
        L += ["", f"MIDのタワープレート: 取った {a['mid_plates']['ours']} / 取られた {a['mid_plates']['theirs']}"]

    L += ["", "## アイテム完成", ""]
    if a["items"] and a["items"][0]["t"] is None:
        L.append("（完成時刻のデータが無いため、最終ビルドのみ）")
    L += [f"- {mmss(i['t']) if i['t'] is not None else ''} {i['name']}{'（靴）' if i['kind'] == 'boots' else ''}"
          for i in a["items"]] or ["なし"]

    if a["me"]["role"] == "MIDDLE":
        L += ["", "## ローム（15分まで、MID以外でのキル関与）", "",
              "- 自分: " + ("、".join(f"{mmss(r['t'])} {r['zone']}" for r in a["roams_mine"]) or "なし"),
              "- 相手MID: " + ("、".join(f"{mmss(r['t'])} {r['zone']}" for r in a["roams_enemy_mid"]) or "なし")]

    L += ["", "---", "※ 位置は1分ごとのデータとイベントからの推定です。ワードの位置はRiot APIに含まれないため、"
          "ワード数は「自分が直前3分に置いた数」で代用しています。"]
    return "\n".join(L) + "\n"


CSS = """
body{font-family:"Yu Gothic UI","Meiryo",sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;
background:#101418;color:#e6e6e6;line-height:1.6}
h1{font-size:1.4em}h2{border-bottom:1px solid #333;padding-bottom:4px;margin-top:2em}
.win{color:#4fc3f7}.lose{color:#ef5350}
.focus{background:#1d2a36;border-left:4px solid #c8aa6e;padding:12px 16px;font-size:1.15em;font-weight:bold}
table{border-collapse:collapse;width:100%;font-size:.9em}td,th{border:1px solid #333;padding:4px 6px;text-align:left}
th{background:#1a1f25}.bad{color:#ef5350;font-weight:bold}.stills img{width:24%;margin-right:1%}
.note{color:#888;font-size:.85em}a{color:#4fc3f7}
"""


def _md_inline_to_html(text: str) -> str:
    out = html.escape(text)
    parts = out.split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


TEMPLATES = Path(__file__).parent


def _render(template, data):
    html_text = (TEMPLATES / template).read_text(encoding="utf-8")
    return html_text.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def to_html(a) -> str:
    """Visual report: cards, death timeline + map, lane bars, roams (rendered client-side, no libraries)."""
    title = f"{a['me']['champ_ja']} {'勝ち' if a['win'] else '負け'}"
    clips = []
    for n in range(1, len(a.get("deaths", [])) + 1):
        video, stills = _clip_files(a["match_id"], n)
        rel = f"../clips/{a['match_id']}/"
        clips.append({"video": rel + video.name if video else None, "stills": [rel + s.name for s in stills]})
    return _render("report_template.html", dict(a, clips=clips)).replace("__TITLE__", html.escape(title))


def summary(a) -> dict:
    """Compact per-game row for the index page."""
    from collections import Counter
    s = a["stats"]
    causes = Counter(d["cause"]["primary"]["key"] for d in a["deaths"] if d.get("cause"))
    top = a["issues"][0] if a["issues"] else None
    return {
        "id": a["match_id"], "start": a["game_start_ms"], "win": a["win"], "remake": a["remake"],
        "champ": a["me"]["champ"], "champ_ja": a["me"]["champ_ja"], "role": a["me"]["role"],
        "opp": a["opp"]["champ_ja"] if a["opp"] else "",
        "kda": f"{s['kills']}/{s['deaths']}/{s['assists']}", "deaths": s["deaths"], "cs_min": s["cs_min"], "kp": s["kp"],
        "focus": a["focus"], "issue": top["title"] if top else "", "top_cause": top.get("cause") if top else None,
        "causes": dict(causes),
    }


def write(a):
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    base = config.REPORT_DIR / a["match_id"]
    base.with_suffix(".json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(to_markdown(a), encoding="utf-8")
    base.with_suffix(".html").write_text(to_html(a), encoding="utf-8")
    return base.with_suffix(".html")


def write_index(analyses):
    """reports/index.html: game cards, most common death causes, trends."""
    rows = sorted((summary(a) for a in analyses), key=lambda r: r["start"] or 0, reverse=True)
    path = config.REPORT_DIR / "index.html"
    path.write_text(_render("index_template.html", rows), encoding="utf-8")
    return path
