"""Roams and ganks before 15:00.

- Successful roams: kills/assists away from the player's own lane (exact).
- Roam trips: minutes where a laner's 1-minute position was outside their lane
  and not in base (estimate; short trips between frames are missed).
- For each enemy trip: what I did meanwhile (followed / farmed / nothing).
- Enemy jungler: kills per lane and how often they were seen near each lane.
"""
ROLE_LANE = {"TOP": "TOP", "MIDDLE": "MID", "BOTTOM": "BOT", "UTILITY": "BOT"}
LANES = ("TOP", "MID", "BOT")
END_MIN = 15


def lane_of(zone: str):
    for l in LANES:
        if zone.startswith(l):
            return l
    return None


def _zone_at(pos, zone_fn, pid, t_ms, team):
    p = pos.at(pid, t_ms)
    return zone_fn(*p, team) if p else ""


def _kills_away(events, pid, home, team_of, my_team, zone_fn, victim_team):
    out = []
    for e in events:
        if e["type"] != "CHAMPION_KILL" or e["timestamp"] > END_MIN * 60000 or not e.get("position"):
            continue
        if e.get("killerId") != pid and pid not in (e.get("assistingParticipantIds") or []):
            continue
        if team_of.get(e.get("victimId")) != victim_team:
            continue
        z = zone_fn(e["position"]["x"], e["position"]["y"], my_team)
        if lane_of(z) == home:
            continue
        out.append({"t": e["timestamp"] / 1000, "zone": z, "victim_pid": e.get("victimId")})
    return out


def _trips(frames, pos, zone_fn, pid, home, my_team, dead_at):
    """Consecutive minutes outside the home lane (not in base, not dead)."""
    trips, cur = [], None
    for m in range(3, min(END_MIN, len(frames))):
        t = m * 60000
        z = _zone_at(pos, zone_fn, pid, t, my_team)
        away = z and lane_of(z) != home and "ベース" not in z and not dead_at(pid, t / 1000)
        if away:
            if cur and cur["end"] == m - 1:
                cur["end"] = m
                cur["zones"].append(z)
            else:
                cur = {"start": m, "end": m, "zones": [z]}
                trips.append(cur)
        else:
            cur = None
    return trips


def analyze_roams(*, events, frames, pos, zone_fn, me, opp, ejg, by_id, my_team, deaths_of):
    team_of = {pid: p["team"] for pid, p in by_id.items()}
    enemy_team = 300 - my_team

    def dead_at(pid, t_sec):
        return any(d <= t_sec < d + r for d, r in deaths_of.get(pid, []))

    out = {"opp": None, "mine": None, "enemy_jg": None}
    my_lane = ROLE_LANE.get(me["role"])

    if opp and my_lane:
        success = _kills_away(events, opp["pid"], my_lane, team_of, my_team, zone_fn, my_team)
        trips = _trips(frames, pos, zone_fn, opp["pid"], my_lane, my_team, dead_at)
        for tr in trips:
            # what did I do while the opponent was away?
            followed = any(lane_of(_zone_at(pos, zone_fn, me["pid"], m * 60000, my_team) or "") not in (my_lane, None)
                           for m in range(tr["start"], tr["end"] + 1))
            f0 = frames[max(0, tr["start"] - 1)]["participantFrames"][str(me["pid"])]
            f1 = frames[min(len(frames) - 1, tr["end"] + 1)]["participantFrames"][str(me["pid"])]
            cs = (f1["minionsKilled"] - f0["minionsKilled"]) / max(1, tr["end"] - tr["start"] + 2)
            tr["got_kill"] = any(tr["start"] * 60 - 60 <= s["t"] <= tr["end"] * 60 + 60 for s in success)
            tr["response"] = "followed" if followed else ("farmed" if cs >= 7 else "nothing")
            tr["my_cs_per_min"] = round(cs, 1)
        out["opp"] = {"lane": my_lane, "success": success, "trips": trips}
        mine_success = _kills_away(events, me["pid"], my_lane, team_of, my_team, zone_fn, enemy_team)
        mine_trips = _trips(frames, pos, zone_fn, me["pid"], my_lane, my_team, dead_at)
        out["mine"] = {"success": mine_success, "trips": mine_trips}

    if me["role"] == "JUNGLE":
        ganks = {l: 0 for l in LANES}
        for e in events:
            if e["type"] != "CHAMPION_KILL" or e["timestamp"] > END_MIN * 60000 or not e.get("position"):
                continue
            if me["pid"] != e.get("killerId") and me["pid"] not in (e.get("assistingParticipantIds") or []):
                continue
            l = lane_of(zone_fn(e["position"]["x"], e["position"]["y"], my_team))
            if l and team_of.get(e.get("victimId")) == enemy_team:
                ganks[l] += 1
        out["mine"] = {"ganks": ganks, "success": [], "trips": []}

    if ejg:
        kills = {l: 0 for l in LANES + ("JG",)}
        for e in events:
            if e["type"] != "CHAMPION_KILL" or e["timestamp"] > END_MIN * 60000 or not e.get("position"):
                continue
            if ejg["pid"] != e.get("killerId") and ejg["pid"] not in (e.get("assistingParticipantIds") or []):
                continue
            if team_of.get(e.get("victimId")) != my_team:
                continue
            l = lane_of(zone_fn(e["position"]["x"], e["position"]["y"], my_team)) or "JG"
            kills[l] += 1
        visits = {l: 0 for l in LANES}
        for m in range(2, min(END_MIN, len(frames))):
            l = lane_of(_zone_at(pos, zone_fn, ejg["pid"], m * 60000, my_team) or "")
            if l:
                visits[l] += 1
        out["enemy_jg"] = {"kills": kills, "visits": visits}
    return out
