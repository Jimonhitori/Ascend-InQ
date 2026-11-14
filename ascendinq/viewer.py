"""Interactive match viewer: video (optional) + minimap replay + timeline + per-moment commentary.

Writes reports/<match_id>_viewer.html (a single static page, no server needed).
"""
import json
from pathlib import Path

import requests

from . import analyze as an, config, ddragon
from .analyze import mmss

ASSET_DIR = config.REPORT_DIR / "assets"
TEMPLATE = Path(__file__).with_name("viewer_template.html")
LANE_PREFIX = {"TOP": "TOPレーン", "MIDDLE": "MIDレーン", "BOTTOM": "BOTレーン", "UTILITY": "BOTレーン"}


# ---------------------------------------------------------------- assets

def _download(url, path: Path) -> bool:
    if path.exists():
        return True
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            return True
    except requests.RequestException:
        pass
    return False


def ensure_assets(champs):
    try:
        version = requests.get(f"{ddragon.BASE}/api/versions.json", timeout=10).json()[0]
    except (requests.RequestException, ValueError):
        version = None
    has_map = (ASSET_DIR / "map11.png").exists() or (
        version and _download(f"{ddragon.BASE}/cdn/{version}/img/map/map11.png", ASSET_DIR / "map11.png"))
    icons = {}
    for c in champs:
        p = ASSET_DIR / "champion" / f"{c}.png"
        ok = p.exists() or (version and _download(f"{ddragon.BASE}/cdn/{version}/img/champion/{c}.png", p))
        icons[c] = f"assets/champion/{c}.png" if ok else None
    return ("assets/map11.png" if has_map else None), icons


# ---------------------------------------------------------------- commentary

def death_moment(n, d, a):
    me = a["me"]
    role = me["role"]
    who = d["killer"] + ("＋" + "・".join(d["assists"]) if d["assists"] else "")
    facts = []
    if d["jg_involved"]:
        facts.append("敵JGが参加")
    elif d["ejg_dist_20s"] is not None:
        facts.append(f"20秒前の敵JG: {d['ejg_zone_20s']}（{d['ejg_dist_20s']}離れていた）")
    facts.append("近くの味方: " + ("・".join(d["allies_near"]) if d["allies_near"] else "なし"))
    if d.get("opp_level") is not None:
        facts.append(f"レベル {d['level']} vs 対面 {d['opp_level']}")
    if d.get("lane_gold_diff") is not None:
        facts.append(f"対面とのゴールド差 {d['lane_gold_diff']:+}")
    if d["my_wards_3min"] is not None:
        facts.append(f"直前3分の自分のワード {d['my_wards_3min']}個")
    facts.append(f"復活まで約{d['respawn_est']}秒（推定）")
    if d["lost_after"]:
        facts.append("このデス中に取られた: " + "・".join(d["lost_after"]))

    advice = []
    early = d["t"] < 15 * 60
    if d["jg_involved"] and early and role != "JUNGLE":
        if "敵側" in d["zone"] or "敵陣" in d["zone"]:
            advice.append("敵側に押し込んだ位置でガンクされた。敵JGの位置が分からない時は、ウェーブを押し切ったらすぐ自陣側へ下がる。")
        else:
            advice.append("敵JGのガンク。20秒前の敵JGの位置を見て、来られる距離だったなら先に下がるかフラッシュを温存する。")
    if d["jg_involved"] and early and role == "JUNGLE":
        advice.append("敵JGとの戦いで負けた。相手のレベル・体力・味方の寄りやすさを比べて、不利なら競らずに反対側のキャンプへ。")
    if d["lost_after"]:
        advice.append(f"このデスで{'・'.join(d['lost_after'])}を取られた。湧き前の1分は「生きていること」を最優先に。")
    if d["n_enemies"] >= 3 and not d["allies_near"]:
        advice.append(f"味方がいない場所で{d['n_enemies']}人に捕まった。見えていない敵の人数を数えてから前に出る。")
    if d["n_enemies"] == 1 and d["killer_is_opp"]:
        if d.get("opp_level") and d["opp_level"] > d["level"]:
            advice.append(f"レベルで負けている（{d['level']} vs {d['opp_level']}）状態で1v1をした。レベル差がある時は戦わない。")
        elif d.get("lane_gold_diff") is not None and d["lane_gold_diff"] < -300:
            advice.append(f"ゴールドで負けている（{d['lane_gold_diff']:+}）状態で1v1をした。アイテム差がある時は無理をしない。")
        else:
            advice.append("条件はほぼ互角の1v1で負けた。動画でスキルの当て合いと相手の主要スキルのCDを確認する。")
    if not d["allies_near"] and d["my_wards_3min"] == 0 and any(k in d["zone"] for k in ("リバー", "敵陣ジャングル")):
        advice.append("視界のないリバー/敵陣で倒された。入る前にワードかスイーパーを使う。")
    if not advice:
        advice.append("動画で倒される5〜10秒前の判断（前に出た理由・逃げ道）を確認する。")

    return {
        "t": d["t"], "kind": "death", "icon": "💀", "severity": 3,
        "title": f"デス{n}: {who} に倒された",
        "sub": d["zone"], "facts": facts, "advice": advice,
        "jump": max(0, d["t"] - 20),
    }


def build_moments(a, match, timeline):
    me, opp = a["me"], a["opp"]
    role = me["role"]
    moments = [death_moment(n, d, a) for n, d in enumerate(a["deaths"], 1)]
    by_id = {p["participantId"]: p for p in match["info"]["participants"]}
    ja = lambda pid: ddragon.champion_name(by_id[pid]["championName"]) if pid in by_id else "ミニオン/タワー"
    my_id, my_team = me["pid"], me["team"]
    lane_prefix = LANE_PREFIX.get(role)

    for f in timeline["info"]["frames"]:
        for e in f["events"]:
            if e["type"] != "CHAMPION_KILL" or not e.get("position"):
                continue
            t = e["timestamp"] / 1000
            z = an.zone(e["position"]["x"], e["position"]["y"], my_team)
            assists = e.get("assistingParticipantIds") or []
            if e.get("killerId") == my_id or my_id in assists:
                kind = "キル" if e.get("killerId") == my_id else "アシスト"
                note = []
                if lane_prefix and not z.startswith(lane_prefix) and t < 15 * 60:
                    note.append("自分のレーンを離れて取ったキル。このあと自分のレーンのウェーブを失っていないか確認。")
                moments.append({"t": t, "kind": "kill", "icon": "⚔️", "severity": 1,
                                "title": f"{kind}: {ja(e.get('victimId', 0))}", "sub": z,
                                "facts": [f"関与: {ja(e.get('killerId', 0))}" + (" ＋" + "・".join(ja(p) for p in assists) if assists else "")],
                                "advice": note, "jump": max(0, t - 10)})
            elif (opp and role != "JUNGLE" and t < 15 * 60 and lane_prefix and not z.startswith(lane_prefix)
                  and (e.get("killerId") == opp["pid"] or opp["pid"] in assists)
                  and by_id.get(e.get("victimId"), {}).get("teamId") == my_team):
                moments.append({"t": t, "kind": "roam", "icon": "👣", "severity": 2,
                                "title": f"対面 {opp['champ_ja']} がレーンを離れてキル", "sub": z,
                                "facts": [f"倒された味方: {ja(e.get('victimId', 0))}"],
                                "advice": ["対面が見えなくなったらすぐピンを出し、ウェーブを押してプレート/タワーを取る。"],
                                "jump": max(0, t - 25)})

    duty = an.OBJ_DUTY.get(role, an.OBJ_DUTY["MIDDLE"])
    for o in a["objectives"]:
        facts = [f"30秒前の自分: {o['my_zone_before']}", f"自分との距離: {o['my_dist']}"]
        advice = []
        if o["ours"]:
            title = f"{o['name']} を取った" + ("（参加）" if o["involved"] else "")
            sev = 1
        else:
            title = f"{o['name']} を取られた"
            sev = 2
            if o["my_dead"]:
                facts.append("自分はデス中")
                advice.append("デス中に取られた。直前のデスを見直す。")
            elif o["my_dist"] and o["my_dist"] > 4000 and o["t"] >= duty.get(o["kind"], 0) * 60:
                advice.append(an.OBJ_FOCUS.get(role, an.OBJ_FOCUS["MIDDLE"]))
                sev = 3
            elif o["my_dist"] and o["my_dist"] <= 4000:
                advice.append("近くにいたのに取られた。人数差・体力差で戦えなかったのか、スマイト/位置取りの問題かを動画で確認。")
        icon = {"BARON_NASHOR": "👾", "HORDE": "🪱", "RIFTHERALD": "👁️", "ATAKHAN": "😈"}.get(o["kind"], "🐉")
        moments.append({"t": o["t"], "kind": "objective", "icon": icon, "severity": sev, "title": title,
                        "sub": "", "facts": facts, "advice": advice, "jump": max(0, o["t"] - 40),
                        "ours": o["ours"]})

    for tw in a["towers"]:
        moments.append({"t": tw["t"], "kind": "tower", "icon": "🏰", "severity": 1,
                        "title": f"{'敵' if tw['ours'] else '味方'}の{tw['lane']} {tw['tier']}タワーが折れた"
                                 + ("（関与）" if tw["involved"] else ""),
                        "sub": "", "facts": [], "advice": [], "jump": max(0, tw["t"] - 20), "ours": tw["ours"]})

    for it in a["items"]:
        if it["t"] is None:
            continue
        moments.append({"t": it["t"], "kind": "item", "icon": "🛒", "severity": 0,
                        "title": f"{it['name']} 完成", "sub": "", "facts": [], "advice": [], "jump": max(0, it["t"] - 5)})

    for r in a["lane"]:
        if "cs_opp" not in r:
            continue
        facts = [f"CS {r['cs']}（{r['cs'] - r['cs_opp']:+}）", f"ゴールド {r['gold']}（{r['gold'] - r['gold_opp']:+}）",
                 f"経験値差 {r['xp'] - r['xp_opp']:+}", f"レベル {r['level']} vs {r['level_opp']}"]
        target = an.CS10_TARGET.get(role)
        advice = []
        if r["min"] == 10 and target and r["cs"] < target:
            advice.append(f"10分CSの目標は{target}。")
        moments.append({"t": r["min"] * 60, "kind": "lane", "icon": "📊", "severity": 1,
                        "title": f"{r['min']}分時点のレーン状況", "sub": "", "facts": facts, "advice": advice,
                        "jump": r["min"] * 60})

    moments.sort(key=lambda m: m["t"])
    return moments


# ---------------------------------------------------------------- positions / graph

def build_tracks(match, timeline):
    pos = an.Positions(timeline)
    tracks = {pid: [[round(t / 1000, 1), round(x), round(y)] for t, x, y in pts] for pid, pts in pos.pts.items()}
    deaths = {pid: [] for pid in range(1, 11)}
    for f in timeline["info"]["frames"]:
        for e in f["events"]:
            if e["type"] == "CHAMPION_KILL" and e.get("victimId") in deaths:
                pid, t = e["victimId"], e["timestamp"]
                lvl = an.level_at(timeline, pid, t)
                deaths[pid].append([round(t / 1000, 1), round(an.respawn_estimate(lvl, t / 1000))])
    gold = []
    for f in timeline["info"]["frames"]:
        teams = {100: 0, 200: 0}
        for pid_s, pf in f["participantFrames"].items():
            p = next(p for p in match["info"]["participants"] if p["participantId"] == int(pid_s))
            teams[p["teamId"]] += pf["totalGold"]
        gold.append([f["timestamp"] / 1000, teams[100] - teams[200]])
    return tracks, deaths, gold


# ---------------------------------------------------------------- page

def build(a, match, timeline, video: Path | None = None, offset: float | None = None) -> Path:
    from .clips import video_offset
    parts = match["info"]["participants"]
    map_src, icons = ensure_assets({p["championName"] for p in parts})
    tracks, deaths, gold = build_tracks(match, timeline)
    if video and offset is None:
        offset = video_offset(video, a["game_start_ms"])
    data = {
        "matchId": a["match_id"],
        "gameStartMs": a["game_start_ms"],
        "duration": a["duration"],
        "header": {
            "title": f"{a['me']['champ_ja']}（{an.ROLE_JA.get(a['me']['role'], a['me']['role'])}）"
                     + (f" vs {a['opp']['champ_ja']}" if a["opp"] else ""),
            "result": "リメイク" if a["remake"] else ("勝ち" if a["win"] else "負け"),
            "win": a["win"],
            "kda": f"{a['stats']['kills']}/{a['stats']['deaths']}/{a['stats']['assists']}",
            "line": f"CS {a['stats']['cs']}（{a['stats']['cs_min']}/分） KP {a['stats']['kp']}% 視界 {a['stats']['vision_score']}",
        },
        "focus": a["focus"],
        "issues": a["issues"][:3],
        "good": a["good"],
        "myTeam": a["me"]["team"],
        "me": a["me"]["pid"],
        "players": [{"pid": p["participantId"], "champ": ddragon.champion_name(p["championName"]),
                     "icon": icons.get(p["championName"]), "team": p["teamId"],
                     "role": an.ROLE_JA.get(p.get("teamPosition", ""), "")} for p in parts],
        "tracks": tracks, "deathTimers": deaths, "gold": gold,
        "moments": build_moments(a, match, timeline),
        "map": map_src,
        "video": video.resolve().as_uri() if video else None,
        "videoName": video.name if video else None,
        "offset": offset,
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    html = html.replace("__TITLE__", f"{data['header']['title']} {data['header']['result']}")
    out = config.REPORT_DIR / f"{a['match_id']}_viewer.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
