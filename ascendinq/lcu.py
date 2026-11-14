"""Read match data from the local League client (no Riot API key needed).

The client exposes a local HTTPS API (the "LCU"), authenticated with a
password from its lockfile. Match history there uses the older v4 layout,
so it is converted to the Match-V5 shape the analyzer expects.
Player roles come from the replay file (.rofl) when it exists, otherwise
they are inferred from early-game positions.
"""
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
import urllib3

from . import ddragon

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SR_QUEUES = {400, 420, 430, 440, 490, 480}  # Summoner's Rift modes worth reviewing
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class ClientNotRunning(Exception):
    pass


# ---------------------------------------------------------------- connection

def _install_dirs():
    env = os.getenv("LEAGUE_DIR")
    if env:
        yield Path(env)
    meta = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData")) / "Riot Games" / "Metadata" / \
        "league_of_legends.live" / "league_of_legends.live.product_settings.yaml"
    try:
        m = re.search(r'product_install_full_path:\s*"?([^"\n]+)', meta.read_text(encoding="utf-8"))
        if m:
            yield Path(m.group(1).strip())
    except OSError:
        pass
    for drive in "CDEFG":
        yield Path(f"{drive}:/Riot Games/League of Legends")


def _from_process():
    """Fallback: read port/token from the running client's command line."""
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe'\").CommandLine"],
            capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    port = re.search(r"--app-port=(\d+)", out)
    token = re.search(r"--remoting-auth-token=([\w-]+)", out)
    return (int(port.group(1)), token.group(1)) if port and token else None


class LCU:
    def __init__(self, port: int, password: str):
        self.base = f"https://127.0.0.1:{port}"
        auth = base64.b64encode(f"riot:{password}".encode()).decode()
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Basic {auth}"
        self.s.verify = False

    @classmethod
    def connect(cls) -> "LCU":
        for d in _install_dirs():
            lock = d / "lockfile"
            try:
                parts = lock.read_text(encoding="utf-8").split(":")
                c = cls(int(parts[2]), parts[3])
                c.get("/lol-summoner/v1/current-summoner")
                return c
            except (OSError, IndexError, ValueError, requests.RequestException, ClientNotRunning):
                continue
        hit = _from_process()
        if hit:
            c = cls(*hit)
            try:
                c.get("/lol-summoner/v1/current-summoner")
                return c
            except (requests.RequestException, ClientNotRunning):
                pass
        raise ClientNotRunning("LoL クライアントが見つかりません。LoL を起動してログインしてから、もう一度試してください。")

    def get(self, path, **params):
        r = self.s.get(self.base + path, params=params or None, timeout=20)
        if r.status_code != 200:
            raise ClientNotRunning(f"クライアントからの取得に失敗しました（HTTP {r.status_code}: {path}）")
        return r.json()

    # ------------------------------------------------------------ data
    def me(self) -> dict:
        s = self.get("/lol-summoner/v1/current-summoner")
        name = s.get("gameName") or s.get("displayName", "")
        tag = s.get("tagLine", "")
        return {"puuid": s["puuid"], "riot_id": f"{name}#{tag}" if tag else name}

    def platform(self) -> str:
        try:
            return self.get("/riotclient/region-locale").get("platformId", "JP1") or "JP1"
        except (ClientNotRunning, requests.RequestException):
            return "JP1"

    def recent_games(self, puuid: str, n: int = 20) -> list:
        d = self.get(f"/lol-match-history/v1/products/lol/{puuid}/matches", begIndex=0, endIndex=n - 1)
        games = d.get("games", {}).get("games", [])
        return [g for g in games if g.get("mapId") == 11 and g.get("queueId") in SR_QUEUES]

    def game(self, game_id: int) -> dict:
        return self.get(f"/lol-match-history/v1/games/{game_id}")

    def timeline(self, game_id: int) -> dict:
        return self.get(f"/lol-match-history/v1/game-timelines/{game_id}")


# ---------------------------------------------------------------- roles

def rofl_positions(platform: str, game_id: int) -> dict:
    """{puuid: TEAM_POSITION} from the saved replay, if any."""
    path = Path.home() / "Documents" / "League of Legends" / "Replays" / f"{platform.upper()}-{game_id}.rofl"
    try:
        with open(path, "rb") as f:
            head = f.read(400_000)
        i = head.find(b'{"gameLength"')
        j = head.find(b'}]"}', i)
        stats = json.loads(json.loads(head[i:j + 4].decode("utf-8", "replace"))["statsJson"])
        return {p["PUUID"]: p.get("TEAM_POSITION", "") for p in stats if p.get("PUUID")}
    except (OSError, ValueError, KeyError):
        return {}


def infer_roles(participants: list, frames: list) -> dict:
    """Guess TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY from early positions and farm."""
    def frame(m):
        return frames[min(m, len(frames) - 1)]["participantFrames"] if frames else {}

    roles = {}
    for team in (100, 200):
        ids = [p["participantId"] for p in participants if p["teamId"] == team]
        f10 = frame(10)
        stat = lambda pid, k: f10.get(str(pid), {}).get(k, 0)
        jungler = max(ids, key=lambda pid: stat(pid, "jungleMinionsKilled"))
        roles[jungler] = "JUNGLE"
        lane_score = {}
        for pid in ids:
            if pid == jungler:
                continue
            pts = [frame(m).get(str(pid), {}).get("position") for m in range(2, 11)]
            pts = [p for p in pts if p]
            if not pts:
                lane_score[pid] = "MIDDLE"
                continue
            x = sum(p["x"] for p in pts) / len(pts)
            y = sum(p["y"] for p in pts) / len(pts)
            if abs(x - y) < 2500:
                lane_score[pid] = "MIDDLE"
            elif y > x:
                lane_score[pid] = "TOP"
            else:
                lane_score[pid] = "BOT"
        bots = [pid for pid, l in lane_score.items() if l == "BOT"]
        bots.sort(key=lambda pid: stat(pid, "minionsKilled"), reverse=True)
        for i, pid in enumerate(bots):
            roles[pid] = "BOTTOM" if i == 0 else "UTILITY"
        for pid, l in lane_score.items():
            if l in ("TOP", "MIDDLE") and l not in [roles.get(o) for o in ids]:
                roles[pid] = l
        left = [r for r in ("TOP", "MIDDLE", "BOTTOM", "UTILITY") if r not in [roles.get(o) for o in ids]]
        for pid in ids:
            if pid not in roles and left:
                roles[pid] = left.pop(0)
    return roles


# ---------------------------------------------------------------- v4 -> v5

def to_v5(game: dict, timeline: dict, game_start_ms: int | None = None):
    platform = (game.get("platformId") or "JP1").upper()
    gid = game["gameId"]
    match_id = f"{platform}_{gid}"
    names = ddragon.champion_ids()
    idents = {pi["participantId"]: pi.get("player", {}) for pi in game.get("participantIdentities", [])}
    frames = timeline.get("frames", [])
    for f in frames:  # normalise participantFrames keys to strings
        f["participantFrames"] = {str(k): v for k, v in f.get("participantFrames", {}).items()}
    roles_rofl = rofl_positions(platform, gid)
    roles_guess = infer_roles(game["participants"], frames)

    parts = []
    team_of = {}
    for p in game["participants"]:
        pid = p["participantId"]
        st = p.get("stats", {})
        pl = idents.get(pid, {})
        puuid = pl.get("puuid", f"unknown-{pid}")
        team_of[pid] = p["teamId"]
        parts.append({
            "participantId": pid,
            "puuid": puuid,
            "teamId": p["teamId"],
            "championName": names.get(p["championId"], str(p["championId"])),
            "riotIdGameName": pl.get("gameName") or pl.get("summonerName", ""),
            "teamPosition": roles_rofl.get(puuid) or roles_guess.get(pid, ""),
            "kills": st.get("kills", 0), "deaths": st.get("deaths", 0), "assists": st.get("assists", 0),
            "totalMinionsKilled": st.get("totalMinionsKilled", 0),
            "neutralMinionsKilled": st.get("neutralMinionsKilled", 0),
            "win": bool(st.get("win")),
            "visionScore": st.get("visionScore", 0),
            "wardsPlaced": st.get("wardsPlaced", 0),
            "visionWardsBoughtInGame": st.get("visionWardsBoughtInGame", 0),
            "totalDamageDealtToChampions": st.get("totalDamageDealtToChampions", 0),
            "goldEarned": st.get("goldEarned", 0),
            "gameEndedInEarlySurrender": bool(st.get("gameEndedInEarlySurrender")),
            **{f"item{k}": st.get(f"item{k}", 0) for k in range(7)},
        })

    for f in frames:
        for e in f.get("events", []):
            if e.get("type") == "ELITE_MONSTER_KILL" and "killerTeamId" not in e:
                e["killerTeamId"] = team_of.get(e.get("killerId"), 0)

    match = {
        "metadata": {"matchId": match_id, "source": "client"},
        "info": {
            "gameId": gid,
            "queueId": game.get("queueId"),
            "gameDuration": game.get("gameDuration", 0),
            "gameCreation": game.get("gameCreation"),
            "gameStartTimestamp": game_start_ms or game.get("gameCreation"),
            "participants": parts,
        },
    }
    return match, {"metadata": {"matchId": match_id}, "info": {"frames": frames}}
