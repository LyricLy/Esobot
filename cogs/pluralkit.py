import asyncio
import aiohttp
import discord
import time

from collections import defaultdict, deque
from dataclasses import dataclass, field
from discord.ext import commands


PLURALKIT_ROOT = "https://api.pluralkit.me/v2"

type Member = str

@dataclass
class PKSettings:
    tags: dict[tuple[str, str], Member] = field(default_factory=dict)
    autoproxy_guilds: dict[discord.Guild, Member] = field(default_factory=dict)

    def proc(self, message):
        print(self)
        for (start, end), name in self.tags.items():
            if (not start or message.content.startswith(start)) and (not end or message.content.endswith(end)):
                return name
        if message.content.startswith("\\\\"):
            self.autoproxy_guilds.pop(message.guild, None)
        if message.content.startswith("\\"):
            return None
        return self.autoproxy_guilds.get(message.guild)

def name_of_member(member, system):
    name = member["display_name"] or member["name"]
    tag = system["tag"]
    if tag:
        name = f"{name} {tag}"
    return name


class PluralKit(commands.Cog):
    """Support for proxied messages from PluralKit."""

    def __init__(self, bot):
        self.bot = bot
        self.expected_proxies = defaultdict(deque)
        self.settings_cache = defaultdict(PKSettings)
        self.og_dispatch = discord.Client.dispatch
        discord.Client.dispatch = self.dispatch

    async def cog_unload(self):
        discord.Client.dispatch = self.og_dispatch

    def dispatch_message(self, message):
        self.og_dispatch(self.bot, "message", message)

    async def pk_get(self, endpoint):
        headers = {"User-Agent": "Esobot (https://github.com/LyricLy/Esobot)"}
        while True:
            async with self.bot.session.get(PLURALKIT_ROOT + endpoint, headers=headers) as resp:
                json = await resp.json()
                if resp.status == 429:
                    await asyncio.sleep(json["retry_after"] / 1000)
                    continue
            return json

    async def too_bad(self, message):
        await asyncio.sleep(1)
        self.dispatch_message(message)
        self.settings_cache[message.author].autoproxy_guilds.pop(message.guild, None)

    async def autopsy(self, message):
        # our job is to figure out the deal with the given webhook message is, and
        # see if it was a missed pluralkit proxy message

        # first, see if pluralkit knows about it
        msg = await self.pk_get(f"/messages/{message.id}")
        if "code" in msg:
            # it does not, so dispatch it normally
            self.dispatch_message(message)
            return

        # it does! then our info is out of date, so we need to update the cache.
        # first, find the original message
        for original_message in self.bot.cached_messages[:-16:-1]:
            if original_message.id == int(msg["original"]):
                break
        else:
            # that's weird... oh well, just give up here, this shouldn't happen often
            return

        # then fill in the fields
        settings = self.settings_cache[original_message.author]
        system = msg["system"]

        tags = {}
        for member in await self.pk_get(f"/systems/{system["id"]}/members"):
            for t in member["proxy_tags"]:
                tags[t["prefix"], t["suffix"]] = name_of_member(member, system)
        settings.tags = tags

        # if the original message wouldn't have proxied with these tags, it's probably autoproxy
        if not settings.proc(original_message):
            settings.autoproxy_guilds[message.guild] = name_of_member(msg["member"], system)

        # this was a missed proxy message, so dispatching it is unlikely to do any good as we
        # probably already dispatched the original message. the info is ready for next time now,
        # so the function can return without doing anything else.

    def dispatch(self, event_name, /, *args, **kwargs):
        if event_name != "message":
            return self.og_dispatch(self.bot, event_name, *args, **kwargs)
        message = args[0]

        # a webhook! could be pluralkit...
        if message.webhook_id:
            # were we expecting this?
            d = self.expected_proxies.get((message.author.name, message.channel))
            while d:
                task, author = d.popleft()
                if not task.done():
                    # we were, so cancel the `too_bad` task and dispatch the proxy
                    message.author = author
                    self.dispatch_message(message)
                    task.cancel()
                    return

            # looks like we weren't, so kick this off to be autopsied
            self.bot.loop.create_task(self.autopsy(message))

        if name := self.settings_cache[message.author].proc(message):
            task = self.bot.loop.create_task(self.too_bad(message))
            self.expected_proxies[name, message.channel].append((task, message.author))
        else:
            self.dispatch_message(message)


async def setup(bot):
    await bot.add_cog(PluralKit(bot))
