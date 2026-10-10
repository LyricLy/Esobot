import asyncio
import datetime
import random
import os
import math
import re
from dataclasses import dataclass
from typing import Literal

import discord
from discord.ext import commands
from openskill.models import PlackettLuce

from utils import HandledConversionFailure, rank_enumerate


model = PlackettLuce(limit_sigma=True)

def is_idea_message(content):
    return bool(re.match(r".*\bidea\s*:", content))

def is_permutation_of(length, xs):
    return set(range(1, length+1)) == set(xs) and len(xs) == length

def to_numbers(s):
    return [int(x) for x in re.findall(r"\d+", s)]

def merge(xs, ys, key):
    inversions = 0
    i = 0
    j = 0
    r = []
    while i < len(xs) and j < len(ys):
        if key(xs[i]) > key(ys[j]):
            r.append(ys[j])
            inversions += len(xs)-i
            j += 1
        else:
            r.append(xs[i])
            i += 1
    r += xs[i:]
    r += ys[j:]
    return r, inversions

def sort_inversions(xs, key=lambda x: x):
    if len(xs) <= 1:
        return xs, 0
    split = len(xs)//2
    left, left_inv = sort_inversions(xs[:split], key)
    right, right_inv = sort_inversions(xs[split:], key)
    r, inv = merge(left, right, key)
    return r, left_inv + right_inv + inv

def message_embed(message):
    embed = discord.Embed(description=message.content)
    embed.set_footer(text="#" + message.channel.name)
    embed.timestamp = message.edited_at or message.created_at
    embed.set_author(name=message.author.global_name or message.author.name, icon_url=message.author.display_avatar)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.filename.endswith((".png", ".jpg", ".jpeg")):
            embed.set_image(url=attachment.url)
    return embed


@dataclass
class Winrate:
    s: int = 0
    n: int = 0

    def interval(self):
        z = 3
        s = self.s
        n = self.n
        avg = s / n
        divisor = 1 + z*z / n
        return (avg + z*z/(2*n)) / divisor, z/(2*n) * math.sqrt(4 * n * avg * (1-avg) + z*z) / divisor

    def centre(self):
        return self.interval()[0]

    def lower_bound(self):
        centre, radius = self.interval()
        return centre - radius

    def upper_bound(self):
        centre, radius = self.interval()
        return centre + radius

    def _ord_key(self):
        try:
            return self.lower_bound()
        except ZeroDivisionError:
            return float("-inf")

    def __str__(self):
        try:
            centre, radius = self.interval()
        except ZeroDivisionError:
            return "N/A (no games)"
        else:
            return f"{centre:.2%} ± {radius:.2%} ({self.s}/{self.n})"

    def __add__(self, other):
        return Winrate(self.s + other.s, self.n + other.n)

    def __sub__(self, other):
        return Winrate(self.s - other.s, self.n - other.n)

    def __lt__(self, other):
        if not isinstance(other, Winrate):
            return NotImplemented
        return self._ord_key() < other._ord_key()

    def __le__(self, other):
        if not isinstance(other, Winrate):
            return NotImplemented
        return self._ord_key() <= other._ord_key()

    def __gt__(self, other):
        if not isinstance(other, Winrate):
            return NotImplemented
        return self._ord_key() > other._ord_key()

    def __ge__(self, other):
        if not isinstance(other, Winrate):
            return NotImplemented
        return self._ord_key() >= other._ord_key()


class Games(commands.Cog):
    """Games! Fun and games! Have fun!"""

    def __init__(self, bot):
        self.bot = bot
        self.words = None

    async def pick_random_message(self, ctx):
        async with self.bot.db.execute("SELECT channel_id, weight FROM HwdykChannels WHERE guild_id = ?", (ctx.guild.id,)) as cur:
            channels = await cur.fetchall()
        if not channels:
            await ctx.send("This server isn't set up for `hwdyk`. Sorry!")
            raise HandledConversionFailure()

        channel_ids, weights = zip(*channels)
        channel = self.bot.get_channel(random.choices(channel_ids, weights)[0])

        # this doesn't uniformly pick a random message: it strongly prefers messages sent after longer pauses
        # however this is a trade-off for making it incredibly cheap to grab a message because we don't have to spam history calls or store any data
        t = channel.created_at + (datetime.datetime.now(datetime.timezone.utc) - channel.created_at) * random.random()
        ms = [m async for m in channel.history(around=t)]
        random.shuffle(ms)
        for message in ms:
            if message.webhook_id:
                msg = await self.bot.get_cog("PluralKit").pk_get(f"/messages/{message.id}")
                message.author = message.guild.get_member(int(msg.get("sender", "0")))

            if message.content and message.content.count(" ") > 3 and message.author in message.guild.members:
                break

        return message

    def rating_from_row(self, r, kind="player"):
        mu = f"{kind}_mu"
        sigma = f"{kind}_sigma"
        days = (datetime.datetime.now(datetime.timezone.utc) - r["played_at"]).days - 30
        if days > 0:
            r[sigma] = min(r[sigma] + 0.05 * days, model.sigma)
        return model.rating(r[mu], r[sigma])

    async def get_rating(self, guild, user, kind="player"):
        async with self.bot.db.execute(f"SELECT played_at, {kind}_mu, {kind}_sigma FROM HwdykGames WHERE guild_id = ? AND {kind}_id = ? ORDER BY played_at DESC, rowid DESC LIMIT 1", (guild.id, user.id,)) as cur:
            r = await cur.fetchone()
        if not r:
            return model.rating()
        return self.rating_from_row(r, kind)

    @commands.group(invoke_without_command=True)
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.guild_only()
    async def hwdyk(self, ctx, _: Literal["msg", "message"] | None = None, practice: Literal["practice"] | None = None):
        """How well do you know your friends? Pick a random message. If you can guess who sent it, you win!"""

        message = await self.pick_random_message(ctx)
        real_embed = message_embed(message)
        hidden_embed = real_embed.copy()
        hidden_embed.set_footer(text="#??? • ??/??/????")
        hidden_embed.set_author(name="❓  ???")
        hidden_embed.timestamp = None
        bot_msg = await ctx.reply("Who sent this message?", embed=hidden_embed)

        while True:
            r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author and not m.content.startswith("!"))
            try:
                member = await commands.MemberConverter().convert(ctx, r.content)
            except commands.BadArgument:
                pass
            else:
                break

        if not practice:
            player = await self.get_rating(ctx.guild, ctx.author)
            author = await self.get_rating(ctx.guild, message.author, "author")
            [player], [author] = model.rate([[player], [author]], ranks=[1, 2] if member == message.author else [2, 1])
            await self.bot.db.execute("""
                INSERT INTO HwdykGames (played_at, player_id, guild_id, message_id, guess, author_id, player_mu, player_sigma, author_mu, author_sigma)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (datetime.datetime.now(datetime.timezone.utc), ctx.author.id, ctx.guild.id, message.id, member.id, message.author.id, player.mu, player.sigma, author.mu, author.sigma))
            await self.bot.db.commit()

        # reveal info
        await bot_msg.edit(embed=real_embed)

        if member == message.author:
            await bot_msg.reply("You were correct!")
        else:
            await bot_msg.reply("Too bad. Good luck with the next time!")

    @hwdyk.command(aliases=["time"])
    @commands.guild_only()
    async def when(self, ctx, difficulty: int = 4):
        """Pick some random messages. If you can guess what order they were sent in, you win!""" 

        if not 2 <= difficulty <= 8:
            return await ctx.send("Difficulty must be between 2 and 8.") 

        msgs = []
        for _ in range(difficulty):
            msgs.append(await self.pick_random_message(ctx))

        real_embeds = []
        hidden_embeds = []
        for idx, msg in enumerate(msgs, start=1):
            real_embed = message_embed(msg)
            real_embed.set_footer(text=f"Message {idx} • " + real_embed.footer.text)
            hidden_embed = real_embed.copy()
            hidden_embed.set_footer(text=hidden_embed.footer.text + " • ??/??/????")
            hidden_embed.timestamp = None
            real_embeds.append(real_embed)
            hidden_embeds.append(hidden_embed)

        bot_msg = await ctx.reply("In what order were these messages sent?", embeds=hidden_embeds)
        r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author and is_permutation_of(len(msgs), to_numbers(m.content)))
        guess = [msgs[i-1] for i in to_numbers(r.content)]

        real_embeds.sort(key=lambda e: e.timestamp)
        await bot_msg.edit(content="The true order.", embeds=real_embeds)

        _, inversions = sort_inversions(guess, key=lambda m: m.created_at)
        score = 1 - inversions / math.comb(difficulty, 2)
        if difficulty == 2 and not score:
            await r.reply("Aww, too bad. Try again next time!")
        elif difficulty == 2:
            await r.reply("You got it right! Well done!")
        elif score == 0.0:
            await r.reply("Huh. You know you're supposed to put them in *ascending* order, right?")
        elif score == 1.0:
            await r.reply("Perfect! Congratulations!")
        elif inversions == 1:
            await r.reply("Just one swap away from perfect! Good going.")
        elif score > 0.5:
            await r.reply(f"You were {score*100:.0f}% correct. Not bad.")
        else:
            await r.reply(f"You were {score*100:.0f}% correct. Try harder next time.")

    @hwdyk.command()
    @commands.guild_only()
    async def stats(self, ctx, *, member: discord.Member = None):
        """See how well someone (or everyone) is doing."""

        embed = discord.Embed(title="`hwdyk` statistics", colour=discord.Colour(0x6b32a8))

        if not member:
            def render(rs, key=lambda r: Winrate(r["correct"], r["total"]), display=str, reverse=False):
                l = []
                for rank, r in rank_enumerate(rs, key=key, reverse=reverse):
                    if rank > 5:
                        break
                    l.append(f"{rank}: <@{r[0]}> - {display(key(r))}")
                return "\n".join(l)

            async with self.bot.db.execute("SELECT player_id, player_mu, player_sigma, played_at, MAX(played_at) FROM HwdykGames WHERE guild_id = ? GROUP BY player_id", (ctx.guild.id,)) as cur:
                players = await cur.fetchall()
            embed.add_field(name="Best players", value=render(
                players,
                key=self.rating_from_row,
                display=lambda k: f"{k.ordinal(target=1000, alpha=21):.0f}",
                reverse=True,
            ), inline=False)

            async with self.bot.db.execute("SELECT author_id, COUNT(*) as total, SUM(guess = author_id) as correct FROM HwdykGames WHERE guild_id = ? GROUP BY author_id", (ctx.guild.id,)) as cur:
                items = await cur.fetchall()
            embed.add_field(name="Hardest to guess", value=render(
                items,
                key=lambda r: (wr.upper_bound() if (wr := Winrate(r["correct"], r["total"])).n else float("inf"), wr),
                display=lambda t: str(t[1]),
            ))
            embed.add_field(name="Easiest to guess", value=render(items, reverse=True))
            embed.set_footer(text=f"Statistics only for this server, {ctx.guild.name}")

        else:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

            async with self.bot.db.execute("SELECT COUNT(*), COALESCE(SUM(guess = author_id), 0) FROM HwdykGames WHERE guild_id = ? AND player_id = ?", (ctx.guild.id, member.id,)) as cur:
                total, correct = await cur.fetchone()

            async with self.bot.db.execute("SELECT COUNT(*), COALESCE(SUM(guess = author_id), 0) FROM HwdykGames WHERE guild_id = ? AND author_id = ?", (ctx.guild.id, member.id,)) as cur:
                total_author, correct_author = await cur.fetchone()

            rating = await self.get_rating(ctx.guild, member)
            author_rating = await self.get_rating(ctx.guild, member, "author")
            embed.add_field(name="Rating", value=f"{rating.ordinal(target=1000, alpha=21):.0f}")
            embed.add_field(name="Guess difficulty rating", value=f"{author_rating.ordinal(target=1000, alpha=21):.0f}")

            embed.add_field(name="Winrate", value=str(Winrate(correct, total)), inline=False)

            if not total_author:
                embed.set_footer(text=f"No message by {member.display_name} has appeared yet")
            elif total_author == 1:
                end = "was guessed correctly (100%)" if correct_author else "was not guessed correctly (0%)"
                embed.set_footer(text=f"A message by {member.display_name} has appeared 1 time and {end}")
            else:
                times = f"{correct_author} times" if correct_author != 1 else "1 time"
                embed.set_footer(text=f"Messages by {member.display_name} have appeared {total_author} times and been guessed correctly {times} ({correct_author/total_author:.2%})")

        await ctx.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def on_message_idea(self, message):
        if not message.author.bot and message.guild and is_idea_message(message.content):
            await self.bot.db.execute("INSERT INTO Ideas (guild_id, channel_id, message_id) VALUES (?, ?, ?)", (message.guild.id, message.channel.id, message.id))
            await self.bot.db.commit()

    @commands.command()
    async def idea(self, ctx):
        """Get a random idea."""
        while True:
            async with self.bot.db.execute("SELECT rowid FROM Ideas") as cur:
                rowid, = random.choice(await cur.fetchall())
            async with self.bot.db.execute("SELECT * FROM Ideas WHERE rowid = ?", (rowid,)) as cur:
                m = await cur.fetchone()
            try:
                msg = await self.bot.get_guild(m["guild_id"]).get_channel(m["channel_id"]).fetch_message(m["message_id"])
            except discord.HTTPException:
                msg = None
            if not msg or not is_idea_message(idea := msg.content):
                await self.bot.db.execute("DELETE FROM Ideas WHERE rowid = ?", (rowid,))
                continue
            if idea.endswith("idea:"):
                idea_extra = None
                async for m in msg.channel.history(after=msg, limit=5):
                    if m.author == msg.author:
                        idea_extra = m.content
                        break
                if idea_extra is not None:
                    idea += "\n"
                    idea += idea_extra
            await ctx.send(f"{msg.jump_url}\n{msg.content}", allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=False))
            break

    async def run_race(self, ctx, prompt, is_valid):
        await ctx.send(f"Race begins in 5 seconds. Get ready!")
        await asyncio.sleep(5)

        zwsp = "\u2060"
        start = await ctx.send(zwsp.join(prompt.translate(str.maketrans({
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
        }))))

        winners = {}
        is_ended = asyncio.Event()

        async def on_message(message):
            if message.channel == ctx.channel and is_valid(message.content) and not message.author.bot and message.author not in winners:
                first_winner = not winners
                winners[message.author] = (message.created_at - start.created_at).total_seconds()
                if first_winner:
                    async def ender():
                        await asyncio.sleep(10)
                        is_ended.set()
                    await ctx.send(f"{message.author.name.replace('@', '@' + zwsp)} wins. Other participants have 10 seconds to finish.")
                    self.bot.loop.create_task(ender())
                await message.delete()

        self.bot.add_listener(on_message)
        try:
            await asyncio.wait_for(is_ended.wait(), 120)
        except asyncio.TimeoutError:
            pass
        else:
            await ctx.send("\n".join(f"{i + 1}. {u.name.replace('@', '@' + zwsp)} - {t:.4f} seconds ({len(prompt) / t * 12:.2f}WPM)" for i, (u, t) in enumerate(winners.items())))
        finally:
            self.bot.remove_listener(on_message)

    @commands.command(aliases=["tr", "type", "race"])
    @commands.guild_only()
    async def typerace(self, ctx, words: int = 10):
        """A simple typing race."""
        if not 5 <= words <= 75:
            return await ctx.send("Use between 5 and 75 words.")
        if not self.words:
            async with self.bot.session.get("https://raw.githubusercontent.com/monkeytypegame/monkeytype/master/frontend/static/languages/english_1k.json") as resp:
                self.words = (await resp.json(content_type="text/plain"))["words"]
        prompt = " ".join(random.choices(self.words, k=words))
        await self.run_race(ctx, prompt, lambda s: s.lower() == prompt)

    @commands.command()
    @commands.guild_only()
    async def kanarace(self, ctx, kana_count: int = 10, use_katakana: bool = False):
        """A typing race with hiragana (or katakana)"""
        if not 1 <= kana_count <= 50:
            return await ctx.send("Use between 1 and 50 kana.")
        hiragana = "あいうえおかきくけこがぎぐげごさしすせそざじずぜぞたちつてとだぢづでどなにぬねのはひふへほばびぶべぼぱぴぷぺぽまみむめもやゆよらりるれろわを"
        katakana = "アイウエオカキクケコガギグゲゴサシスセソザジズゼゾタチツテトダヂヅデドナニヌネノハヒフヘホバビブベボポピプペポマミムメモヤユヨラリルレロワヲ"
        table = str.maketrans(katakana, hiragana)
        prompt = "".join(random.choices(katakana if use_katakana else hiragana, k=kana_count))
        await self.run_race(ctx, prompt, lambda s: s.translate(table) == prompt.translate(table))

    @commands.command()
    @commands.guild_only()
    async def sortrace(self, ctx, count: int = 10, max_value: int = 100):
        """Why would you play this?"""
        if not 1 <= count <= 100:
            return await ctx.send("Use between 1 and 100 numbers.")
        prompt = [random.randint(0, max_value) for _ in range(count)]
        sorted_prompt = sorted(prompt)
        await self.run_race(ctx, str(prompt), lambda s: [(m := x.strip("[],")).isdigit() and int(m) for x in s.split()] == sorted_prompt)


async def setup(bot):
    await bot.add_cog(Games(bot))
