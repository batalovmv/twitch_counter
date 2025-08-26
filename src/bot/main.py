from __future__ import annotations
import argparse
import asyncio
import logging
import os
from pathlib import Path
from bot.services.live_state import TwitchLiveChecker
from src.bot.services.telegram_notifier import TelegramNotifier
try:
    import uvloop  # type: ignore
    uvloop.install()
except Exception:
    pass

from dotenv import load_dotenv, find_dotenv

from bot.config import Config
from bot.data.store_ydb import WatchtimeStoreYDB
from bot.services.accrual import AccrualService
from bot.services.twitch_bot import StreamStatsBot

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stream Stats Bot (YDB)")
    p.add_argument("--version", action="store_true", help="print version and exit")
    return p.parse_args()

def load_env() -> None:
    dotenv_path = os.getenv("DOTENV_PATH")
    if dotenv_path and Path(dotenv_path).exists():
        load_dotenv(dotenv_path)
        return
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found)
        return
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.exists():
        load_dotenv(root_env.as_posix())

async def _run() -> None:
    load_env()
    cfg = Config.load()

    if cfg.db_provider != "ydb":
        raise RuntimeError("This build supports only DB_PROVIDER=ydb")

    store = WatchtimeStoreYDB(endpoint=cfg.ydb_endpoint, database=cfg.ydb_database)
    await store.init()
    
    tg_token = os.getenv("TG_BOT_TOKEN")
    tg_chat = os.getenv("TG_CHAT_ID")
    tg_mode = os.getenv("TG_PARSE_MODE", "HTML")
    tg_disable_prev = os.getenv("TG_DISABLE_WEB_PAGE_PREVIEW", "1") == "1"
    notifier: TelegramNotifier | None = None
    if tg_token and tg_chat:
        notifier = TelegramNotifier(tg_token, tg_chat, parse_mode=tg_mode, disable_preview=tg_disable_prev)
        await notifier.start()

    # live checker с колбэком
    async def _on_live_change(info):
        if notifier:
            await notifier.on_stream_update(info)

    live_checker = TwitchLiveChecker(
        client_id=cfg.twitch_client_id,
        client_secret=cfg.twitch_client_secret,
        channel_login=cfg.channel,
        poll_seconds=cfg.live_poll_seconds,
        on_change=lambda info: asyncio.create_task(_on_live_change(info)),
    )
    await live_checker.start()

    accrual = AccrualService(
        store=store,
        tick_interval_sec=cfg.tick_interval_sec,
        active_window_sec=cfg.active_window_sec,
        should_accrue=lambda: live_checker.is_live,
    )

    bot = StreamStatsBot(
        token=cfg.oauth_token,
        nick=cfg.bot_username,
        channel=cfg.channel,
        default_top_n=cfg.default_top_n,
        store=store,
        accrual=accrual,
    )

    try:
        await bot.start()
    finally:
        await accrual.stop()
        await live_checker.stop()
        if notifier:
            await notifier.stop()
        await store.close()

def main() -> None:
    args = parse_args()
    if args.version:
        print("stream-stats-bot-ydb 1.0.0")
        return
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
