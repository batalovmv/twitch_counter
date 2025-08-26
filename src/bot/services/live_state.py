from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional, Callable, Dict, Any

import aiohttp

log = logging.getLogger(__name__)

class TwitchLiveChecker:
    """
    Периодически опрашивает Helix streams + games.
    Держит флаг is_live и dict stream_info.
    Вызывает on_change(stream_info|None) при переходах или изменениях.
    """
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        channel_login: str,
        poll_seconds: int = 60,
        on_change: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.channel_login = channel_login.lower().lstrip("#")
        self.poll_seconds = max(15, int(poll_seconds))

        self._is_live: bool = False
        self._info: Optional[Dict[str, Any]] = None  # {title, game_id, game_name, viewer_count, started_at, url}
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._on_change = on_change

        self._app_token: Optional[str] = None
        self._app_token_exp: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def stream_info(self) -> Optional[Dict[str, Any]]:
        return self._info

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
            txt = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Get app token failed: {resp.status} {txt}")
            data = await resp.json()
        self._app_token = data["access_token"]
        self._app_token_exp = now + int(data.get("expires_in", 3600))
        log.info("Obtained Twitch app token.")
        return self._app_token

    async def _refresh_once(self) -> None:
        try:
            token = await self._ensure_token()
            assert self._session is not None
            streams_url = "https://api.twitch.tv/helix/streams"
            headers = {"Client-Id": self.client_id, "Authorization": f"Bearer {token}"}
            params = {"user_login": self.channel_login}
            async with self._session.get(streams_url, headers=headers, params=params) as resp:
                data = await resp.json()
                if resp.status != 200:
                    log.warning("Helix streams failed: %s %s", resp.status, data)
                    return

            if not data.get("data"):
                # оффлайн
                changed = self._is_live
                self._is_live = False
                self._info = None
                if changed and self._on_change:
                    self._on_change(None)
                return

            s = data["data"][0]
            game_name = ""
            game_id = s.get("game_id") or ""
            if game_id:
                games_url = "https://api.twitch.tv/helix/games"
                async with self._session.get(games_url, headers=headers, params={"id": game_id}) as r2:
                    gdata = await r2.json()
                    if r2.status == 200 and gdata.get("data"):
                        game_name = gdata["data"][0].get("name", "")

            info = {
                "title": s.get("title", ""),
                "game_id": game_id,
                "game_name": game_name,
                "viewer_count": int(s.get("viewer_count", 0)),
                "started_at": s.get("started_at", ""),
                "url": f"https://twitch.tv/{self.channel_login}",
            }

            changed = (not self._is_live) or (self._info != info)
            self._is_live = True
            self._info = info
            if changed and self._on_change:
                self._on_change(info)

        except Exception:
            log.exception("Failed to refresh live state")
