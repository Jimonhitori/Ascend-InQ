"""Builders for synthetic (fake) Match-V5 matches/timelines and v4-style client games.

All names / PUUIDs are fake. Participant layout:
  team 100: 1 TOP, 2 JUNGLE, 3 MIDDLE (= me), 4 BOTTOM, 5 UTILITY
  team 200: 6 TOP, 7 JUNGLE, 8 MIDDLE, 9 BOTTOM, 10 UTILITY
"""
import copy

ME_PID = 3
ME_PUUID = "puuid-fake-0003"
ME_NAME = "Tester"
ME_RIOT_ID = "Tester#JP1"
GAME_START_MS = 1_790_000_000_000

ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

# (championName, numeric key, Japanese name)
CHAMPIONS = [
    ("Garen", 86, "ガレン"), ("XinZhao", 5, "シン・ジャオ"), ("Anivia", 34, "アニビア"),
    ("Jinx", 222, "ジンクス"), ("Thresh", 412, "スレッシュ"),
    ("Darius", 122, "ダリウス"), ("LeeSin", 64, "リー・シン"), ("Zed", 238, "ゼド"),
    ("Caitlyn", 51, "ケイトリン"), ("Lulu", 117, "ルル"),
]

# rough laning positions per (team, role)
POS = {
    (100, "TOP"): (1500, 10000), (100, "JUNGLE"): (4000, 7000), (100, "MIDDLE"): (6500, 6500),
    (100, "BOTTOM"): (10000, 1500), (100, "UTILITY"): (10200, 1700),
    (200, "TOP"): (1800, 11000), (200, "JUNGLE"): (10500, 8000), (200, "MIDDLE"): (8000, 8000),
    (200, "BOTTOM"): (12500, 4000), (200, "UTILITY"): (12600, 4200),
}


def pid_info(pid):
    team = 100 if pid <= 5 else 200
    role = ROLES[(pid - 1) % 5]
    return team, role


def _cs_per_min(pid, role):
    if pid == ME_PID:
        return 6          # 60 CS at 10:00 -> below the MID target of 70
    return {"JUNGLE": 1, "UTILITY": 1}.get(role, 7)


def _participant_frame(pid, minute):
    team, role = pid_info(pid)
    x, y = POS[(team, role)]
    return {
        "participantId": pid,
        "position": {"x": x, "y": y},
        "minionsKilled": _cs_per_min(pid, role) * minute,
        "jungleMinionsKilled": 5 * minute if role == "JUNGLE" else 0,
        "totalGold": 500 + 350 * minute + (0 if pid == ME_PID else 20 * minute),
        "xp": 400 * minute,
        "level": min(18, 1 + minute // 2),
    }


def _events():
    """Events keyed by minute index of the frame they belong to."""
    ev = {}

    def add(e):
        ev.setdefault(e["timestamp"] // 60000, []).append(e)

    # --- my deaths
    # 5:30 gank in pushed mid: enemy mid kills, enemy jungler assists
    add({"type": "CHAMPION_KILL", "timestamp": 330_000, "victimId": ME_PID, "killerId": 8,
         "assistingParticipantIds": [7], "position": {"x": 8800, "y": 8800}, "bounty": 300})
    # 12:00 solo kill by lane opponent at mid center
    add({"type": "CHAMPION_KILL", "timestamp": 720_000, "victimId": ME_PID, "killerId": 8,
         "assistingParticipantIds": [], "position": {"x": 7400, "y": 7400}, "bounty": 300})
    # 22:00 caught alone in the river by three enemies
    add({"type": "CHAMPION_KILL", "timestamp": 1_320_000, "victimId": ME_PID, "killerId": 6,
         "assistingParticipantIds": [9, 10], "position": {"x": 4500, "y": 10000}, "bounty": 300})
    # a kill I get on the enemy mid
    add({"type": "CHAMPION_KILL", "timestamp": 480_000, "victimId": 8, "killerId": ME_PID,
         "assistingParticipantIds": [], "position": {"x": 7000, "y": 7000}, "bounty": 300})

    # --- objectives
    for t in (360_000, 390_000, 420_000):  # 3 grubs within 90 s -> one objective
        add({"type": "ELITE_MONSTER_KILL", "timestamp": t, "monsterType": "HORDE",
             "killerId": 7, "killerTeamId": 200, "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 10500}})
    add({"type": "ELITE_MONSTER_KILL", "timestamp": 540_000, "monsterType": "DRAGON",
         "monsterSubType": "FIRE_DRAGON", "killerId": 2, "killerTeamId": 100,
         "assistingParticipantIds": [ME_PID], "position": {"x": 9800, "y": 4400}})
    add({"type": "ELITE_MONSTER_KILL", "timestamp": 1_000_000, "monsterType": "DRAGON",
         "monsterSubType": "WATER_DRAGON", "killerId": 7, "killerTeamId": 200,
         "assistingParticipantIds": [9, 10], "position": {"x": 9800, "y": 4400}})

    # --- towers / plates
    add({"type": "BUILDING_KILL", "timestamp": 840_000, "buildingType": "TOWER_BUILDING",
         "teamId": 200, "laneType": "MID_LANE", "towerType": "OUTER_TURRET",
         "killerId": ME_PID, "assistingParticipantIds": [], "position": {"x": 8955, "y": 8510}})
    add({"type": "TURRET_PLATE_DESTROYED", "timestamp": 600_000, "teamId": 200,
         "laneType": "MID_LANE", "killerId": ME_PID, "position": {"x": 8955, "y": 8510}})

    # --- wards (mine) and items
    for t in (150_000, 310_000):
        add({"type": "WARD_PLACED", "timestamp": t, "creatorId": ME_PID, "wardType": "YELLOW_TRINKET"})
    add({"type": "ITEM_PURCHASED", "timestamp": 5_000, "participantId": ME_PID, "itemId": 1056})
    add({"type": "ITEM_PURCHASED", "timestamp": 500_000, "participantId": ME_PID, "itemId": 3020})
    add({"type": "ITEM_PURCHASED", "timestamp": 900_000, "participantId": ME_PID, "itemId": 3089})
    add({"type": "ITEM_PURCHASED", "timestamp": 1_200_000, "participantId": ME_PID, "itemId": 3157})
    add({"type": "ITEM_UNDO", "timestamp": 1_201_000, "participantId": ME_PID, "beforeId": 3157, "afterId": 0})
    return ev


def build_match(n_frames=28, duration=None, wards=True, items=True, remake_flag=False):
    """Return (match, timeline) in Match-V5 shape."""
    duration = duration if duration is not None else n_frames * 60
    participants = []
    for pid in range(1, 11):
        team, role = pid_info(pid)
        champ, _key, _ja = CHAMPIONS[pid - 1]
        p = {
            "participantId": pid, "puuid": ME_PUUID if pid == ME_PID else f"puuid-fake-{pid:04d}",
            "riotIdGameName": ME_NAME if pid == ME_PID else f"Bot{pid}",
            "championName": champ, "teamId": team, "teamPosition": role,
            "kills": 1 if pid in (ME_PID, 6, 8) else 0, "deaths": 3 if pid == ME_PID else 1,
            "assists": 2 if team == 100 else 1,
            "totalMinionsKilled": 150, "neutralMinionsKilled": 10,
            "win": team == 200, "visionScore": 12, "wardsPlaced": 6,
            "visionWardsBoughtInGame": 0, "totalDamageDealtToChampions": 15000,
            "goldEarned": 9000, "gameEndedInEarlySurrender": remake_flag,
            **{f"item{k}": 0 for k in range(7)},
        }
        if pid == ME_PID:
            p.update(item0=3089, item1=3020, item2=1056, item6=3340)
        participants.append(p)

    ev = _events()
    frames = []
    for m in range(n_frames):
        events = [e for e in ev.get(m, [])
                  if (wards or e["type"] != "WARD_PLACED")
                  and (items or e["type"] not in ("ITEM_PURCHASED", "ITEM_UNDO"))]
        frames.append({
            "timestamp": m * 60_000,
            "participantFrames": {str(pid): _participant_frame(pid, m) for pid in range(1, 11)},
            "events": copy.deepcopy(events),
        })

    match = {
        "metadata": {"matchId": "JP1_1000000001"},
        "info": {"gameId": 1000000001, "queueId": 420, "gameDuration": duration,
                 "gameCreation": GAME_START_MS - 60_000, "gameStartTimestamp": GAME_START_MS,
                 "participants": participants},
    }
    return match, {"metadata": {"matchId": "JP1_1000000001"}, "info": {"frames": frames}}


def build_client_game(n_frames=15):
    """Return (game, timeline) in the League client's v4 layout (int frame keys, no killerTeamId)."""
    participants, idents = [], []
    for pid in range(1, 11):
        team, _role = pid_info(pid)
        _champ, key, _ja = CHAMPIONS[pid - 1]
        participants.append({
            "participantId": pid, "teamId": team, "championId": key,
            "stats": {"kills": 1, "deaths": 1, "assists": 1, "totalMinionsKilled": 100,
                      "neutralMinionsKilled": 5, "win": team == 100, "visionScore": 10,
                      "item0": 3089, "item1": 3020, "item2": 0, "item3": 0,
                      "item4": 0, "item5": 0, "item6": 3340},
        })
        idents.append({"participantId": pid,
                       "player": {"puuid": f"client-puuid-{pid:04d}",
                                  "gameName": ME_NAME if pid == ME_PID else f"Bot{pid}"}})
    game = {"gameId": 2000000002, "platformId": "JP1", "gameCreation": GAME_START_MS,
            "gameDuration": n_frames * 60, "queueId": 420, "mapId": 11,
            "participants": participants, "participantIdentities": idents}

    frames = []
    for m in range(n_frames):
        pf = {}
        for pid in range(1, 11):
            f = _participant_frame(pid, m)
            team, role = pid_info(pid)
            if role == "BOTTOM":
                f["minionsKilled"] = 8 * m
            elif role == "UTILITY":
                f["minionsKilled"] = 1 * m
            pf[pid] = f  # int keys, as the client returns them
        events = []
        if m == 6:
            events.append({"type": "ELITE_MONSTER_KILL", "timestamp": 361_000, "monsterType": "HORDE",
                           "killerId": 7, "position": {"x": 5000, "y": 10500}})
        if m == 9:
            events.append({"type": "ELITE_MONSTER_KILL", "timestamp": 541_000, "monsterType": "DRAGON",
                           "monsterSubType": "FIRE_DRAGON", "killerId": 2,
                           "position": {"x": 9800, "y": 4400}})
        frames.append({"timestamp": m * 60_000, "participantFrames": pf, "events": events})
    return game, {"frames": frames}
