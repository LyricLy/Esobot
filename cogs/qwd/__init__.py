import asyncio
import discord
import datetime
import re
from dataclasses import dataclass, fields, field

from discord.ext import commands


class QwdBase(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await self.bot.wait_until_ready()
        QwdBase.qwd = self.bot.get_guild(1133026989637382144)

    def cog_check(self, ctx):
        return not ctx.guild and QwdBase.qwd.get_member(ctx.author.id) or ctx.guild == self.qwd


@dataclass
class OobTime:
    timestamp: int


WORD = re.compile(r"""
\s*

  `*"(?P<string>(?:[^\\"]|\\[^a-zA-Z0-9]|\\[nrt0]|\\x[0-7][0-9a-fA-F])*)"`*
| (?P<num>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)
| <\#(?P<channel>[0-9]+)>
| <@(?P<user>[0-9]+)>
| <@&(?P<role>[0-9]+)>
| https://discord\.com/channels/(?P<msg_guild>[0-9]+)/(?P<msg_channel>[0-9]+)/(?P<msg>[0-9]+)
| <(?P<emoji>a?:[a-zA-Z_0-9]+:[0-9]+)>
| <t:(?P<time>[0-9]+)(?::[dDtTfFR])?>
| (?P<bool>✅|❌)
| (?P<null>🦖)
""", re.VERBOSE)

def de(bot, s):
    values = []
    i = 0
    while i < len(s):
        m = WORD.match(s, i)
        if not m:
            return None
        if string := m["string"]:
            try:
                # TODO: never remove this!!!
                values.append(re.sub(r"\\[nrt0]|\\x..", lambda m: eval(f'"{m[0]}"'), string))
            except SyntaxError:
                return None
        elif num := m["num"]:
            try:
                values.append(int(num))
            except ValueError:
                # can't fail
                values.append(float(num))
        elif time := m["time"]:
            try:
                values.append(datetime.datetime.fromtimestamp(int(time), tz=datetime.timezone.utc))
            except OverflowError:
                values.append(OobTime(int(time)))
        elif channel := m["channel"]:
            values.append(QwdBase.qwd.get_channel(int(channel)) or discord.Object(int(channel), type=discord.abc.GuildChannel))
        elif user := m["user"]:
            values.append(QwdBase.qwd.get_member(int(user)) or discord.Object(int(user), type=discord.abc.User))
        elif role := m["role"]:
            values.append(QwdBase.qwd.get_member(int(role)) or discord.Object(int(role), type=discord.Role))
        elif emoji := m["emoji"]:
            partial = discord.PartialEmoji.from_str(emoji)
            values.append(QwdBase.qwd.get_emoji(partial.id) or partial)
        elif msg := m["msg"]:
            values.append(bot.get_partial_messageable(int(m["msg_channel"]), guild_id=int(m["msg_guild"]), type=discord.TextChannel).get_partial_message(int(msg)))
        elif bool := m["bool"]:
            values.append(bool == "✅")
        elif m["null"]:
            values.append(None)
        i = m.end() + 1  # skip a whitespace
    return values

def ser(l):
    out = []
    for val in l:
        if isinstance(val, str):
            out.append(f'"{val.replace("\\", r"\\").replace('"', r"\"")}"')
        elif isinstance(val, (int, float, discord.Emoji, discord.PartialEmoji)):
            out.append(str(val))
        elif isinstance(val, (discord.abc.GuildChannel, discord.abc.User, discord.Role)):
            out.append(val.mention)
        elif isinstance(val, discord.Object):
            _, letter = discord.utils.find(lambda x: issubclass(val.type, x), {
                discord.abc.User: "@",
                discord.abc.GuildChannel: "#",
                discord.Role: "@&",
                object: None,
            }.items())
            if not letter:
                raise ValueError(f"{val} is Object of unknown type")
            out.append(f"<{letter}{val.id}>")
        elif isinstance(val, (discord.Message, discord.PartialMessage)):
            out.append(val.jump_url)
        elif isinstance(val, datetime.datetime):
            out.append(discord.utils.format_dt(val))
        elif isinstance(val, bool):
            out.append("✅❌"[::2*val-1][0])
        elif val is None:
            out.append("🦖")
        else:
            raise ValueError(f"can't serialize {val}")
    return " ".join(out)


class ChitterError(Exception):
    pass

def myself(bot, user):
    return user == bot.user

def only(*people):
    return lambda bot, user: user in people

def bots(bot, user):
    return user.bot

def everyone(bot, user):
    return True


@dataclass
class ChitterRow:
    _message: discord.Message = field(kw_only=True, repr=False)

    synced = False
    _sync_task = None
    _added_listeners = False

    @classmethod
    def thread(cls):
        return QwdBase.qwd.get_thread(cls._thread_id)

    @classmethod
    def _see_message(cls, message):
        if message.channel != cls.thread() or not cls._listen_to(cls._bot, message.author):
            return
        l = de(cls._bot, message.content)
        if not l:
            return cls._table.pop(message.id, None)
        if cls._table.get(message.id) != (new := cls(*l, _message=message)):
            cls._table[message.id] = new

    @classmethod
    async def _sync(cls, bot):
        await bot.wait_until_ready()

        cls._bot = bot
        cls._table = {}
        cls.synced = False

        if not cls._added_listeners:
            bot.add_listener(cls.on_message)
            bot.add_listener(cls.on_raw_message_edit)
            bot.add_listener(cls.on_raw_message_delete)
            cls._added_listeners = True

        async for message in cls.thread().history(limit=None):
            cls._see_message(message)

        cls.synced = True

    @classmethod
    async def sync(cls, bot):
        if cls._sync_task:
            return await cls._sync_task
        cls._sync_task = asyncio.create_task(cls._sync(bot))
        await cls._sync_task
        cls._sync_task = None

    @classmethod
    async def on_message(cls, message):
        cls._see_message(message)

    @classmethod
    async def on_raw_message_edit(cls, payload):
        cls._see_message(payload.message)

    @classmethod
    async def on_raw_message_delete(cls, payload):
        cls._table.pop(payload.message_id)

    @classmethod
    def rows(cls):
        if not cls.synced:
            raise ChitterError("must be synced to get rows")
        return cls._table.values()

    @classmethod
    def writable(cls):
        return cls._listen_to(cls._bot, cls._bot.user)

    @classmethod
    def _require_writable(cls):
        if not cls.writable():
            raise ChitterError("table is not writable")

    def __iter__(self):
        for field in fields(self):
            if not field.kw_only:
                yield getattr(self, field.name)

    def __str__(self):
        return ser(self)

    @classmethod
    async def insert(cls, *args, **kwargs):
        cls._require_writable()
        us = cls(*args, **kwargs, _message=None)
        us._message = await cls.thread().send(str(us), allowed_mentions=discord.AllowedMentions.none())
        cls._table[us._message.id] = us
        return us

    async def update(self, **kwargs):
        self._require_writable()
        for x, y in kwargs.items():
            setattr(self, x, y)
        await self._message.edit(content=str(self))

    async def delete(self):
        self._require_writable()
        await self._message.delete()


def chitterclass(thread_id, *, listen_to=myself):
    def deco(cls):
        d = dict(cls.__dict__)
        d.pop("__dict__")
        d.pop("__weakref__")
        d["_thread_id"] = thread_id
        d["_listen_to"] = listen_to
        return dataclass(type(cls)(cls.__name__, (ChitterRow, *cls.__bases__), d))
    deco.__name__ = f"chitterclass({thread_id}, listen_to={listen_to})"
    return deco
