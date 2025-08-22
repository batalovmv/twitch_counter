from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Dict, Callable

from bot.util.time import utcnow, month_key

class AccrualService:
    """
    Каждые tick_interval_sec начисляет +1 минуту всем, кто писал в чат за последние active_window_sec.
    """
    def __init__(
        self,
        store,
        tick_interval_sec: int,
        active_window_sec: int,
        should_accrue: Callable[[], bool] | None = None,
    ) -> None:
        self.store = store
        self.tick_interval_sec = tick_interval_sec
        self.active_window_sec = active_window_sec
        self.should_accrue = should_accrue or (lambda: True)

        self.last_seen: Dict[str, datetime] = {}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def mark_active(self, username: str) -> None:
        if username:
            self.last_seen[username] = utcnow()

    async def start(self) -> None:
        if self._task:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                await asyncio.sleep(self.tick_interval_sec)
                await self._accrue_once()
        except asyncio.CancelledError:
            pass

    async def _accrue_once(self) -> None:
        if not self.should_accrue():
            return  # эфир не идёт

        now = utcnow().timestamp()
        cutoff = now - self.active_window_sec
        active = [u for u, ts in list(self.last_seen.items()) if ts.timestamp() >= cutoff]
        if not active:
            return
        mkey = month_key()
        for u in active:
            await self.store.add_minutes(mkey, u, 1)
