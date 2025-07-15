import math
import asyncio
from io import BytesIO
from tokenize import TokenError

import discord
from PIL import Image
from discord.ext import commands, tasks
from pint import UnitRegistry, UndefinedUnitError, DimensionalityError, formatting, register_unit_format
from typing import Union

from . import QwdBase, chitterclass, myself
from utils import EmbedPaginator, rank_enumerate


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


@chitterclass(1394562583348121620, listen_to=myself)
class QwdieTimezone:
    member: discord.Member
    timezone: str


class QwdInfo(QwdBase, name="User info (QWD)"):
    """QWD commands dealing with user-provided information."""

    async def cog_load(self):
        await super().cog_load()
        await QwdieTimezone.sync(self.bot)
        self.sync_times.start()

    def cog_unload(self):
        self.sync_times.cancel()

    @tasks.loop(minutes=5)
    async def sync_times(self):
        async with self.bot.db.execute("SELECT * FROM Timezones") as cur:
            rows = await cur.fetchall()

        ours = {m: tz for user, tz in rows if (m := QwdBase.qwd.get_member(user))}

        for row in list(QwdieTimezone.rows()):
            if not isinstance(row.member, discord.Member) or not (our := ours.get(row.member)):
                await row.delete()
                continue
            if row.timezone != our:
                await row.update(timezone=our)
            ours.pop(row.member)

        for user, tz in ours.items():
            await QwdieTimezone.insert(user, tz)

    @commands.group(invoke_without_command=True, aliases=["doxx"])
    @commands.guild_only()
    async def dox(self, ctx, *, target: discord.Member):
        """Reveal someone's address if they have set it through the bot. Must be used in a guild; the answer will be DMed to you."""
        p = ctx.get_pronouns(target)
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
        p = ctx.get_pronouns(member)
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
            p = ctx.get_pronouns(target)
            async with self.bot.db.execute("SELECT location FROM WeatherLocations WHERE user_id = ?", (target.id,)) as cur:
                r = await cur.fetchone()
            if not r:
                return await ctx.send(f"{p.they_do_not()} have a location set.")
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


async def setup(bot):
    await bot.add_cog(QwdInfo(bot))
