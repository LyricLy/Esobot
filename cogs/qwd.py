import math
import re
import datetime
import random
import asyncio
from io import BytesIO
from collections import defaultdict
from tokenize import TokenError

import discord
from PIL import Image
from discord.ext import commands
from pint import UnitRegistry, UndefinedUnitError, DimensionalityError, formatting, register_unit_format
from typing import Optional, Union

from utils import get_pronouns, EmbedPaginator


ureg = UnitRegistry(autoconvert_offset_to_baseunit=True)
ureg.separate_format_defaults = True

try:
    @register_unit_format("Pc")
    def format_pretty_cool(unit, registry, **options):
        opts = {**registry.formatter._formatters["P"], "division_fmt": " / ", **options}
        return formatting.formatter(unit.items(), **opts)
except ValueError:
    # already defined
    pass

ureg.default_format = "~Pc"

class ParseError(ValueError):
    pass

class UnitFormatter:
    def __init__(self, unit, prec, compact, radices):
        self.unit = unit
        self.prec = prec
        self.compact = compact
        self.radices = radices

    def format(self, q):
        q = round(q.to(self.unit), self.prec)
        s = ""
        for radix in self.radices:
            digit, q = divmod(q, 1*radix)
            s += f"{digit*radix:.0f}"
        if self.compact:
            q = q.to_compact()
        s += f"{q:.{self.prec}f}"
        return s.replace(" ", "")

    def __repr__(self):
        return f"UnitFormatter({self.unit!r}, {self.prec!r}, {self.compact!r}, {self.radices!r})"

    def __str__(self):
        s = "".join([f"{unit:Pc} + " for unit in self.radices])
        s += f"{'~'*self.compact}{self.unit:Pc}"
        if self.prec:
            s += f".{self.prec}"
        return s

class Leaderboard:
    def __init__(self, main, others, asc):
        self.main = main
        self.others = others
        self.asc = asc

    def ureq(self, string):
        q = ureg.Quantity(string)
        if q.unitless:
            q = q.m * self.main.unit
        else:
            q.ito(self.main.unit)
        if not math.isfinite(q.m):
            raise commands.BadArgument("What are you doing?")
        return q

    def format(self, q):
        s = self.main.format(q)
        if self.others:
            s += f" ({', '.join([formatter.format(q) for formatter in self.others])})"
        return s

    def __repr__(self):
        return f"Leaderboard({self.main!r}, {self.others!r}, {self.asc!r})"

    def __str__(self):
        return "asc "*self.asc + ", ".join(str(f) for f in [self.main, *self.others])

    def lean(self):
        return f"{self.main.unit:Pc}"

    @classmethod
    async def convert(cls, ctx, argument):
        async with ctx.bot.db.execute("SELECT definition, NULL FROM Leaderboards WHERE name = ?1 UNION SELECT definition, source FROM LeaderboardAliases WHERE name = ?1", (argument,)) as cur:
            defn = await cur.fetchone()
        if not defn:
            raise commands.BadArgument("leaderboard doesn't exist :(")
        x = parse_leaderboard(defn[0])
        x.name = defn[1] or argument
        x.display_name = argument
        return x

class LeaderboardParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def peek(self):
        return self.s[self.i:self.i+1]

    def advance(self):
        self.i += 1

    def panic(self, msg):
        pre = "  \033[1;34m|\033[0m "
        s = f"\n\033[1;31merror: \033[0m\033[1m{msg}\n{pre}\n{pre}{self.s}\n{pre}{' '*self.i}\033[1;31m^"
        raise ParseError(s)

    def assert_compatible(self, x, y):
        if not x.is_compatible_with(y):
            self.panic(f"units '{x:Pc}' and '{y:Pc}' are incompatible")

    def unit(self):
        n = ""
        while (c := self.peek()) not in ",.~+":
            if c == "-":
                self.panic("unexpected - in unit")
            n += c
            self.advance()
        n = n.strip()
        if not n:
            self.panic("expected unit")
        try:
            u = ureg.Unit(n)
        except (ValueError, UndefinedUnitError):
            self.panic(f"'{n}' is not a unit")
        else:
            return u

    def skip_ws(self):
        while self.peek().isspace():
            self.advance()

    def formatter(self):
        parts = []
        while True:
            self.skip_ws()
            if self.peek() == "~":
                if parts:
                    self.panic("the compacting operator ~ is incompatible with + chaining")
                compact = True
                self.advance()
            else:
                compact = False
            unit = self.unit()
            if parts:
                self.assert_compatible(parts[0], unit)
            parts.append(unit)
            prec = 0
            if self.peek() == ".":
                self.advance()
                try:
                    prec = int(self.peek())
                except ValueError:
                    self.panic("precision must be a digit")
                self.advance()
                self.skip_ws()
                break
            if compact or self.peek() != "+":
                break
            self.advance()
        *radices, unit = parts
        return UnitFormatter(unit, prec, compact, radices)

    def rule(self):
        asc = self.s.startswith("asc ")
        if asc:
            self.i += 4
        main = self.formatter()
        others = []
        while self.peek():
            if self.peek() != ",":
                self.panic("expected comma or end of string")
            self.advance()
            formatter = self.formatter()
            self.assert_compatible(main.unit, formatter.unit)
            others.append(formatter)
        return Leaderboard(main, others, asc)

def parse_leaderboard(text):
    return LeaderboardParser(text).rule()

def calc_value(row):
    return parse_leaderboard(row["main_unit"]).ureq(row["datum"])

async def accept_leaderboard(ctx, definition, *, compat=None):
    try:
        lb = parse_leaderboard(definition)
    except ParseError as e:
        raise commands.BadArgument(f"```ansi{e}```")
    if compat and not lb.main.unit.is_compatible_with(compat.main.unit):
        raise commands.BadArgument(f"The unit '{lb.main.unit:Pc}' is incompatible with the unit '{compat.main.unit:Pc}'.")
    if len(str(lb)) > 4000:
        raise commands.BadArgument("Definition is too long.")
    return lb

def rank_enumerate(xs, *, key, reverse=True):
    cur_idx = None
    cur_key = None
    for idx, x in enumerate(sorted(xs, key=key, reverse=reverse), start=1):
        if cur_key is None or key(x) != cur_key:
            cur_idx = idx
            cur_key = key(x)
        yield (cur_idx, x)

def render_graph(member_values):
    # Dimensions: len*120 + 120 x 720
    # Margins: 60 x 40
    base = Image.new('RGBA', (len(member_values) * 120, 720), (200, 200, 200, 0))
    max_value, min_value = max(x[0] for x in member_values), min(x[0] for x in member_values)
    diff = max_value - min_value
    if not diff:
        diff = 100
        min_value -= 100

    for i, (value, member, avatar) in enumerate(member_values):
        bar_value = math.ceil((value - min_value) * 680 / diff) + 40
        avatar = Image.open(BytesIO(avatar)).resize((120, bar_value)).convert('RGBA')
        base.alpha_composite(avatar, (120 * i, 720 - bar_value))

    rendered = BytesIO()
    base.save(rendered, format='png')
    rendered.seek(0)
    return rendered


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


class Qwd(commands.Cog, name="QWD"):
    """Commands for QWD."""

    def __init__(self, bot):
        self.bot = bot
        self.qwd = None

    def cog_check(self, ctx):
        if not self.qwd:
            self.qwd = self.bot.get_guild(1133026989637382144)
        return not ctx.guild and self.qwd.get_member(ctx.author.id) or ctx.guild == self.qwd

    @commands.group(invoke_without_command=True, aliases=["doxx"])
    @commands.guild_only()
    async def dox(self, ctx, *, target: discord.Member):
        """Reveal someone's address if they have set it through the bot. Must be used in a guild; the answer will be DMed to you."""
        p = get_pronouns(target)
        async with self.bot.db.execute("SELECT address FROM Addresses WHERE user_id = ?", (target.id,)) as cur:
            r = await cur.fetchone()
        if not r:
            return await ctx.send(f'{p.they_do_not()} have an address set.')
        await ctx.author.send(r[0])
        await ctx.send(f"Alright, I've DMed you {p.pos_det} address.")

    @dox.command(name="set")
    @commands.dm_only()
    async def set_dox(self, ctx, *, address=None):
        """Set your address to be doxxed by others. Must be used in a DM with the bot. You can clear your address by using `set` without an argument."""
        if address:
            await self.bot.db.execute("INSERT OR REPLACE INTO Addresses (user_id, address) VALUES (?, ?)", (ctx.author.id, address))
            await ctx.send("Successfully set your address.")
        else:
            await self.bot.db.execute("DELETE FROM Addresses WHERE user_id = ?", (ctx.author.id,))
            await ctx.send("Successfully cleared your address.")
        await self.bot.db.commit()

    async def lb_members(self, lb, *, reverse=False):
        async with self.bot.db.execute("SELECT user_id, datum, main_unit FROM LeaderboardData WHERE leaderboard = ?", (lb.name,)) as cur:
            r = [(calc_value(row), member) async for row in cur if (member := self.qwd.get_member(row["user_id"]))]
        return rank_enumerate(
            r,
            key=lambda x: x[0],
            reverse=lb.asc == reverse,
        )

    @commands.group(invoke_without_command=True, aliases=["lb"])
    async def leaderboard(self, ctx, lb: Leaderboard):
        """Show a leaderboard, given its name."""
        entries = []
        for i, (value, user) in await self.lb_members(lb):
            entries.append(rf"{i}\. {user.global_name or user.name} - {lb.format(value)}")
        embed = discord.Embed(title=f"The `{lb.display_name}` leaderboard", colour=discord.Colour(0x75ffe3), description="\n".join(entries))
        if not entries:
            embed.set_footer(text="Seems to be empty")
        await ctx.send(embed=embed)

    @leaderboard.command()
    async def get(self, ctx, lb: Leaderboard, *, member: discord.Member = None):
        """Get a specific person's number on a leaderboard."""
        member = member or ctx.author
        p = get_pronouns(member)
        async with self.bot.db.execute("SELECT datum, main_unit FROM LeaderboardData WHERE user_id = ? AND leaderboard = ?", (member.id, lb.name)) as cur:
            r = await cur.fetchone()
        if not r:
            return await ctx.send(f'{p.they_do_not()} have an entry in `{lb.name}`.')
        await ctx.send(embed=discord.Embed(title=f"{member.global_name or member.name}'s `{lb.display_name}`", description=lb.format(calc_value(r)), colour=discord.Colour(0x75ffe3)))

    @leaderboard.command()
    async def set(self, ctx, lb: Leaderboard, *, value=None):
        """Play nice. Don't test me."""
        if not value:
            await self.bot.db.execute("DELETE FROM LeaderboardData WHERE user_id = ? AND leaderboard = ?", (ctx.author.id, lb.name))
            await self.bot.db.commit()
            return await ctx.send("Done.")
        try:
            nice = lb.ureq(value)
        except (TokenError, UndefinedUnitError, AssertionError):
            return await ctx.send("I couldn't parse that as a sensible value.")
        except DimensionalityError:
            return await ctx.send(f"Unit mismatch: your unit is incompatible with the leaderboard's unit '{lb.main.unit:Pc}'.")
        await self.bot.db.execute("INSERT OR REPLACE INTO LeaderboardData (user_id, leaderboard, datum, main_unit) VALUES (?, ?, ?, ?)", (ctx.author.id, lb.name, value, lb.lean()))
        await self.bot.db.commit()
        await ctx.send(f"Okay, your value will display as {lb.format(nice)}.")

    async def leaderboard_exists(self, name):
        async with self.bot.db.execute("SELECT EXISTS(SELECT 1 FROM Leaderboards WHERE name = ?1 UNION SELECT 1 FROM LeaderboardAliases WHERE name = ?1)", (name,)) as cur:
            r, = await cur.fetchone()
        return r

    @leaderboard.command(aliases=["new", "add", "make"])
    async def create(self, ctx, name="", *, definition=""):
        """Create a leaderboard. WARNING: The syntax for this command is complex and you cannot remove leaderboards. Use `!help lb new` for more info.

        To make a leaderboard, you pass to this command the name of the command (in quotes if necessary) and its definition. The simplest leaderboards consist of a single unit, and look like this:
        `!lb create height cm`

        However, this leaderboard will only display values in centimetres. The `create` command has various formatting options to make output nicer. For starters, you can offer multiple choices of unit, like so:
        `!lb create height cm, in`

        This will show both centimeters and inches. However, people's heights are usually shown in feet *and* inches, so we can chain those units together with `+`.
        `!lb create height cm, ft+in`

        We probably want to show the shortest people first (I like them better), so we can also flip the sorting order.
        `!lb create height asc cm, ft+in`

        This is now a good height leaderboard, so let's explore the rest of the options by making a leaderboard for people's remaining disk space. The base unit should be gigabytes.
        `!lb create disk gigabytes`

        But some people have almost filled up their drives, while others have empty 2TB hard drives. We don't want to display 2TB values as "2000GB" or small values as "0GB". We could try to alleviate this by using `TB + GB + MB`, but the resulting strings are fairly ugly. Instead, we can use the `~` option to automatically scale the unit.
        `!lb create disk ~bytes`

        Now, no matter the number of bytes entered, the displayed value will scale correspondingly. The final option is the `.` operator, which allows us to specify more significant digits to show.
        `!lb create disk ~bytes.2`

        That's it! Now you know about all of `create`'s formatting features and how they can be used to make convenient leaderboards. Remember once again to be VERY careful with this command.
        """
        if not name or not definition:
            return await ctx.send("No definition provided. **Please** read the text of `!help lb create` in full to learn how to use this command. Refrain from using it lightly, as only LyricLy can remove leaderboards. And she will *not* like helping you. I promise.")
        if await self.leaderboard_exists(name):
            return await ctx.send("Aww, look at you! You should see how cute you look. Trying to harness forces you don't understand. This leaderboard already exists, you know?")
        lb = await accept_leaderboard(ctx, definition)
        await self.bot.db.execute("INSERT INTO Leaderboards (name, definition) VALUES (?, ?)", (name, str(lb)))
        await self.bot.db.commit()
        await ctx.send(f"Successfully created a new ``{name}`` leaderboard: ``{lb}``. You'd better not regret this. You can edit this leaderboard at any time.")

    @leaderboard.command(aliases=["link", "point", "ln"])
    async def alias(self, ctx, to_lb: Leaderboard, fro: str, *, definition=None):
        """Create a new alias to another leaderboard. You may specify a new way to format the values; the default is to use the formatting of the source leaderboard."""
        if await self.leaderboard_exists(fro):
            return await ctx.send("^w^\n\nName taken.")
        from_lb = await accept_leaderboard(ctx, definition, compat=to_lb) if definition else to_lb
        await self.bot.db.execute("INSERT INTO LeaderboardAliases (name, definition, source) VALUES (?, ?, ?)", (fro, str(from_lb), to_lb.name))
        await self.bot.db.commit()
        await ctx.send(f"Successfully created a new alias ``{fro}`` -> ``{to_lb.name}``: ``{from_lb}``. You can edit or delete this alias at any time.")

    @leaderboard.command(aliases=["delete"])
    async def remove(self, ctx, lb: Leaderboard):
        """Remove a leaderboard (as LyricLy) or leaderboard alias."""
        lyric = ctx.author.id == 319753218592866315
        if lyric:
            await self.bot.db.execute("DELETE FROM Leaderboards WHERE name = ?", (lb.display_name,))
        async with self.bot.db.execute("DELETE FROM LeaderboardAliases WHERE name = ?", (lb.display_name,)) as cur:
            if not cur.rowcount and not lyric:
                return await ctx.send("You're but a little kitty and can only delete aliases, not full leaderboards. Come back when you're a bit bigger.")
        await self.bot.db.commit()
        await ctx.send("Done.")

    @leaderboard.command(aliases=["modify", "update", "replace"])
    async def edit(self, ctx, old: Leaderboard, *, definition):
        """Edit a leaderboard's formatting definition."""
        new = await accept_leaderboard(ctx, definition, compat=old)
        await self.bot.db.execute("UPDATE Leaderboards SET definition = ? WHERE name = ?", (str(new), old.display_name))
        await self.bot.db.execute("UPDATE LeaderboardAliases SET definition = ? WHERE name = ?", (str(new), old.display_name))
        await self.bot.db.commit()
        await ctx.send("Done.")

    @leaderboard.command(aliases=["list"])
    async def all(self, ctx):
        """List all of the leaderboards."""
        paginator = EmbedPaginator()
        async with self.bot.db.execute("SELECT name, definition FROM Leaderboards") as cur:
            async for name, lb in cur:
                paginator.add_line(f"`{name}`: `{lb}`")
        paginator.embeds[0].title = "All leaderboards"
        for embed in paginator.embeds:
            await ctx.send(embed=embed)

    @leaderboard.command()
    async def graph(self, ctx, lb: Leaderboard):
        """Graph a (somewhat humorous) ranking of people's values in a leaderboard such as `height`."""
        people = [(value.m, user, await user.avatar.read()) for _, (value, user) in await self.lb_members(lb, reverse=True)]
        if not people:
            return await ctx.send("A leaderboard must have at least one person on it to use `graph`.")
        image = await asyncio.to_thread(render_graph, people)
        await ctx.send(file=discord.File(image, filename='height_graph.png'))

    @commands.group(invoke_without_command=True, aliases=["temp"])
    async def weather(self, ctx, *, target: Union[discord.Member, str] = ""):
        """Display current weather at a location or a user's stored location."""
        target = target or ctx.author
        if isinstance(target, discord.Member):
            p = get_pronouns(target)
            async with self.bot.db.execute("SELECT location FROM WeatherLocations WHERE user_id = ?", (target.id,)) as cur:
                r = await cur.fetchone()
            if not r:
                return await ctx.send(f"{p.they_do_not()} have a location set." if target != ctx.author else "You don't have a location set.")
            location, = r
        else:
            location = target

        async with self.bot.session.get(f"https://wttr.in/{location}", params={"format": "j1"}) as resp:
            if resp.status >= 400:
                return await ctx.send("Unknown location.")
            data = await resp.json()

        area = ", ".join([t for k in ["areaName", "region", "country"] if (t := data["nearest_area"][0][k][0]["value"])])
        current = data["current_condition"][0]
        c = current["temp_C"]
        f = current["temp_F"]
        weather = data["weather"][0]
        max_c = weather["maxtempC"]
        max_f = weather["maxtempF"]
        min_c = weather["mintempC"]
        min_f = weather["mintempF"]
        desc = current["weatherDesc"][0]["value"]

        embed = discord.Embed(
            title=f"Current weather in {area}",
            description=f"{desc}, {c}°C ({f}°F)\n\nToday's high: {max_c}°C ({max_f}°F)\nToday's low: {min_c}°C ({min_f}°F)"
        )
        await ctx.send(embed=embed)

    @weather.command(name="set")
    async def set_location(self, ctx, *, location=""):
        """Set your location to use for weather info. You can clear your location by using `set` without an argument.

        Accepted formats are those accepted by [wttr](https://wttr.in/:help). You probably want to use a city name, area code, or GPS coordinates.
        """
        async with self.bot.session.head(f"https://wttr.in/{location}") as resp:
            if resp.status >= 400:
                return await ctx.send("Unknown location. See the [wttr documentation](<https://wttr.in/:help>).")

        if not location:
            await self.bot.db.execute("DELETE FROM WeatherLocations WHERE user_id = ?", (ctx.author.id,))
            await ctx.send("Successfully cleared your location.")
        else:
            await self.bot.db.execute("INSERT OR REPLACE INTO WeatherLocations (user_id, location) VALUES (?, ?)", (ctx.author.id, location))
            await ctx.send("Successfully set your location.")
        await self.bot.db.commit()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild == self.qwd and message.content.startswith("!mja"):
            word1, word2 = message.content.split(" ", 1)
            try:
                n = int(word2.strip())
            except ValueError:
                return
            s = "mja" + word1.removeprefix("!mja") * n
            if len(s) >= 2000:
                return
            await message.channel.send(s)

    @commands.group(invoke_without_command=True)
    async def hwdyk(self, ctx):
        """How well do you know your friends?"""
        pass

    async def pick_random_message(self):
        base = datetime.datetime(year=2023, month=7, day=25)
        year = 2023
        channel = self.qwd.get_channel(1133026989637382149 if random.random() < .909 else 1133027144512049223)

        # this doesn't uniformly pick a random message: it strongly prefers messages sent after longer pauses
        # however this is a trade-off for making it incredibly cheap to grab a message because we don't have to spam history calls or store any data
        t = base + datetime.timedelta(milliseconds=random.randint(0, int((datetime.datetime.utcnow() - base).total_seconds() * 1000)))
        async for message in channel.history(before=t):
            if message.content and message.content.count(" ") > 3 and message.author in message.guild.members:
                break

        return message

    @commands.guild_only()
    @hwdyk.group(aliases=["msg"], invoke_without_command=True)
    async def message(self, ctx):
        """Pick a random message. If you can guess who sent it, you win!"""

        message = await self.pick_random_message()
        real_embed = message_embed(message)
        hidden_embed = real_embed.copy()
        hidden_embed.set_footer(text="#??? • ??/??/????")
        hidden_embed.set_author(name="❓  ???")
        hidden_embed.timestamp = None
        bot_msg = await ctx.reply("Who sent this message?", embed=hidden_embed)

        while True:
            r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                member = await commands.MemberConverter().convert(ctx, r.content)
            except commands.BadArgument:
                pass
            else:
                break

        # insert into stat db
        await self.bot.db.execute("INSERT INTO HwdykGames (player_id, guessed, actual) VALUES (?, ?, ?)", (ctx.author.id, member.id, message.author.id))
        await self.bot.db.commit()

        # reveal info
        await bot_msg.edit(embed=real_embed)

        if member == message.author:
            await r.reply("You were correct!")
        else:
            await r.reply("Too bad. Good luck with the next time!")

    @commands.guild_only()
    @message.command(aliases=["time"])
    async def when(self, ctx, difficulty: int = 4):
        """Pick some random messages. If you can guess what order they were sent in, you win!""" 

        if not 2 <= difficulty <= 8:
            return await ctx.send("Difficulty must be between 2 and 8.") 

        msgs = []
        for _ in range(difficulty):
            msgs.append(await self.pick_random_message())

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
    async def stats(self, ctx, *, member: discord.Member = None):
        embed = discord.Embed(title="`hwdyk msg` statistics", colour=discord.Colour(0x6b32a8))

        if not member:
            def key(r):
                return r["correct"] / r["total"]

            def render(rs):
                l = []
                for rank, (id, total, correct) in rs:
                    if rank > 5:
                        break
                    l.append(f"{rank}: <@{id}> - {correct}/{total} ({correct/total*100:.2f}%)")
                return "\n".join(l)

            async with self.bot.db.execute("SELECT player_id, COUNT(*) as total, SUM(actual = guessed) as correct FROM HwdykGames GROUP BY player_id HAVING total >= 35") as cur:
                embed.add_field(name="Best players", value=render(rank_enumerate(await cur.fetchall(), key=key)), inline=False)

            async with self.bot.db.execute("SELECT actual, COUNT(*) as total, SUM(actual = guessed) as correct FROM HwdykGames GROUP BY actual HAVING total >= 20") as cur:
                items = await cur.fetchall()
                embed.add_field(name="Hardest to guess", value=render(rank_enumerate(items, key=key, reverse=False)))
                embed.add_field(name="Easiest to guess", value=render(rank_enumerate(items, key=key, reverse=True)))

        else:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

            async with self.bot.db.execute("SELECT COUNT(*), SUM(actual = guessed) FROM HwdykGames WHERE player_id = ?", (member.id,)) as cur:
                total, correct = await cur.fetchone()

            async with self.bot.db.execute("SELECT COUNT(*), SUM(actual = guessed) FROM HwdykGames WHERE actual = ?", (member.id,)) as cur:
                total_total, correct_total = await cur.fetchone()

            embed.add_field(name="Times played", value=str(total))
            if total:
                embed.add_field(name="Correct answers", value=f"{correct} ({correct/total*100:.2f}%)")
            if not total_total:
                embed.set_footer(text=f"No message by {member.display_name} has appeared yet")
            else:
                embed.set_footer(text=f"Messages by {member.display_name} have appeared {total_total} times and been guessed correctly {correct_total} times ({correct_total/total_total*100:.2f}%)")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Qwd(bot))
