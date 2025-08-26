from __future__ import annotations
import os
from typing import List, Tuple

import ydb
import ydb.aio

SCHEMA_YQL = """
CREATE TABLE IF NOT EXISTS watchtime (
  month Utf8,
  user Utf8,
  minutes Uint64,
  PRIMARY KEY (month, user)
);
"""

def _esc(s: str) -> str:
    """Экранирует одинарные кавычки для YQL строк."""
    return str(s).replace("'", "''")

def _credentials():
    # 1) Serverless Containers — берём метаданные SA
    if os.getenv("YDB_METADATA_CREDENTIALS") == "1":
        return ydb.iam.MetadataUrlCredentials()
    # 2) Файл ключа сервисного аккаунта
    key_file = os.getenv("YDB_SERVICE_ACCOUNT_KEY_FILE_CREDENTIALS")
    if key_file:
        return ydb.iam.ServiceAccountCredentials.from_file(key_file)
    # 3) Токен из env (YDB_TOKEN/YC_TOKEN)
    return ydb.credentials_from_env()

class WatchtimeStoreYDB:
    def __init__(self, endpoint: str, database: str) -> None:
        self.endpoint = endpoint
        self.database = database
        self.driver: ydb.aio.Driver | None = None
        self.pool: ydb.aio.SessionPool | None = None

    async def init(self) -> None:
        creds = _credentials()
        self.driver = ydb.aio.Driver(
            endpoint=self.endpoint,
            database=self.database,
            credentials=creds,
            root_certificates=ydb.load_ydb_root_certificate(),
        )
        await self.driver.wait(fail_fast=True, timeout=15)
        self.pool = ydb.aio.SessionPool(self.driver, size=5)

        # создаём схему
        async with self.pool.checkout() as s:
            await s.execute_scheme(SCHEMA_YQL)

    async def close(self) -> None:
        if self.pool:
            await self.pool.stop()
        if self.driver:
            await self.driver.stop()

    async def add_minutes(self, month: str, user: str, delta: int) -> None:
        assert self.pool is not None
        d = max(0, int(delta))
        m = _esc(month)
        u = _esc(user)

        async with self.pool.checkout() as s:
            tx = s.transaction(ydb.SerializableReadWrite())
            await tx.begin()

            # читаем текущее
            rs = await tx.execute(
                f"""
                SELECT minutes FROM watchtime
                WHERE month = '{m}' AND user = '{u}';
                """
            )
            rows = rs[0].rows
            if rows:
                await tx.execute(
                    f"""
                    UPDATE watchtime
                    SET minutes = minutes + {d}
                    WHERE month = '{m}' AND user = '{u}';
                    """
                )
            else:
                await tx.execute(
                    f"""
                    UPSERT INTO watchtime (month, user, minutes)
                    VALUES ('{m}', '{u}', {d});
                    """
                )

            await tx.commit()

    async def get_minutes(self, month: str, user: str) -> int:
        assert self.pool is not None
        m = _esc(month)
        u = _esc(user)
        async with self.pool.checkout() as s:
            tx = s.transaction(ydb.StaleReadOnly())
            rs = await tx.execute(
                f"""
                SELECT minutes FROM watchtime
                WHERE month = '{m}' AND user = '{u}';
                """,
                commit_tx=True,
            )
            rows = rs[0].rows
            return int(rows[0]["minutes"]) if rows else 0

    async def get_top(self, month: str, n: int, exclude: list[str] | None = None) -> list[tuple[str, int]]:
        """Топ N за месяц, с возможностью исключить логины (бота, стримера и т.п.)."""
        assert self.pool is not None
        m = _esc(month)
        lim = max(1, min(50, int(n)))
        ex = exclude or []
        # нормализуем в нижний регистр и убираем пустые/дубли
        ex_norm = sorted(set([e.lower() for e in ex if e]))
        not_in = ""
        if ex_norm:
            ex_list = ", ".join(f"'{_esc(x)}'" for x in ex_norm)
            not_in = f" AND user NOT IN ({ex_list})"

        async with self.pool.checkout() as s:
            tx = s.transaction(ydb.StaleReadOnly())
            rs = await tx.execute(
                f"""
                SELECT user, minutes
                FROM watchtime
                WHERE month = '{m}'{not_in}
                ORDER BY minutes DESC, user ASC
                LIMIT {lim};
                """,
                commit_tx=True,
            )
            return [(r["user"], int(r["minutes"])) for r in rs[0].rows]
