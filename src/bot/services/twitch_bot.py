from __future__ import annotations
import logging
from twitchio.ext import commands

from bot.util.time import month_key
from bot.services.accrual import AccrualService

log = logging.getLogger(__name__)

HELP = (
    "Команды: !top [N] — топ за месяц; !watchtime [ник] — минуты зрителя; "
    "!settopn N — дефолтный размер топа (стример/мод); !help — помощь."
)

def fmt_minutes(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}ч {m}м" if h else f"{m}м"

class StreamStatsBot(commands.Bot):
    def __init__(self, token: str, nick: str, channel: str, default_top_n: int, store, accrual: AccrualService):
        super().__init__(token=token, prefix="!", initial_channels=[f"#{channel}"], nick=nick)
        self.default_top_n = default_top_n
        self.store = store
        self.accrual = accrual
        # нормализованные логины (нижний регистр)
        self.bot_login = (nick or "").lower()
        self.channel_login = (channel or "").lower()

    async def event_ready(self):
        log.info("Connected as %s", self.nick)
        await self.accrual.start()

    async def event_message(self, message):
        # игнорируем сообщения без автора (служебные события и пр.)
        if not message.author or not message.author.name:
            return

        self.accrual.mark_active(message.author.name)
        await self.handle_commands(message)

    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context):
        await ctx.send(HELP)

    @commands.command(name="top")
    async def top_cmd(self, ctx: commands.Context, n: int | None = None):
        n = max(1, min(50, n or self.default_top_n))
        mkey = month_key()
        # исключаем из вывода стримера и бота
        exclude = [self.channel_login, self.bot_login]
        top = await self.store.get_top(mkey, n, exclude=exclude)
        if not top:
            await ctx.send("Пока нет данных за этот месяц.")
            return
        parts = [f"{i+1}) {user} — {fmt_minutes(minutes)}" for i, (user, minutes) in enumerate(top)]
        await ctx.send(f"Топ {n} за {mkey}: " + "; ".join(parts))

    @commands.command(name="time", aliases=["wt"])
    async def watchtime_cmd(self, ctx: commands.Context, nickname: str | None = None):
        user = nickname or (ctx.author.name if ctx.author else "")
        if not user:
            await ctx.send("Не удалось определить ник.")
            return
        mkey = month_key()
        minutes = await self.store.get_minutes(mkey, user)
        await ctx.send(f"{user}: {fmt_minutes(minutes)} за {mkey}.")

    @commands.command(name="settopn")
    async def settopn_cmd(self, ctx: commands.Context, n: int | None = None):
        if not (ctx.author and (ctx.author.is_broadcaster or ctx.author.is_mod)):
            await ctx.send("Эта команда доступна только стримеру или модератору.")
            return
        if not n or n < 1 or n > 50:
            await ctx.send("Использование: !settopn <1..50>")
            return
        self.default_top_n = n
        await ctx.send(f"Топ по умолчанию теперь: {self.default_top_n}.")
    @commands.command(name="live")
    async def live_cmd(self, ctx: commands.Context):
        # простая проверка через accrual.should_accrue()
        state = "идёт" if self.accrual.should_accrue() else "выключен"
        await ctx.send(f"Стрим сейчас {state}.")
