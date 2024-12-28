from collections import defaultdict
from typing import Union, Optional, MutableMapping

import discord
from datetime import datetime, timedelta, timezone
from discord.ext import commands
from bs4 import BeautifulSoup

from utils import get_pronouns
from constants.anon import CANON_URL, EVENT_DISCUSSION


class Connection:
    def __init__(self, name, target, persona):
        self.name = name
        self.target = target
        self.persona = persona

def cfg_norm(s):
    return s.replace("_", "-")

async def persona_named(ctx, name):
    async with ctx.bot.session.get(CANON_URL + "/personas/who", params={"name": name}) as resp:
        j = await resp.json()
    if j["result"] == "missing" or j["user"] != ctx.author.id:
        await ctx.send("You don't have a persona by that name.")
        return None
    return j["id"]

class CodeGuessing(commands.Cog, name="Code guessing"):
    """Functions related to code guessing."""

    def __init__(self, bot):
        self.bot = bot
        self.conns = {}
        self.channel_conns: MutableMapping[discord.TextChannel, list[Connection]] = defaultdict(list)

    @commands.command()
    async def cg(self, ctx):
        """Current information about code guessing."""
        await ctx.send("Deary me, deary me.")

    @commands.dm_only()
    @commands.group(invoke_without_command=True)
    async def anon(self, ctx, target: Optional[Union[discord.User, discord.TextChannel]], *, name=None):
        """Use in DMs with Esobot to anonymously message a user or channel."""
        target = target or self.bot.get_channel(EVENT_DISCUSSION)

        if ctx.author in self.conns:
            return await ctx.send("You're already in an anonymous connection.")

        if not name:
            async with self.bot.session.get(f"{CANON_URL}/users/{ctx.author.id}/personas") as resp:
                j = await resp.json()
            name = j[0]["name"]
            persona = j[0]["id"]
        elif not (persona := await persona_named(ctx, name)):
            return

        if isinstance(target, discord.User):
            p = get_pronouns(target)
            if target.bot:
                return await ctx.send(f"{p.are()} a bot.")
            async with self.bot.session.get(f"{CANON_URL}/users/{target.id}/settings") as resp:
                dms = discord.utils.find(lambda x: x["name"] == "dms", await resp.json())["value"]
            if target in self.conns or not dms:
                return await ctx.send(f"{p.are()} already in an anonymous channel or {'have' if p.plural else 'has'} anonymous DMs disabled.")
            where = f"to {p.obj}"
            prep = "with"
            self.conns[target] = Connection(target.global_name or target.name, ctx.author, None)
            await target.send(f"You are being messaged anonymously by '{name}'.")
        elif not ((member := target.guild.get_member(ctx.author.id)) and target.permissions_for(member).send_messages):
            return await ctx.send("You can't speak in that channel.")
        elif target.id != EVENT_DISCUSSION:
            return await ctx.send(f"Anonymous messages are currently only allowed in <#{EVENT_DISCUSSION}>.")
        else:
            where = "there"
            prep = "in"
            self.channel_conns[target].append(Connection(None, ctx.author, None))
            await target.send(f"An anonymous user ({name}) joined the channel.")

        self.conns[ctx.author] = Connection(name, target, persona)
        await ctx.send(f"Started a session {prep} {target.mention}. All the messages you send (except commands) after this point will be sent {where}.\n"
                       f"You are **{name}**. Do `!anon leave` to stop bridging.\n"
                       "Avoid automatic normalization for a single message by prefixing it with `\\`.\n"
                       "**NB**: Full anonymity is not guaranteed. Your identity can be accessed by the developer of the bot.\n")

    @commands.dm_only()
    @anon.command(aliases=["stop"])
    async def leave(self, ctx):
        """Leave a channel which you are anonymously messaging."""
        if conn := self.conns.pop(ctx.author, None):
            if not self.conns.pop(conn.target, None):
                conns = self.channel_conns[conn.target]
                for c in conns:
                    if c.target == ctx.author:
                        conns.remove(c)
                        break
            await conn.target.send(f"{conn.name} left.")
            await ctx.send("Left.")
        else:
            await ctx.send("?")

    @commands.dm_only()
    @anon.group(invoke_without_command=True, aliases=["persona"])
    async def personas(self, ctx):
        """See, add or remove your anonymous personas."""
        async with self.bot.session.get(f"{CANON_URL}/users/{ctx.author.id}/personas") as resp:
            personas = await resp.json()
        l = []
        for persona in personas:
            l.append(f"- **{persona['name']}**" + " (temp)"*persona['temp'])
        await ctx.send("\n".join(l))

    @commands.dm_only()
    @personas.command(aliases=["create", "make", "new"])
    async def add(self, ctx, *, name):
        """Add a new anonymous persona."""
        async with self.bot.session.post(f"{CANON_URL}/users/{ctx.author.id}/personas", json={"name": name}) as resp:
            j = await resp.json()
        if j["result"] == "taken":
            return await ctx.send("That name is taken or reserved.")
        await ctx.send("All done.")

    @commands.dm_only()
    @personas.command(aliases=["delete", "del", "rm", "nix"])
    async def remove(self, ctx, *, name):
        """Remove an anonymous persona."""
        if not (persona := await persona_named(ctx, name)):
            return
        await self.bot.session.delete(f"{CANON_URL}/personas/{persona}")
        await ctx.send("All done.")

    @anon.command(aliases=["settings", "config", "opt", "options"])
    async def cfg(self, ctx, name=None, value: bool | None = None):
        """Query and set options related to comments and anon."""
        url = f"{CANON_URL}/users/{ctx.author.id}/settings"
        async with self.bot.session.get(url) as resp:
            settings = await resp.json()
        if not name:
            embed = discord.Embed()
            for setting in settings:
                n = cfg_norm(setting["name"])
                v = "yes" if setting["value"] else "no"
                embed.add_field(name=f"{setting['display']} (`!anon cfg {n} {v}`)", value=setting["blurb"], inline=False)
            await ctx.send(embed=embed)
        else:
            d = {}
            for setting in settings:
                if setting["value"] if cfg_norm(setting["name"]) != cfg_norm(name) else value if value is not None else not setting["value"]:
                    d[setting["name"]] = True
            await self.bot.session.post(url, json=d)
            await ctx.send("All done.")

    @commands.is_owner()
    @anon.command(aliases=["uncover", "reveal", "deanon", "de"])
    async def see(self, ctx, *, name):
        async with self.bot.session.get(CANON_URL + "/personas/who", params={"name": name}) as resp:
            j = await resp.json()
        if j["result"] == "missing":
            return await ctx.send("There's nobody called that.")
        user = self.bot.get_user(j["user"])
        await ctx.send(f"That's {user}.")

    @commands.guild_only()
    @anon.command(aliases=["list"])
    async def who(self, ctx):
        """See what anonymous users are connected to a channel."""
        if not (conns := self.channel_conns[ctx.channel]):
            return await ctx.send("Nobody here!")
        await ctx.send(", ".join(self.conns[conn.target].name for conn in conns))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user or message.content.startswith("!"):
            return
        conns = self.channel_conns[message.channel]
        if not message.guild and (conn := self.conns.get(message.author)) and conn.persona:
            conns = [conn, *[Connection(conn.name, c.target, conn.persona) for c in self.channel_conns[conn.target]]]
            async with self.bot.session.post(f"{CANON_URL}/users/{message.author.id}/transform", json={"text": message.content, "persona": conn.persona}) as resp:
                content = (await resp.json())["text"]
        else:
            content = message.content
        files = [await f.to_file() for f in message.attachments]
        for conn in conns:
            if message.author == conn.target:
                continue
            name = conn.name or message.author.display_name
            for file in files:
                file.fp.seek(0)
            await conn.target.send(f"<{discord.utils.escape_markdown(name)}> {content}", embeds=message.embeds, files=files)

async def setup(bot):
    await bot.add_cog(CodeGuessing(bot))
