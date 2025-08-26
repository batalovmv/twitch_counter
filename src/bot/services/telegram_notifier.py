from __future__ import annotations
import html
import logging
import asyncio
from typing import Optional, Dict, Any

import aiohttp

log = logging.getLogger(__name__)

class TelegramNotifier:
    """
    Публикует/обновляет одно сообщение в Telegram-канале про стрим.
    При завершении стрима удаляет пост из канала.
    Создаёт НОВОЕ сообщение для КАЖДОГО нового стрима (по started_at).
    Требуется: бот добавлен в канал и является администратором.
    """

    def __init__(self, bot_token: str, chat_id: str, parse_mode: str = "HTML", disable_preview: bool = True) -> None:
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self.parse_mode = parse_mode
        self.disable_preview = disable_preview

        self._session: Optional[aiohttp.ClientSession] = None
        self._message_id: Optional[int] = None
        self._last_payload: Optional[str] = None
        self._stream_tag: Optional[str] = None  # хранит started_at текущей сессии
        self._lock = asyncio.Lock()  # сериализация операций пост/эдит/делит

    async def start(self) -> None:
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _fmt(self, info: Dict[str, Any]) -> str:
        title = html.escape(info.get("title") or "")
        game = html.escape(info.get("game_name") or "Unknown")
        viewers = int(info.get("viewer_count") or 0)
        url = html.escape(info.get("url") or "#")

        lines = [
            "🎥 <b>Стрим начался!</b>",
            f"🎮 Игра: <b>{game}</b>",
            f"👀 Зрителей: <b>{viewers}</b>",
            f"📝 Заголовок: <i>{title}</i>",
            "",
            f"👉 <a href=\"{url}\">Смотреть на Twitch</a>",
        ]
        return "\n".join(lines)

    async def _send(self, text: str) -> None:
        assert self._session is not None
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": self.disable_preview,
        }
        async with self._session.post(f"{self.base}/sendMessage", json=payload) as resp:
            data = await resp.json()
            if resp.status != 200 or not data.get("ok"):
                log.warning("sendMessage failed: %s %s", resp.status, data)
                return
            self._message_id = data["result"]["message_id"]
            self._last_payload = text

    async def _edit(self, text: str) -> None:
        assert self._session is not None
        if self._message_id is None:
            await self._send(text)
            return
        if text == self._last_payload:
            return
        payload = {
            "chat_id": self.chat_id,
            "message_id": self._message_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": self.disable_preview,
        }
        async with self._session.post(f"{self.base}/editMessageText", json=payload) as resp:
            data = await resp.json()
            if resp.status != 200 or not data.get("ok"):
                # если сообщение исчезло — создаём заново
                log.warning("editMessageText failed, will repost: %s %s", resp.status, data)
                self._message_id = None
                self._last_payload = None
                await self._send(text)
                return
            self._last_payload = text

    async def _delete(self) -> None:
        # Сбрасываем локальное состояние СРАЗУ, чтобы параллельный апдейт не редактировал старый пост
        mid = self._message_id
        self._message_id = None
        self._last_payload = None

        if mid is None or self._session is None:
            return
        payload = {
            "chat_id": self.chat_id,
            "message_id": mid,
        }
        async with self._session.post(f"{self.base}/deleteMessage", json=payload) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}
            if resp.status != 200 or not data.get("ok", True):
                log.warning("deleteMessage failed: %s %s", resp.status, data)

    async def on_stream_update(self, info: Optional[Dict[str, Any]]) -> None:
        """
        Вызывается при изменениях: онлайн/оффлайн/смена игры/заголовка/зрителей.
        - info = None (оффлайн): удаляем пост и сбрасываем тег сессии.
        - info != None (онлайн): если started_at изменился — создаём новое сообщение.
        """
        await self.start()
        async with self._lock:
            if info is None:
                await self._delete()
                self._stream_tag = None
                return

            # новый стрим? сравним started_at
            tag = (info.get("started_at") or "").strip()
            if tag and tag != self._stream_tag:
                # новая сессия → гарантированно создаём НОВОЕ сообщение
                self._stream_tag = tag
                self._message_id = None
                self._last_payload = None

            text = self._fmt(info)
            # при той же сессии просто редактируем текст
            if self._message_id is None:
                await self._send(text)
            else:
                await self._edit(text)
