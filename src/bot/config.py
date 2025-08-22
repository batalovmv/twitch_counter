from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    # Twitch
    bot_username: str
    oauth_token: str
    channel: str

    # Bot
    default_top_n: int
    tick_interval_sec: int
    active_window_sec: int

    # Storage
    db_provider: str  # "ydb"
    # YDB
    ydb_endpoint: str
    ydb_database: str

    # Live check
    twitch_client_id: str
    twitch_client_secret: str
    live_poll_seconds: int

    @staticmethod
    def _int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except Exception:
            return default

    @staticmethod
    def load() -> "Config":
        return Config(
            bot_username=os.environ["TWITCH_BOT_USERNAME"].strip(),
            oauth_token=os.environ["TWITCH_OAUTH_TOKEN"].strip(),
            channel=os.environ["TWITCH_CHANNEL"].strip().lstrip("#"),
            default_top_n=Config._int("BOT_DEFAULT_TOPN", 3),
            tick_interval_sec=Config._int("TICK_INTERVAL_MINUTES", 1) * 60,
            active_window_sec=Config._int("ACTIVE_WINDOW_MINUTES", 5) * 60,
            db_provider=os.getenv("DB_PROVIDER", "ydb").strip().lower(),
            ydb_endpoint=os.environ["YDB_ENDPOINT"].strip(),
            ydb_database=os.environ["YDB_DATABASE"].strip(),
            twitch_client_id=os.environ["TWITCH_CLIENT_ID"].strip(),
            twitch_client_secret=os.environ["TWITCH_CLIENT_SECRET"].strip(),
            live_poll_seconds=Config._int("LIVE_POLL_SECONDS", 60),
        )
