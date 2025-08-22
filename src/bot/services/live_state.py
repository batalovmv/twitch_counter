from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

class TwitchLiveChecker:
    """
    Периодически опрашивает Helix: streams?user_login=<channel>
    Держит флаг is_live. Токен обновляет сам (app access token).
    """
    def __init__(self, client_id: str, client_secret: str, channel_login: str, poll_seconds: int = 60) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.channel_login = channel_login.lower().lstrip("#")
        self.poll_seconds = max(15, int(poll_seconds))

        self._is_live: bool = False
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        self._app_token: Optional[str] = None
        self._app_token_exp: float = 0.0  # epoch seconds
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_live(self) -> bool:
        return self._is_live

    async def start(self) -> None:
        if self._task:
            return
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        if self._session:
            await self._session.close()

    async def _loop(self) -> None:
        try:
            # Первичная проверка раньше, чем спать
            await self._refresh_once()
            while not self._stop.is_set():
                await asyncio.sleep(self.poll_seconds)
                await self._refresh_once()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("LiveChecker loop failed")

    async def _ensure_token(self) -> str:
        now = time.time()
        if self._app_token and now < self._app_token_exp - 60:
            return self._app_token

        assert self._session is not None
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        async with self._session.post(url, params=params) as resp:
            if resp.status != 200:
                txt = await resp.text()
                raise RuntimeError(f"Failed to get app token: {resp.status} {txt}")
            data = await resp.json()
        self._app_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._app_token_exp = now + expires_in
        log.info("Obtained Twitch app token, expires in ~%ss", expires_in)
        return self._app_token

    async def _refresh_once(self) -> None:
        try:
            token = await self._ensure_token()
            assert self._session is not None
            url = "https://api.twitch.tv/helix/streams"
            headers = {
                "Client-Id": self.client_id,
                "Authorization": f"Bearer {token}",
            }
            params = {"user_login": self.channel_login}
            async with self._session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    txt = await resp.text()
                    log.warning("Helix streams failed: %s %s", resp.status, txt)
                    return
                data = await resp.json()
            live = bool(data.get("data"))  # если массив непустой — стрим в онлайне
            if live != self._is_live:
                self._is_live = live
                log.info("Stream live state changed: %s", "LIVE" if live else "OFFLINE")
        except Exception:
            log.exception("Failed to refresh live state")
