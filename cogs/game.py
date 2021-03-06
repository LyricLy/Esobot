import asyncio
import datetime
import random

import discord
from discord.ext import commands

from utils import make_embed


class Games(commands.Cog):
    """Games! Fun and games! Have fun!"""

    def __init__(self, bot):
        self.bot = bot
        self.words = None

    @commands.group(invoke_without_command=True)
    async def hwdyk(self, ctx):
        pass

    @hwdyk.command(aliases=["msg"])
    async def message(self, ctx):
        """Pick a random message. If you can guess who sent it, you win!"""

        # hardcoded list of "discussion" channels: esolang*, recreation-room, off-topic, r9k-test, programming, *-games
        channel = self.bot.get_channel(random.choice([
            348671457808613388,
            348702485994668033,
            348702065062838273,
            351171126594109455,
            348702212110680064,
            481655540976451584,
            412764872816852994,
            415981720286789634,
            445375649511768074,
            348697452712427522
        ]))

        # this doesn't uniformly pick a random message: it strongly prefers messages sent after longer pauses, however this is a trade-off for an incredibly cheap getting oper-
        # ation which doesn't require spamming calls or storing data
        base = datetime.datetime(year=2020, month=1, day=1)
        while True:
            t = base + datetime.timedelta(milliseconds=random.randint(0, int((datetime.datetime.utcnow() - base).total_seconds() * 1000)))
            try:
                message = (await channel.history(after=t, limit=1).flatten())[0]
            except IndexError:
                pass
            else:
                if (not message.content or len(message.content) > 25) and message.author in ctx.guild.members:
                    break

        embed = make_embed(
            description=message.content,
            footer_text="#??? • ??/??/????",
        )
        embed.set_author(name="❓  ???")
        if message.attachments:
            filename = message.attachments[0].filename
            if filename.endswith(".png") or filename.endswith(".jpg") or filename.endswith(".jpeg"):
                embed.set_image(url=message.attachments[0].url)

        bot_msg = await ctx.send("Who sent this message?", embed=embed)

        while True:
            r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                member = await commands.MemberConverter().convert(ctx, r.content)
            except commands.BadArgument:
                pass
            else:
                break

        # reveal info
        embed.set_footer(text="#" + message.channel.name)
        embed.timestamp = message.edited_at or message.created_at
        embed.set_author(name=message.author.name, icon_url=message.author.avatar_url)
        await bot_msg.edit(embed=embed)

        if member == message.author:
            await ctx.send("You were correct!")
        else:
            await ctx.send("Too bad. Good luck with the next time!")


    async def screen_abr(self, ctx):
        m = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author.id == 509849474647064576, timeout=1)
        await m.delete()

    @commands.command(aliases=["tr", "type", "race"])
    @commands.guild_only()
    async def typerace(self, ctx, words: int = 10):
        """Race typing speeds!"""
        if not 5 <= words <= 50:
            return await ctx.send("Use between 5 and 50 words.")
        if not self.words:
            async with self.bot.session.get("https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears-medium.txt") as resp:
                self.words = (await resp.text()).splitlines()

        WAIT_SECONDS = 5
        await ctx.send(f"Type race begins in {WAIT_SECONDS} seconds. Get ready!")
        await asyncio.sleep(WAIT_SECONDS)

        prompt = " ".join(random.choices(self.words, k=words))
        zwsp = "\u2060"

        self.bot.loop.create_task(self.screen_abr(ctx))
        start = await ctx.send(zwsp.join(list(prompt.translate(str.maketrans({
            "a": "а",
            "c": "с",
            "e": "е",
            "s": "ѕ",
            "i": "і",
            "j": "ј",
            "o": "о",
            "p": "р",
            "y": "у",
            "x": "х"
        })))))

        winners = {}
        is_ended = asyncio.Event()
        timeout = False
        while not is_ended.is_set():
            done, pending = await asyncio.wait([
                self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.content.lower() == prompt.lower() and not m.author.bot and m.author not in winners),
                is_ended.wait()
            ], return_when=asyncio.FIRST_COMPLETED); [*map(asyncio.Task.cancel, pending)]
            r = done.pop().result()
            if isinstance(r, discord.Message):
                msg = r
            else:
                break
            await msg.delete()
            winners[msg.author] = (msg.created_at - start.created_at).total_seconds()
            if not timeout:
                timeout = True
                async def ender():
                    await asyncio.sleep(10)
                    is_ended.set()
                await ctx.send(f"{msg.author.name.replace('@', '@' + zwsp)} wins. Other participants have 10 seconds to finish.")
                self.bot.loop.create_task(ender())
        await ctx.send("\n".join(f"{i + 1}. {u.name.replace('@', '@' + zwsp)} - {t:.4f} seconds ({len(prompt) / t * 12:.2f}WPM)" for i, (u, t) in enumerate(winners.items())))


def setup(bot):
    bot.add_cog(Games(bot))
