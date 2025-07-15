#!/usr/bin/env python3

import asyncio
import aiohttp
import aiosqlite
import discord
import datetime
import functools
import logging
import sys
import traceback
import os

from cogs import get_extensions
from constants import colors, info
from discord.ext import commands
from utils import l, show_error
from sqlite3 import PARSE_DECLTYPES

LOG_LEVEL_API = logging.WARNING
LOG_LEVEL_BOT = logging.INFO
LOG_FMT = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"

try:
    with open("token.txt") as f:
        TOKEN = f.read().strip()
except IOError:
    print("Create a file token.txt and place the bot token in it.")
    exit(1)

if not os.path.exists("config"):
    os.mkdir("config")


if info.DEV:
    logging.basicConfig(format=LOG_FMT)
else:
    logging.basicConfig(format=LOG_FMT, filename="bot.log")
logging.getLogger("discord").setLevel(LOG_LEVEL_API)
l.setLevel(LOG_LEVEL_BOT)


try:
    with open("admin.txt") as f:
        owner_id = int(f.read())
except IOError:
    owner_id = None

COMMAND_PREFIX = "!"

intents = discord.Intents(
    guilds=True,
    members=True,
    messages=True,
    message_content=True,
    reactions=True,
    emojis=True,
)

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or(COMMAND_PREFIX),
    case_insensitive=True,
    max_messages=50,
    status=discord.Status.dnd,
    allowed_mentions=discord.AllowedMentions(everyone=False, replied_user=False),
    intents=intents
)
bot.owner_id = owner_id
bot.needed_extensions = set(get_extensions())
bot.loaded_extensions = set()


@bot.event
async def on_ready():
    bot.owner_id = (await bot.application_info()).owner.id
    l.info(f"Ready")
    await wait_until_loaded()
    await bot.change_presence(status=discord.Status.online)


@bot.event
async def on_connect():
    l.info(f"Connected as {bot.user}")
    await wait_until_loaded()
    await bot.change_presence(status=discord.Status.idle)


@bot.event
async def on_resumed():
    await wait_until_loaded()
    await bot.change_presence(status=discord.Status.online)
    l.info("Resumed session")


@bot.event
async def on_command_error(ctx, exc):
    command_name = ctx.command.qualified_name if ctx.command else "unknown command"
    if isinstance(exc, commands.UserInputError):
        if isinstance(exc, commands.MissingRequiredArgument):
            description = f"Missing required argument `{exc.param.name}`."
        elif isinstance(exc, (commands.BadArgument, commands.BadUnionArgument)):
            description = f"Invalid argument. {str(exc)}"
        else:
            description = f"Unknown user input exception."
        description += f"\n\nRun `{COMMAND_PREFIX}help {command_name}` to view the required arguments."
    elif isinstance(exc, commands.CommandNotFound):
        return
    elif isinstance(exc, commands.CheckFailure):
        if isinstance(exc, commands.NoPrivateMessage):
            description = "Cannot be used in a DM."
        elif isinstance(exc, commands.MissingPermissions):
            description = "You don't have permission to do that. "
            missing_perms = ", ".join(exc.missing_permissions)
            description += f"Missing {missing_perms}"
        elif isinstance(exc, commands.NotOwner):
            description = "You have to be the bot owner to do that."
        elif isinstance(exc, commands.MissingRole):
            description = f"You're missing the required role '{exc.missing_role}'."
        elif isinstance(exc, commands.PrivateMessageOnly):
            description = "This command has to be used in a DM."
        else:
            description = "Command check failed. For one reason or another, you're not allowed to run that command in this context."
    elif isinstance(exc, commands.DisabledCommand):
        description = "That command is disabled."
    elif isinstance(exc, commands.CommandOnCooldown):
        description = f"That command is on cooldown. Try again in {exc.retry_after:.1f} seconds."
    elif isinstance(exc, commands.MaxConcurrencyReached):
        description = "This command is currently already in use. Please try again later."
    else:
        description = "Sorry, something went wrong."
        l.error(
            f"Unknown error encountered while executing '{command_name}'\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        )
    await show_error(ctx, description)


@bot.event
async def on_error(event_method, *args, **kwargs):
    l.error(
        f"Error encountered during '{event_method}' (args: {args}; kwargs: {kwargs})\n" + traceback.format_exc()
    )

async def load_extensions():
    await bot.load_extension("jishaku")
    for extension in bot.needed_extensions:
        await asyncio.sleep(0)
        try:
            await bot.load_extension("cogs." + extension)
        except Exception as e:
            print(f"Failed to load {extension}: {type(e).__name__}: {e}")
            continue
        bot.loaded_extensions.add(extension)
    l.info("Loaded all extensions")

aiosqlite.register_converter("timestamp", lambda x: datetime.datetime.fromisoformat(x.decode()))
aiosqlite.register_adapter(datetime.datetime, lambda x: x.isoformat())

async def setup():
    bot.loop.create_task(load_extensions())
    bot.session = aiohttp.ClientSession(loop=bot.loop, headers={"User-Agent": info.NAME})
    db = await aiosqlite.connect("config/the.db", detect_types=PARSE_DECLTYPES)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")

    with open("schema.sql") as f:
        script = f.read()
    await db.executescript(script)
    await db.commit()

    bot.db = db

async def close(old_close=bot.close):
    await bot.session.close()
    await bot.db.close()
    await old_close()

bot.setup_hook = setup
bot.close = close

async def wait_until_loaded():
    while bot.needed_extensions < bot.loaded_extensions:
        await asyncio.sleep(0)


if __name__ == "__main__":
    bot.run(TOKEN)
