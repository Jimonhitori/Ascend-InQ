"""Step 4: write reports/<match_id>.md and .html (+ analysis .json)."""
import datetime as dt
import html
import json

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


def to_html(a) -> str:
    """Render the markdown into simple HTML (tables, lists, headings, images)."""
    md = to_markdown(a).splitlines()
    out, in_table, in_list = [], False, False
    for line in md:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-"):
                continue
            if not in_table:
                out.append("<table>")
                in_table = "head"
            tag = "th" if in_table == "head" else "td"
            out.append("<tr>" + "".join(f"<{tag}>{_md_inline_to_html(c)}</{tag}>" for c in cells) + "</tr>")
            in_table = True
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        stripped = line.strip()
        is_item = stripped.startswith("- ") or (stripped[:2].rstrip(".").isdigit() and ". " in stripped[:4])
        if in_list and not is_item and not line.startswith("   "):
            out.append("</ul>")
            in_list = False
        if line.startswith("# "):
            cls = "win" if a["win"] else "lose"
            out.append(f"<h1 class='{cls}'>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("> "):
            out.append(f"<div class='focus'>{_md_inline_to_html(line[2:].replace('**', ''))}</div>")
        elif line.startswith("!["):
            src = line[line.index("(") + 1:-1]
            out.append(f"<span class='stills'><img src='{html.escape(src)}'></span>")
        elif is_item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            body = stripped[2:] if stripped.startswith("- ") else stripped.split(". ", 1)[1]
            if "](" in body:
                label, href = body.split("](", 1)
                body_html = f"動画: <a href='{html.escape(href.rstrip(')'))}'>開く</a>"
            else:
                body_html = _md_inline_to_html(body)
            out.append(f"<li>{body_html}</li>")
        elif line.startswith("   - "):
            out.append(f"<div style='margin-left:1.5em'>{_md_inline_to_html(line[5:])}</div>")
        elif line.startswith("※"):
            out.append(f"<p class='note'>{html.escape(line)}</p>")
        elif line == "---":
            out.append("<hr>")
        elif line:
            out.append(f"<p>{_md_inline_to_html(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    title = html.escape(md[0][2:])
    return (f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{CSS}</style></head><body>{''.join(out)}</body></html>")


def write(a):
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    base = config.REPORT_DIR / a["match_id"]
    base.with_suffix(".json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    base.with_suffix(".md").write_text(to_markdown(a), encoding="utf-8")
    base.with_suffix(".html").write_text(to_html(a), encoding="utf-8")
    return base.with_suffix(".html")


def write_index(analyses):
    """reports/index.html: list of games + recurring issues across games."""
    from collections import Counter
    rows, counter = [], Counter()
    for a in analyses:
        start, result, title, line = _header(a)
        top = a["issues"][0]["title"] if a["issues"] else "-"
        for iss in a["issues"][:3]:
            counter[iss["title"]] += 1
        cls = "win" if a["win"] else "lose"
        rows.append(f"<tr><td>{start}</td><td class='{cls}'>{result}</td>"
                    f"<td><a href='{a['match_id']}_viewer.html'>▶ {html.escape(title)}</a>"
                    f" <a href='{a['match_id']}.html' style='font-size:.85em'>(レポート)</a></td>"
                    f"<td>{html.escape(line)}</td><td>{html.escape(top)}</td></tr>")
    trend = "".join(f"<li>{html.escape(t)}（{n}試合）</li>" for t, n in counter.most_common(5))
    body = (f"<h1>Ascend InQ — 試合一覧</h1><h2>よく出る改善点（直近{len(analyses)}試合のトップ3から集計）</h2><ul>{trend}</ul>"
            "<h2>試合</h2><table><tr><th>日時</th><th>結果</th><th>チャンピオン</th><th>成績</th><th>一番の改善点</th></tr>"
            + "".join(rows) + "</table>")
    path = config.REPORT_DIR / "index.html"
    path.write_text(f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>Ascend InQ</title>"
                    f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    return path
