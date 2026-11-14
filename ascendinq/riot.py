"""Minimal Riot API client with rate limiting (dev key: 20/1s, 100/2min)."""
import collections
import time
from urllib.parse import quote

import requests


class RiotAPIError(Exception):
    pass


class KeyExpiredError(RiotAPIError):
    pass


class NotFoundError(RiotAPIError):
    pass


class RateLimiter:
    def __init__(self, limits=((20, 1.0), (100, 120.0))):
        self.limits = limits
        self.calls = collections.deque()
        self.max_window = max(w for _, w in limits)

    def wait(self):
        while True:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > self.max_window:
                self.calls.popleft()
            sleep_for = 0.0
            for n, window in self.limits:
                recent = [t for t in self.calls if now - t < window]
                if len(recent) >= n:
                    sleep_for = max(sleep_for, window - (now - recent[-n]) + 0.05)
            if sleep_for <= 0:
                self.calls.append(now)
                return
            if sleep_for > 3:
                print(f"  (レート制限のため {sleep_for:.0f} 秒待機)")
            time.sleep(sleep_for)


class RiotClient:
    def __init__(self, api_key: str, region: str = "asia", platform: str = "jp1", account_region: str | None = None):
        self.region_url = f"https://{region}.api.riotgames.com"
        self.account_url = f"https://{account_region or region}.api.riotgames.com"
        self.platform_url = f"https://{platform}.api.riotgames.com"
        self.session = requests.Session()
        self.session.headers["X-Riot-Token"] = api_key
        self.limiter = RateLimiter()

    def _get(self, url: str, params=None):
        for attempt in range(6):
            self.limiter.wait()
            try:
                r = self.session.get(url, params=params, timeout=20)
            except requests.RequestException as e:
                if attempt == 5:
                    raise RiotAPIError(f"通信エラー: {e.__class__.__name__}") from None
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                print(f"  (429: Riot側のレート制限。{wait} 秒待機)")
                time.sleep(wait + 0.5)
                continue
            if r.status_code in (401, 403):
                raise KeyExpiredError(
                    f"APIキーが無効か失効しています (HTTP {r.status_code})。"
                    "開発用キーは24時間で失効します。developer.riotgames.com で再発行して .env を更新してください。"
                )
            if r.status_code == 404:
                raise NotFoundError(f"見つかりません: {url.split('.com', 1)[-1]}")
            if r.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise RiotAPIError(f"HTTP {r.status_code}: {url.split('.com', 1)[-1]}")
        raise RiotAPIError("リトライ上限に達しました")

    def account_by_riot_id(self, game_name: str, tag: str) -> dict:
        return self._get(
            f"{self.account_url}/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name, safe='')}/{quote(tag, safe='')}"
        )

    def match_ids(self, puuid: str, queue: int = 420, count: int = 10, start: int = 0) -> list:
        return self._get(
            f"{self.region_url}/lol/match/v5/matches/by-puuid/{puuid}/ids",
            params={"queue": queue, "count": count, "start": start},
        )

    def match(self, match_id: str) -> dict:
        return self._get(f"{self.region_url}/lol/match/v5/matches/{match_id}")

    def timeline(self, match_id: str) -> dict:
        return self._get(f"{self.region_url}/lol/match/v5/matches/{match_id}/timeline")
