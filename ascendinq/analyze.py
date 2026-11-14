"""Step 2: per-match analysis from match detail + timeline.

Note: timeline positions come from 1-minute frames plus event positions, so
positions between those points are linear estimates.
"""
import bisect
import math

from . import ddragon

MAP_CENTER_SUM = 14870  # x + y along the river diagonal
NEAR = 2500             # "close enough to matter" distance (map units)
RESPAWN = [10, 10, 12, 12, 14, 16, 20, 25, 28, 32.5, 35, 37.5, 40, 42.5, 45, 47.5, 50, 52.5]

ROLE_JA = {"TOP": "TOP", "JUNGLE": "JG", "MIDDLE": "MID", "BOTTOM": "ADC", "UTILITY": "SUP"}
CS10_TARGET = {"TOP": 70, "MIDDLE": 70, "BOTTOM": 75, "JUNGLE": 55}
MONSTER_JA = {
    "RIFTHERALD": "ヘラルド", "BARON_NASHOR": "バロン", "HORDE": "ヴォイドグラブ",
    "ATAKHAN": "アタカン", "DRAGON": "ドラゴン",
}
DRAGON_JA = {
    "FIRE_DRAGON": "インファーナル", "WATER_DRAGON": "オーシャン", "EARTH_DRAGON": "マウンテン",
    "AIR_DRAGON": "クラウド", "HEXTECH_DRAGON": "ヘクステック", "CHEMTECH_DRAGON": "ケミテック",
    "ELDER_DRAGON": "エルダー",
}
LANE_JA = {"TOP_LANE": "TOP", "MID_LANE": "MID", "BOT_LANE": "BOT"}
TOWER_JA = {"OUTER_TURRET": "1st", "INNER_TURRET": "2nd", "BASE_TURRET": "3rd(インヒ前)", "NEXUS_TURRET": "ネクサス"}


def mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


# ---------------------------------------------------------------- map zones

def zone(x: float, y: float, team_id: int) -> str:
    """Rough Summoner's Rift zone name from my team's point of view."""
    s = x + y
    blue = team_id == 100

    def side_word(enemy_side: bool) -> str:
        return "敵陣" if enemy_side else "自陣"

    if x < 4600 and y < 4600 and s < 6600:
        return side_word(not blue) + "ベース"
    if x > 10200 and y > 10200 and s > 23200:
        return side_word(blue) + "ベース"

    if s > MAP_CENTER_SUM + 1800:
        lane_side = "敵側" if blue else "自陣側"
    elif s < MAP_CENTER_SUM - 1800:
        lane_side = "自陣側" if blue else "敵側"
    else:
        lane_side = "中央"

    if (x < 2200 and y > 4500) or (y > 12600 and x < 10300):
        return f"TOPレーン({lane_side})"
    if (y < 2200 and x > 4500) or (x > 12600 and y < 10300):
        return f"BOTレーン({lane_side})"
    if abs(y - x) < 1100:
        return f"MIDレーン({lane_side})"
    if abs(s - MAP_CENTER_SUM) < 1500:
        return "リバー(TOP側)" if y > x else "リバー(BOT側)"
    enemy_side = (s > MAP_CENTER_SUM) if blue else (s < MAP_CENTER_SUM)
    return side_word(enemy_side) + "ジャングル"


def dist(a, b) -> float:
    if not a or not b:
        return math.inf
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------- positions

class Positions:
    """Known (time_ms, x, y) per participant from frames + positional events."""

    def __init__(self, timeline: dict):
        self.pts = {pid: [] for pid in range(1, 11)}
        info = timeline["info"]
        for f in info["frames"]:
            for pid_s, pf in f["participantFrames"].items():
                pos = pf.get("position")
                if pos:
                    self.pts[int(pid_s)].append((f["timestamp"], pos["x"], pos["y"]))
            for e in f["events"]:
                pos = e.get("position")
                if not pos:
                    continue
                pids = [e.get("killerId"), e.get("victimId")]
                pids += e.get("assistingParticipantIds", []) or []
                for pid in pids:
                    if pid and 1 <= pid <= 10:
                        self.pts[pid].append((e["timestamp"], pos["x"], pos["y"]))
        for pid in self.pts:
            self.pts[pid].sort()
        self.times = {pid: [p[0] for p in v] for pid, v in self.pts.items()}

    def at(self, pid: int, t_ms: float):
        pts, times = self.pts.get(pid), self.times.get(pid)
        if not pts:
            return None
        i = bisect.bisect_left(times, t_ms)
        if i < len(pts) and pts[i][0] == t_ms:
            return pts[i][1:]
        if i == 0:
            return pts[0][1:]
        if i >= len(pts):
            return pts[-1][1:]
        (t0, x0, y0), (t1, x1, y1) = pts[i - 1], pts[i]
        r = (t_ms - t0) / (t1 - t0) if t1 != t0 else 0
        return (x0 + (x1 - x0) * r, y0 + (y1 - y0) * r)


# ---------------------------------------------------------------- helpers

def frame_at_minute(timeline, minute):
    frames = timeline["info"]["frames"]
    return frames[minute] if minute < len(frames) else None


def all_events(timeline):
    for f in timeline["info"]["frames"]:
        yield from f["events"]


def level_at(timeline, pid, t_ms):
    frames = timeline["info"]["frames"]
    idx = min(int(t_ms // 60000), len(frames) - 1)
    return frames[idx]["participantFrames"][str(pid)].get("level", 1)


def respawn_estimate(level, t_sec):
    base = RESPAWN[max(1, min(18, level)) - 1]
    minutes = t_sec / 60
    if minutes > 15:  # death timers scale up later in the game (approximation)
        base *= 1 + min(0.5, (minutes - 15) * 0.02)
    return base


def pinfo(p):
    return {
        "pid": p["participantId"],
        "champ": p["championName"],
        "champ_ja": ddragon.champion_name(p["championName"]),
        "name": p.get("riotIdGameName") or p.get("summonerName", ""),
        "role": p.get("teamPosition") or p.get("individualPosition", ""),
        "team": p["teamId"],
    }


# ---------------------------------------------------------------- main

def _sample_before(samples, t_sec, gap):
    """Latest live sample taken at least `gap` seconds before t_sec."""
    best = None
    for s in samples or []:
        if s[0] <= t_sec - gap:
            best = s
        else:
            break
    return best


def analyze(match: dict, timeline: dict, puuid: str, live: dict | None = None) -> dict:
    """live: optional data captured during the recording (see recorder): my HP/gold samples, players alive."""
    from . import deaths as death_rules
    live = live or {}
    info = match["info"]
    parts = info["participants"]
    me_p = next((p for p in parts if p["puuid"] == puuid), None)
    if me_p is None:
        raise ValueError("この試合に指定アカウントが見つかりません")
    me = pinfo(me_p)
    my_id, my_team = me["pid"], me["team"]
    by_id = {p["participantId"]: pinfo(p) for p in parts}
    enemies = [p for p in parts if p["teamId"] != my_team]
    allies = [p for p in parts if p["teamId"] == my_team and p["participantId"] != my_id]
    opp_p = next((p for p in enemies if p.get("teamPosition") == me_p.get("teamPosition")), None)
    ejg_p = next((p for p in enemies if p.get("teamPosition") == "JUNGLE"), None)
    emid_p = next((p for p in enemies if p.get("teamPosition") == "MIDDLE"), None)
    opp = pinfo(opp_p) if opp_p else None
    ejg = pinfo(ejg_p) if ejg_p else None
    emid = pinfo(emid_p) if emid_p else None
    duration = info.get("gameDuration", 0)
    if duration > 100000:  # very old matches report ms
        duration //= 1000

    pos = Positions(timeline)
    events = list(all_events(timeline))
    has_wards = any(e["type"] == "WARD_PLACED" for e in events)
    has_items = any(e["type"] == "ITEM_PURCHASED" for e in events)
    has_plates = any(e["type"] == "TURRET_PLATE_DESTROYED" for e in events)
    champ_ja = lambda pid: by_id[pid]["champ_ja"] if pid in by_id else "ミニオン/タワー"

    # ------------------------------------------------ objectives (needed by deaths)
    objectives = []
    last_horde = {}
    for e in events:
        if e["type"] != "ELITE_MONSTER_KILL":
            continue
        t = e["timestamp"]
        mt = e.get("monsterType", "")
        if mt == "HORDE":  # count a grub fight once, not once per grub
            team = e.get("killerTeamId")
            prev = last_horde.get(team)
            last_horde[team] = t
            if prev is not None and t - prev < 90000:
                o = next(o for o in reversed(objectives) if o["kind"] == "HORDE" and o["team"] == team)
                o["count"] += 1
                o["name"] = f"ヴォイドグラブ×{o['count']}"
                o["involved"] = o["involved"] or e.get("killerId") == my_id or my_id in (e.get("assistingParticipantIds") or [])
                continue
        name = MONSTER_JA.get(mt, mt)
        if mt == "DRAGON":
            name = DRAGON_JA.get(e.get("monsterSubType", ""), "ドラゴン")
            if name != "エルダー":
                name += "ドラゴン"
        killer_team = e.get("killerTeamId")
        involved = e.get("killerId") == my_id or my_id in (e.get("assistingParticipantIds") or [])
        my_pos = pos.at(my_id, t)
        obj_pos = (e["position"]["x"], e["position"]["y"]) if e.get("position") else None
        objectives.append({
            "t": t / 1000, "name": name, "kind": mt, "team": killer_team, "count": 1,
            "ours": killer_team == my_team,
            "involved": involved, "my_dist": round(dist(my_pos, obj_pos)) if obj_pos else None,
            "my_zone_before": zone(*pos.at(my_id, t - 30000), my_team) if pos.at(my_id, t - 30000) else "?",
            "emid_zone_before": (zone(*pos.at(emid["pid"], t - 30000), my_team)
                                 if emid and pos.at(emid["pid"], t - 30000) else "?"),
            "my_dead": False,
        })

    # ------------------------------------------------ deaths
    deaths = []
    for e in events:
        if e["type"] != "CHAMPION_KILL" or e.get("victimId") != my_id:
            continue
        t = e["timestamp"]
        dpos = (e["position"]["x"], e["position"]["y"])
        killer = e.get("killerId", 0)
        assists = e.get("assistingParticipantIds") or []
        involved = [pid for pid in [killer] + assists if pid in by_id]
        jg_involved = bool(ejg and ejg["pid"] in involved)
        ejg_pos20 = pos.at(ejg["pid"], t - 20000) if ejg else None
        my_wards = (sum(1 for w in events if w["type"] == "WARD_PLACED" and w.get("creatorId") == my_id
                        and t - 180000 <= w["timestamp"] <= t and w.get("wardType") not in (None, "UNDEFINED"))
                    if has_wards else None)  # None = ward data not available (client source)
        allies_near = [a["participantId"] for a in allies if dist(pos.at(a["participantId"], t), dpos) < NEAR]
        lvl = level_at(timeline, my_id, t)
        respawn = respawn_estimate(lvl, t / 1000)
        lost_after = [o for o in objectives if not o["ours"] and 0 <= o["t"] - t / 1000 <= respawn + 30]
        for o in objectives:
            if 0 <= o["t"] - t / 1000 <= respawn:
                o["my_dead"] = True
        frames = timeline["info"]["frames"]
        pf = frames[min(int(t // 60000), len(frames) - 1)]["participantFrames"]
        me_s = _sample_before(live.get("me"), t / 1000, 8)      # [gt, hp_frac, gold, level]
        gold_s = _sample_before(live.get("me"), t / 1000, 1)
        pl_s = _sample_before(live.get("players"), t / 1000, 3)  # [gt, {name: [team, dead, level]}]
        enemies_alive = (sum(1 for team, dead, _ in pl_s[1].values() if team != my_team and not dead)
                         if pl_s else None)
        kills_near = [k for k in events if k["type"] == "CHAMPION_KILL" and k is not e
                       and t - 15000 <= k["timestamp"] <= t + 10000 and k.get("victimId") in by_id]
        fight = {
            "allies_dead_before": sum(1 for k in kills_near if k["timestamp"] <= t
                                      and by_id[k["victimId"]]["team"] == my_team),
            "enemies_dead": sum(1 for k in kills_near if by_id[k["victimId"]]["team"] != my_team),
            "first": not any(k["timestamp"] <= t for k in kills_near),
        }
        kf = pf.get(str(killer), {}) if killer in by_id else {}
        deaths.append({
            "fight": fight,
            "killer_level": kf.get("level"),
            "killer_gold_diff": pf[str(my_id)]["totalGold"] - kf["totalGold"] if kf.get("totalGold") is not None else None,
            "hp_before": me_s[1] if me_s and me_s[0] >= t / 1000 - 20 else None,
            "gold_unspent": gold_s[2] if gold_s and gold_s[0] >= t / 1000 - 10 else None,
            "enemies_alive": enemies_alive,
            "t": t / 1000,
            "pos": dpos,
            "killer_pid": killer,
            "opp_level": pf[str(opp["pid"])]["level"] if opp else None,
            "lane_gold_diff": pf[str(my_id)]["totalGold"] - pf[str(opp["pid"])]["totalGold"] if opp else None,
            "zone": zone(*dpos, my_team),
            "killer": champ_ja(killer),
            "killer_is_opp": bool(opp and killer == opp["pid"]),
            "assists": [champ_ja(a) for a in assists],
            "n_enemies": max(1, len(involved)),
            "jg_involved": jg_involved,
            "ejg_zone_20s": zone(*ejg_pos20, my_team) if ejg_pos20 else "?",
            "ejg_dist_20s": round(dist(ejg_pos20, dpos)) if ejg_pos20 else None,
            "my_wards_3min": my_wards,
            "allies_near": [champ_ja(a) for a in allies_near],
            "bounty": e.get("shutdownBounty", 0) + e.get("bounty", 0),
            "level": lvl,
            "respawn_est": round(respawn),
            "lost_after": [o["name"] for o in lost_after],
        })

    # ------------------------------------------------ lane (10 / 15 min)
    lane = []
    for minute in (10, 15):
        f = frame_at_minute(timeline, minute)
        if not f:
            continue
        mf = f["participantFrames"][str(my_id)]
        row = {"min": minute,
               "cs": mf["minionsKilled"] + mf["jungleMinionsKilled"],
               "gold": mf["totalGold"], "xp": mf["xp"], "level": mf["level"]}
        if opp:
            of = f["participantFrames"][str(opp["pid"])]
            row.update({"cs_opp": of["minionsKilled"] + of["jungleMinionsKilled"],
                        "gold_opp": of["totalGold"], "xp_opp": of["xp"], "level_opp": of["level"]})
        lane.append(row)

    # ------------------------------------------------ towers & plates
    towers, plates = [], {"ours": 0, "theirs": 0}
    for e in events:
        if e["type"] == "BUILDING_KILL" and e.get("buildingType") == "TOWER_BUILDING":
            involved = e.get("killerId") == my_id or my_id in (e.get("assistingParticipantIds") or [])
            towers.append({
                "t": e["timestamp"] / 1000,
                "ours": e.get("teamId") != my_team,  # teamId = owner of the destroyed tower
                "lane": LANE_JA.get(e.get("laneType"), "?"),
                "tier": TOWER_JA.get(e.get("towerType"), "?"),
                "involved": involved,
            })
        elif e["type"] == "TURRET_PLATE_DESTROYED" and e.get("laneType") == "MID_LANE":
            plates["ours" if e.get("teamId") != my_team else "theirs"] += 1

    # ------------------------------------------------ items
    items = []
    for e in events:
        if e.get("participantId") != my_id:
            continue
        if e["type"] == "ITEM_PURCHASED":
            kind = ddragon.is_completed_item(e["itemId"])
            if kind:
                items.append({"t": e["timestamp"] / 1000, "id": e["itemId"],
                              "name": ddragon.item_name(e["itemId"]), "kind": kind})
        elif e["type"] == "ITEM_UNDO" and e.get("beforeId"):
            for i in range(len(items) - 1, -1, -1):
                if items[i]["id"] == e["beforeId"]:
                    items.pop(i)
                    break
    if not has_items:  # no purchase timeline (client source without live capture): final build only
        for k in range(7):
            iid = me_p.get(f"item{k}", 0)
            kind = ddragon.is_completed_item(iid) if iid else None
            if kind:
                items.append({"t": None, "id": iid, "name": ddragon.item_name(iid), "kind": kind})

    # ------------------------------------------------ roams (before 15:00)
    def kill_list(pid):
        out = []
        for e in events:
            if e["type"] != "CHAMPION_KILL" or e["timestamp"] > 15 * 60000 or not e.get("position"):
                continue
            if e.get("killerId") != pid and pid not in (e.get("assistingParticipantIds") or []):
                continue
            z = zone(e["position"]["x"], e["position"]["y"], my_team)
            if z.startswith("MID"):
                continue
            out.append({"t": e["timestamp"] / 1000, "zone": z, "victim": champ_ja(e.get("victimId", 0))})
        return out

    roams_mine = kill_list(my_id) if me["role"] == "MIDDLE" else []
    roams_enemy_mid = kill_list(emid["pid"]) if emid and me["role"] == "MIDDLE" else []

    from .roams import analyze_roams
    deaths_of = {}
    for e in events:
        if e["type"] == "CHAMPION_KILL" and e.get("victimId") in by_id:
            v = e["victimId"]
            deaths_of.setdefault(v, []).append(
                (e["timestamp"] / 1000, respawn_estimate(level_at(timeline, v, e["timestamp"]), e["timestamp"] / 1000)))
    roams = analyze_roams(events=events, frames=timeline["info"]["frames"], pos=pos, zone_fn=zone, me=me, opp=opp,
                          ejg=ejg, by_id=by_id, my_team=my_team, deaths_of=deaths_of)

    # ------------------------------------------------ totals
    team_kills = sum(p["kills"] for p in parts if p["teamId"] == my_team)
    minutes = max(1, duration / 60)
    stats = {
        "kills": me_p["kills"], "deaths": me_p["deaths"], "assists": me_p["assists"],
        "cs": me_p["totalMinionsKilled"] + me_p["neutralMinionsKilled"],
        "cs_min": round((me_p["totalMinionsKilled"] + me_p["neutralMinionsKilled"]) / minutes, 1),
        "kp": round(100 * (me_p["kills"] + me_p["assists"]) / team_kills) if team_kills else 0,
        "damage": me_p.get("totalDamageDealtToChampions", 0),
        "vision_score": me_p.get("visionScore", 0),
        "vision_min": round(me_p.get("visionScore", 0) / minutes, 2),
        "wards": me_p.get("wardsPlaced", 0),
        "control_wards": me_p.get("visionWardsBoughtInGame", 0),
        "gold": me_p.get("goldEarned", 0),
    }

    a = {
        "match_id": match["metadata"]["matchId"],
        "game_start_ms": info.get("gameStartTimestamp") or info.get("gameCreation"),
        "duration": duration,
        "win": me_p["win"],
        "remake": me_p.get("gameEndedInEarlySurrender", False),
        "me": me, "opp": opp, "enemy_jg": ejg, "enemy_mid": emid,
        "stats": stats, "lane": lane, "deaths": deaths, "objectives": objectives,
        "towers": towers, "mid_plates": plates if has_plates else None, "items": items,
        "data_missing": [k for k, ok in (("wards", has_wards), ("items", has_items), ("plates", has_plates)) if not ok],
        "roams_mine": roams_mine, "roams_enemy_mid": roams_enemy_mid, "roams": roams,
    }
    if a["remake"] or duration < 6 * 60:
        a["remake"] = True
        a["issues"], a["good"] = [], []
        a["focus"] = "リメイクの試合なので分析していません。"
        return a
    for d in a["deaths"]:
        d["cause"] = death_rules.classify(d, me["role"], ejg["champ_ja"] if ejg else None)
    a["rules_version"] = death_rules.RULES_VERSION
    a["has_live"] = bool(live.get("me"))
    from .teamrate import rate_players
    a["players"] = rate_players(match, timeline, duration)
    a["issues"], a["good"] = find_issues(a)
    a["focus"] = a["issues"][0]["focus"] if a["issues"] else "今の動きを続けつつ、CSを1分あたり+0.5伸ばすことを意識する。"
    return a


# Which objectives each role is expected to help with, and from what minute.
OBJ_DUTY = {
    "TOP": {"HORDE": 0, "RIFTHERALD": 0, "DRAGON": 14, "BARON_NASHOR": 0, "ATAKHAN": 0},
    "JUNGLE": {"HORDE": 0, "RIFTHERALD": 0, "DRAGON": 0, "BARON_NASHOR": 0, "ATAKHAN": 0},
    "MIDDLE": {"HORDE": 0, "RIFTHERALD": 0, "DRAGON": 0, "BARON_NASHOR": 0, "ATAKHAN": 0},
    "BOTTOM": {"HORDE": 14, "RIFTHERALD": 14, "DRAGON": 0, "BARON_NASHOR": 0, "ATAKHAN": 0},
    "UTILITY": {"HORDE": 14, "RIFTHERALD": 14, "DRAGON": 0, "BARON_NASHOR": 0, "ATAKHAN": 0},
}
OBJ_FOCUS = {
    "TOP": "グラブ/ヘラルドの湧き45秒前にTOPのウェーブを押してテレポートか徒歩で川に寄る。",
    "JUNGLE": "オブジェクトの湧き1分前にはジャングルを狩り終えて川に入り、味方レーナーにピンで集合をかける。",
    "MIDDLE": "オブジェクトの湧き45秒前にMIDのウェーブを押し、先に川へ移動する。",
    "BOTTOM": "ドラゴンの湧き45秒前にウェーブを押してサポートと一緒に川へ寄る。",
    "UTILITY": "ドラゴンの湧き1分前に川へワードを置き、ADCと一緒に寄る。",
}


# ---------------------------------------------------------------- advice rules

def find_issues(a):
    issues, good = [], []
    role = a["me"]["role"]
    deaths = a["deaths"]
    st = a["stats"]

    def add(score, title, detail, focus):
        issues.append({"score": score, "title": title, "detail": detail, "focus": focus})

    ts = lambda ds: "、".join(mmss(d["t"]) for d in ds)

    # 1-4. deaths, grouped by classified cause (see deaths.py)
    from . import deaths as death_rules
    issues.extend(death_rules.group_issues(deaths))

    # 5. enemy objectives while I was alive but far away
    duty = OBJ_DUTY.get(role, OBJ_DUTY["MIDDLE"])
    missed = [o for o in a["objectives"] if not o["ours"] and not o["my_dead"]
              and o["my_dist"] is not None and o["my_dist"] > 4000
              and o["t"] >= duty.get(o["kind"], 0) * 60]
    if missed:
        add((2 if role == "JUNGLE" else 1.5) * len(missed), "生存中なのに相手のオブジェクトに寄れていない",
            "、".join(f"{mmss(o['t'])} {o['name']}（距離{o['my_dist']}, 30秒前の自分: {o['my_zone_before']}）"
                     for o in missed),
            OBJ_FOCUS.get(role, OBJ_FOCUS["MIDDLE"]))

    # 7. lane CS / gold
    l10 = next((r for r in a["lane"] if r["min"] == 10), None)
    l15 = next((r for r in a["lane"] if r["min"] == 15), None)
    target = CS10_TARGET.get(role)
    if l10 and target:
        if l10["cs"] < target and l10["cs"] - l10.get("cs_opp", 0) < 5:
            add(1 + (target - l10["cs"]) / 8, f"10分のCSが目標({target})に届いていない",
                f"10分時点 CS {l10['cs']}（対面 {l10.get('cs_opp', '?')}）。",
                f"10分でCS{target}を目標に、" +
                ("ジャングルを狩るルートを止めずに、ガンクは成功しそうな時だけ行く。" if role == "JUNGLE"
                 else "トレードよりもラストヒットを優先する。"))
        elif l10.get("cs_opp") is not None and l10["cs"] - l10["cs_opp"] >= 10:
            good.append(f"10分のCSで対面に+{l10['cs'] - l10['cs_opp']}差をつけた")
    if l15 and l15.get("gold_opp") is not None:
        diff = l15["gold"] - l15["gold_opp"]
        if diff <= -800:
            add(2 + abs(diff) / 1000, "15分時点で対面にゴールド差をつけられている",
                f"15分ゴールド差 {diff:+}、経験値差 {l15['xp'] - l15['xp_opp']:+}。",
                "レーン戦で負けている時は無理に勝負せず、タワー下でCSを取り切ってJGの助けを待つ。")
        elif diff >= 800:
            good.append(f"15分で対面にゴールド{diff:+}差")

    # 8. lane opponent roams (all lane roles)
    ro = (a.get("roams") or {}).get("opp")
    if ro and a.get("opp"):
        idle = [tr for tr in ro["trips"] if tr["response"] == "nothing"]
        if len(ro["success"]) >= 2 or (ro["success"] and idle):
            add(1.5 * len(ro["success"]) + 0.5 * len(idle), "対面のロームに対応できていない",
                f"対面（{a['opp']['champ_ja']}）がレーンを離れてキルに関与: "
                + "、".join(f"{mmss(r['t'])} {r['zone']}" for r in ro["success"])
                + (f" / 対面がいない間に何もできなかった時間: {len(idle)}回" if idle else ""),
                "対面が見えなくなったらすぐピンを出し、ウェーブを押してプレートかCSを取る（または一緒に寄る）。")
        elif len(ro["trips"]) >= 2 and not idle:
            good.append(f"対面のローム{len(ro['trips'])}回に、追いかけるかCSを取って対応できた")
    rm = (a.get("roams") or {}).get("mine")
    if rm and len(rm["success"]) >= 2:
        good.append(f"15分までに{len(rm['success'])}回レーン外のキルに関与")

    # 9. vision
    if role != "UTILITY":
        if st["control_wards"] == 0 and a["duration"] > 20 * 60:
            add(2, "コントロールワードを1つも買っていない",
                f"視界スコア {st['vision_score']}（{st['vision_min']}/分）、ワード設置 {st['wards']}。",
                "帰還するたびにコントロールワードを1つ買い、自分のレーン横のリバーか次のオブジェクト付近に置く。")
        elif st["vision_min"] < 0.7 and a["duration"] > 20 * 60:
            add(1.2, "視界スコアが低い",
                f"視界スコア {st['vision_score']}（{st['vision_min']}/分）。目安は 0.8/分以上。",
                "トリンケットが溜まったら必ず使い、帰還時にコントロールワードを買う。")

    # 10. first item timing
    first = next((i for i in a["items"] if i["kind"] == "legendary" and i["t"] is not None), None)
    if first and role in ("MIDDLE", "TOP", "BOTTOM") and first["t"] > 14 * 60:
        add(1 + (first["t"] - 14 * 60) / 120, "1つ目のコアアイテムが遅い",
            f"{first['name']} 完成 {mmss(first['t'])}（目安 13〜14分以内）。",
            "CSを落とさないことと、ゴールドが溜まったタイミングで帰還することを意識する。")
    elif first and first["t"] <= 12 * 60:
        good.append(f"1つ目のコア（{first['name']}）が {mmss(first['t'])} と早い")

    # 11. too many deaths overall
    if st["deaths"] >= 8:
        add(1 + (st["deaths"] - 7) * 0.5, "デス数が多い",
            f"{st['deaths']}デス。",
            "倒されたら「どこで・誰に・なぜ」をすぐ一言でメモし、同じ死に方を2回しない。")
    elif st["deaths"] <= 2 and a["duration"] > 20 * 60:
        good.append(f"デス {st['deaths']} に抑えた")

    if st["kp"] >= 60:
        good.append(f"キル関与率 {st['kp']}%")

    issues.sort(key=lambda i: i["score"], reverse=True)
    return issues, good
