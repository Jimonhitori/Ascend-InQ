"""Rate all 10 players of a game on a 6-step scale (S/A/B/C/D/F).

Each player gets 0-100 points per component, weighted by role:
  KDA, kill participation, damage share of the team (vision for supports),
  gold difference to the lane opponent at the end, deaths per 10 min, CS per min.
Separate flags call out likely AFK (not moving / almost no gold) and feeding.
"""
from . import ddragon

GRADES = [(80, "S"), (65, "A"), (52, "B"), (42, "C"), (30, "D"), (0, "F")]
ROLE_JA = {"TOP": "TOP", "JUNGLE": "JG", "MIDDLE": "MID", "BOTTOM": "ADC", "UTILITY": "SUP"}
WEIGHTS = {  # kda, kp, impact (damage or vision), lane, deaths, farm, ganks, objectives
    "UTILITY": (0.22, 0.25, 0.20, 0.13, 0.20, 0.00, 0.00, 0.00),
    # a jungler's job: ganks before 15:00 and taking objectives
    "JUNGLE": (0.14, 0.10, 0.10, 0.10, 0.12, 0.06, 0.19, 0.19),
    "default": (0.20, 0.15, 0.20, 0.20, 0.15, 0.10, 0.00, 0.00),
}
GANK_POINTS = [0, 40, 70, 100]  # lane kill participations before 15:00 -> points


def _clamp(v):
    return max(0.0, min(100.0, v))


def grade_of(score: float) -> str:
    return next(g for lim, g in GRADES if score >= lim)


def _afk_minutes(frames, pid):
    """Longest run of minutes (after 2:00) where the player barely moved."""
    best = run = 0
    prev = None
    for f in frames[2:]:
        p = f["participantFrames"].get(str(pid), {}).get("position")
        if p and prev and abs(p["x"] - prev["x"]) + abs(p["y"] - prev["y"]) < 250:
            run += 1
            best = max(best, run)
        else:
            run = 0
        prev = p
    return best


def rate_players(match: dict, timeline: dict, duration: int) -> list:
    parts = match["info"]["participants"]
    frames = timeline["info"]["frames"]
    minutes = max(1.0, duration / 60)
    last = frames[-1]["participantFrames"] if frames else {}
    team_kills = {t: sum(p["kills"] for p in parts if p["teamId"] == t) for t in (100, 200)}
    team_dmg = {t: sum(p.get("totalDamageDealtToChampions", 0) for p in parts if p["teamId"] == t) or 1 for t in (100, 200)}

    from .analyze import zone
    events = [e for f in frames for e in f.get("events", [])]
    objectives = [e for e in events if e.get("type") == "ELITE_MONSTER_KILL"]

    def involved(e, pid):
        return e.get("killerId") == pid or pid in (e.get("assistingParticipantIds") or [])

    def early_ganks(pid, team):
        n = 0
        for e in events:
            if (e.get("type") == "CHAMPION_KILL" and e.get("timestamp", 0) < 15 * 60000 and e.get("position")
                    and involved(e, pid) and not zone(e["position"]["x"], e["position"]["y"], team).endswith("ジャングル")):
                n += 1
        return n

    kill_ev = [e for e in events if e.get("type") == "CHAMPION_KILL"]
    first_blood = kill_ev[0].get("killerId") if kill_ev else None
    most_kills = max((p["kills"] for p in parts), default=0)
    lane_zone = {"TOP": "TOPレーン", "MIDDLE": "MIDレーン", "BOTTOM": "BOTレーン", "UTILITY": "BOTレーン"}
    early = 14 * 60000  # laning phase

    def lane_stats(pid, team, role, opp_pid):
        solo = lambda e: not e.get("assistingParticipantIds")
        st = {
            "solo_kills": sum(1 for e in kill_ev if e.get("killerId") == pid and solo(e)),
            "lane_solo_kills": sum(1 for e in kill_ev if e["timestamp"] < early and e.get("killerId") == pid
                                   and e.get("victimId") == opp_pid and solo(e)),
            "lane_solo_deaths": sum(1 for e in kill_ev if e["timestamp"] < early and e.get("victimId") == pid
                                    and e.get("killerId") == opp_pid and solo(e)),
            "early_deaths": sum(1 for e in kill_ev if e["timestamp"] < early and e.get("victimId") == pid),
            "roams": 0,
        }
        home = lane_zone.get(role)
        if home and role != "UTILITY":
            st["roams"] = sum(1 for e in kill_ev if e["timestamp"] < early and e.get("position") and involved(e, pid)
                              and e.get("victimId") != opp_pid  # fights with the lane opponent are not roams
                              and not zone(e["position"]["x"], e["position"]["y"], team).startswith(home))
        return st

    out = []
    for p in parts:
        pid, team, role = p["participantId"], p["teamId"], p.get("teamPosition", "")
        k, d, a = p["kills"], p["deaths"], p["assists"]
        cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
        opp = next((o for o in parts if o["teamId"] != team and o.get("teamPosition") == role and role), None)
        gold_now = last.get(str(pid), {}).get("totalGold", p.get("goldEarned", 0))
        lane_diff = (gold_now - last.get(str(opp["participantId"]), {}).get("totalGold", 0)) if opp and last else None
        kp = (k + a) / team_kills[team] if team_kills[team] else 0
        dmg_share = p.get("totalDamageDealtToChampions", 0) / team_dmg[team]
        vision_min = p.get("visionScore", 0) / minutes
        deaths10 = d / minutes * 10
        kda = (k + a) / max(1, d)
        ls = lane_stats(pid, team, role, opp["participantId"] if opp else None)

        comp = {
            "kda": _clamp(kda / 5 * 100),
            "kp": _clamp(kp / 0.70 * 100),
            "impact": _clamp(vision_min / 2.0 * 100) if role == "UTILITY" else _clamp(dmg_share / 0.30 * 100),
            # gold lead over the lane opponent, plus/minus solo kills between the two during laning
            "lane": 50.0 if lane_diff is None else _clamp(50 + lane_diff / 3000 * 50
                                                          + 10 * ls["lane_solo_kills"] - 10 * ls["lane_solo_deaths"]),
            "deaths": _clamp(100 - deaths10 * 30),
            "farm": _clamp(cs / minutes / 8 * 100),
            "gank": 0.0, "obj": 0.0,
        }
        ganks = obj_in = None
        if role == "JUNGLE":
            ganks = early_ganks(pid, team)
            obj_in = sum(1 for e in objectives if involved(e, pid))
            comp["gank"] = float(GANK_POINTS[min(ganks, 3)])
            comp["obj"] = _clamp(obj_in / max(1, len(objectives)) * 1.5 * 100)
        w = WEIGHTS.get(role, WEIGHTS["default"])
        score = sum(c * wt for c, wt in zip(comp.values(), w))

        flags = []
        afk = _afk_minutes(frames, pid)
        if afk >= 4 or (minutes > 12 and p.get("goldEarned", 0) / minutes < 180):
            flags.append("放置（AFK）の疑い")
            score = min(score, 15)
        if d >= 8 and kda < 0.6:
            flags.append("ほぼ一方的に倒されている")
        elif d >= 10:
            flags.append(f"デス {d}")
        elif deaths10 >= 3.0 and kda < 1.0:
            flags.append("デス多め")
        if lane_diff is not None and lane_diff <= -4000:
            flags.append("対面に大差をつけられた")
        if role == "JUNGLE" and minutes > 16 and ganks == 0:
            flags.append("15分までガンク0")
        if role == "JUNGLE" and len(objectives) >= 4 and obj_in <= len(objectives) // 5:
            flags.append(f"オブジェクト関与 {obj_in}/{len(objectives)}")

        # League of Graphs-style tags: short good (+) / bad (-) traits of this game
        tags = []
        cs_min = cs / minutes
        laner = role in ("TOP", "MIDDLE", "BOTTOM")
        if kp >= 0.65 and team_kills[team] >= 10:
            tags.append(("高キル関与", "+"))
        if ls["solo_kills"] >= 2:
            tags.append((f"ソロキル {ls['solo_kills']}回", "+"))
        if ls["roams"] >= 2:
            tags.append(("すばらしいローミング", "+"))
        if role == "JUNGLE" and (ganks or 0) >= 5:
            tags.append(("ガンク上手", "+"))
        if role == "JUNGLE" and objectives and obj_in / len(objectives) >= 0.6:
            tags.append(("オブジェクト支配", "+"))
        if vision_min >= (2.5 if role == "UTILITY" else 1.3):
            tags.append(("良い視界", "+"))
        if laner and minutes >= 15 and ls["early_deaths"] == 0:
            tags.append(("倒されないレーナー", "+"))
        if lane_diff is not None and lane_diff >= 3000:
            tags.append(("レーン圧勝", "+"))
        if dmg_share >= 0.30:
            tags.append(("ダメージの柱", "+"))
        if role != "UTILITY" and cs_min >= 8:
            tags.append(("ファーマー", "+"))
        if first_blood == pid:
            tags.append(("ファーストブラッド", "+"))
        if k == most_kills and k >= 8:
            tags.append(("キルリーダー", "+"))
        tags += [(f, "-") for f in flags]
        if ls["lane_solo_deaths"] >= 2:
            tags.append((f"対面にソロキルされた {ls['lane_solo_deaths']}回", "-"))
        elif laner and ls["early_deaths"] >= 3:
            tags.append(("序盤に倒されやすい", "-"))
        if minutes >= 20 and vision_min < (1.2 if role == "UTILITY" else 0.45):
            tags.append(("視界不足", "-"))
        if laner and cs_min < 5:
            tags.append(("ファーム不足", "-"))
        if kp < 0.30 and team_kills[team] >= 10 and role != "TOP":
            tags.append(("集団戦への参加が少ない", "-"))

        labels = {"kda": f"KDA {kda:.1f}", "kp": f"キル関与 {round(kp * 100)}%",
                  "impact": (f"視界 {vision_min:.1f}/分" if role == "UTILITY" else f"ダメージ割合 {round(dmg_share * 100)}%"),
                  "lane": (f"対面とのゴールド差 {lane_diff:+}" if lane_diff is not None else "対面なし"),
                  "deaths": f"デス {d}（10分あたり {deaths10:.1f}）", "farm": f"CS {cs / minutes:.1f}/分",
                  "gank": f"15分までのガンク関与 {ganks}回", "obj": f"オブジェクト関与 {obj_in}/{len(objectives)}"}
        used = [n for n, wt in zip(comp, w) if wt > 0]
        best = max(used, key=lambda n: comp[n])
        worst = min(used, key=lambda n: comp[n])
        out.append({
            "pid": pid, "team": team, "role": ROLE_JA.get(role, role),
            "champ": p["championName"], "champ_ja": ddragon.champion_name(p["championName"]),
            "name": p.get("riotIdGameName") or p.get("summonerName", ""),
            "kda": f"{k}/{d}/{a}", "kp": round(kp * 100), "dmg_share": round(dmg_share * 100),
            "cs_min": round(cs / minutes, 1), "vision_min": round(vision_min, 2), "lane_diff": lane_diff,
            "ganks": ganks, "objectives": None if obj_in is None else f"{obj_in}/{len(objectives)}",
            "solo_kills": ls["solo_kills"], "lane_solo_kills": ls["lane_solo_kills"],
            "lane_solo_deaths": ls["lane_solo_deaths"], "roams": ls["roams"],
            # keep it readable: the 4 most important good and 3 bad traits (lists are in priority order)
            "tags": ([{"text": t, "good": True} for t, g in tags if g == "+"][:4]
                     + [{"text": t, "good": False} for t, g in tags if g == "-"][:3]),
            "score": round(score), "grade": grade_of(score), "flags": flags,
            "good": labels[best] if comp[best] >= 60 else "", "bad": labels[worst] if comp[worst] <= 35 else "",
        })
    order = {"TOP": 0, "JG": 1, "MID": 2, "ADC": 3, "SUP": 4}
    out.sort(key=lambda r: (r["team"], order.get(r["role"], 9)))
    return out
