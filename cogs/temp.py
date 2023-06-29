import asyncio
import datetime
import io
import os
import random
import uuid
import shlex
import re
from textwrap import dedent
from typing import Optional
from collections import defaultdict

import discord
from discord.ext import commands, tasks
from PIL import Image, ImageOps

from constants.paths import QWD_SAVES
from utils import aggressive_normalize, load_json, save_json, get_pronouns


@commands.check
def is_in_esolangs(ctx):
    if ctx.guild.id != 346530916832903169:
        raise commands.CommandNotFound()
    return True

@commands.check
def is_in_qwd(ctx):
    if ctx.guild.id != 1047299292492206101:
        raise commands.CommandNotFound()
    return True

@commands.check
def is_olivia(ctx):
    if ctx.author.id not in (156021301654454272, 319753218592866315):
        raise commands.CommandNotFound()
    return True

def parse_height(s):
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    match [float(x) if "." in x else int(x) for x in nums]:
        case [cm]:
            return cm
        case [feet, inches]:
            return int(2.54 * (feet*12 + inches))
        case [feet, in_top, in_bottom]: 
            return int(2.54 * (feet*12 + in_top/in_bottom))
        case [feet, in_whole, in_top, in_bottom]:
            return int(2.54 * (feet*12 + in_whole + in_top/in_bottom))
        case _:
            raise commands.BadArgument("couldn't parse height")

def show_height(cm):
    base_in = cm / 2.54
    feet, inches = divmod(base_in, 12)
    return f"{cm:.{int(isinstance(cm, float))}f}cm ({feet:.0f}'{inches:.0f}\")"

def rank_enumerate(xs, *, key):
    cur_idx = None
    cur_key = None
    for idx, x in enumerate(sorted(xs, key=key), start=1):
        if cur_key is None or key(x) >= cur_key:
            cur_idx = idx
            cur_key = key(x)
        yield (cur_idx, x)

class Temporary(commands.Cog):
    """Temporary, seasonal, random and miscellaneous poorly-written functionality. Things in here should probably be developed further or removed at some point."""

    def __init__(self, bot):
        self.bot = bot
        self.last_10 = None
        self.qwdies = defaultdict(dict, load_json(QWD_SAVES))
        self.pride_loop.start()

    def cog_unload(self):
        self.pride_loop.cancel()

    # 12PM UTC
    @tasks.loop(
        time=datetime.time(12),
    )
    async def pride_loop(self):
        PATH = "./assets/limes/"
        l = sorted(os.listdir(PATH))
        if "index" in l:
            with open(PATH + "index") as f:
                i = int(f.read())
        else:
            random.shuffle(l)
            for i, f in enumerate(l):
                name = f"{i:0>{len(str(len(l)))}}-{uuid.uuid4()}"
                os.replace(PATH + f, PATH + name)
                l[i] = name
            i = 0
        next_lime = l[i]
        i += 1
        if i >= len(l)-1:
            os.remove(PATH + "index")
        else:
            with open(PATH + "index", "w") as f:
                f.write(str(i))
        with open(PATH + next_lime, "rb") as f:
            d = f.read()
        await self.bot.get_guild(346530916832903169).edit(icon=d)

    @pride_loop.before_loop
    async def before_pride_loop(self):
        await self.bot.wait_until_ready()

    # def get_members(self, channel, *, excluding=None):
    #     if channel.category.id != 730233425251794983:
    #         return None
    #     l = [m for m in channel.members if not any(r.name in ("Administrators", "Esobot") for r in m.roles) and m != excluding]
    #     return l if 1 <= len(l) <= 2 else None

    # @commands.command()
    # async def start(self, ctx):
    #     try:
    #         partner = self.get_members(ctx.channel, excluding=ctx.author)[0]
    #     except TypeError:
    #         return await ctx.send("You're not in a game channel.")
    #     await ctx.send(f"Beginning a start request. Your partner, {partner}, must agree to begin the event in 30 seconds by typing `!accept`!")
    #     try:
    #         await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.content == "!accept", timeout=30)
    #     except asyncio.TimeoutError:
    #         await ctx.send("Request not accepted.")
    #     else:
    #         await ctx.send("Let the games begin!")
    #         playing = ctx.guild.get_role(730594078584078378)
    #         await ctx.author.add_roles(playing)
    #         await partner.add_roles(playing)
    #         await self.bot.get_channel(730593893195710525).send(f"Game started in {ctx.channel.mention}.")

    # @commands.command()
    # async def submit(self, ctx, *, text: commands.clean_content = ""):
    #     """Submit your submission for the event. Accepts a text argument, which should be a URL or similar to your solution. Sends everything to a logging channel to be verified."""
    #     try:
    #         partner = self.get_members(ctx.channel, excluding=ctx.author)[0]
    #     except TypeError:
    #         return await ctx.send("You're not in a game channel.")
    #     playing = ctx.guild.get_role(730594078584078378)
    #     if playing not in ctx.author.roles or playing not in partner.roles:
    #         await ctx.send("You have to be playing to submit.")
    #     await ctx.send("Ending the game. Look over this and make absolutely certain that it is correct! You can't take back your submission! Your partner must agree to submit in 60 seconds by typing `!accept`.")
    #     try:
    #         await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.content == "!accept", timeout=60)
    #     except asyncio.TimeoutError:
    #         await ctx.send("Request not accepted.")
    #     else:
    #         await ctx.author.remove_roles(playing)
    #         await partner.remove_roles(playing)
    #         await self.bot.get_channel(730593893195710525).send(f"{ctx.channel.mention} finished with the following submission: {text}")

    @commands.command()
    async def identicon(self, ctx, username: str, color: Optional[discord.Colour] = discord.Colour(0xF0F0F0), alpha: float = 0.0):
        """Send someone's GitHub identicon. `color` and `alpha` control the background colour."""

        if not 0 <= alpha <= 1.0:
            return await ctx.send("`alpha` must be between 0 and 1.")
        colour = (*color.to_rgb(), int(255*alpha))

        async with self.bot.session.get(f"https://github.com/identicons/{username}.png") as resp:
            if resp.status != 200:
                return await ctx.send("404ed trying to access that identicon.")
            b = io.BytesIO(await resp.read())

        i = Image.open(b, formats=["png"]).convert("RGBA")

        # this sucks
        default = (0xF0, 0xF0, 0xF0, 0xFF)
        w, h = i.size
        if colour != default:
            data = i.load()
            for y in range(h):
                for x in range(w):
                    if data[x, y] == default:
                        data[x, y] = colour

        i2 = Image.new("RGBA", (512, 512), colour)
        i2.paste(i, ((512-w)//2, (512-h)//2))

        b.seek(0)
        i2.save(b, "png")
        b.truncate()
        b.seek(0)
        await ctx.send(file=discord.File(b, "result.png"))

    @commands.group(invoke_without_command=True, aliases=["doxx"])
    @is_in_qwd
    async def dox(self, ctx, *, target: discord.Member):
        """Reveal someone's address if they have set it through the bot. Must be used in a guild; the answer will be DMed to you."""
        p = get_pronouns(target)
        if not (addr := self.qwdies[str(target.id)].get("address")):
            return await ctx.send(f'{p.Subj()} {p.plrnt("do", "es")} have an address set.')
        await ctx.author.send(addr)
        await ctx.send(f"Alright, I've DMed you {p.pos_det} address.")

    @dox.command()
    @commands.dm_only()
    async def set(self, ctx, *, address=""):
        """Set your address to be doxxed by others. Must be used in a DM with the bot. You can clear your address by using `set` without an argument."""
        self.qwdies[str(ctx.author.id)]["address"] = address
        save_json(QWD_SAVES, self.qwdies)
        if not address:
            await ctx.send("Successfully cleared your address.")
        else:
            await ctx.send("Successfully set your address.")     

    @commands.group(invoke_without_command=True)
    @is_in_qwd
    async def height(self, ctx, *, person: discord.Member = None):
        """Show someone's height if they have set it through the bot."""
        target = person or ctx.author
        p = get_pronouns(target)
        if not (height := self.qwdies[str(target.id)].get("height")):
            return await ctx.send(f'{p.Subj()} {p.plrnt("do", "es")} have a height set.')
        they_are = p.are() if person else "You're"
        await ctx.send(f"{they_are} {show_height(height)} tall.")

    @height.command(aliases=["lb", "top"])
    @is_in_qwd
    async def leaderboard(self, ctx):
        """Show a ranking of people's heights."""
        people = []
        for k, v in self.qwdies.items():
            height = v.get("height")
            member = ctx.guild.get_member(int(k))
            if not height or not member:
                continue
            people.append((height, member))

        entries = []
        for i, (height, member) in rank_enumerate(people, key=lambda x: (x[0], x[1].global_name)):
            entries.append(rf"{i}\. {member.global_name} - {show_height(height)}")
        embed = discord.Embed(title="The shortest qwdies", colour=discord.Colour(0x75ffe3), description="\n".join(entries))
        await ctx.send(embed=embed)

    @height.command()
    @is_in_qwd
    async def set(self, ctx, *, height: parse_height):
        """Set your height (in cm or ft/in) for the height leaderboard. You can clear your height by passing `0`."""
        if height < 50:
            try:
                del self.qwdies[str(ctx.author.id)]["height"]
            except KeyError:
                await ctx.send("Did nothing.")
            else:
                await ctx.send("Successfully cleared your height.")
        else:
            self.qwdies[str(ctx.author.id)]["height"] = height
            await ctx.send(f"I set your height to {show_height(height)}.")
        save_json(QWD_SAVES, self.qwdies)

    @commands.group(hidden=True, invoke_without_command=True)
    async def olivia(self, ctx):
        pass

    @olivia.command(name="time", hidden=True)
    @is_in_esolangs
    async def _time(self, ctx):
        await self.bot.get_command("time")(ctx, user=ctx.guild.get_member(156021301654454272))

    @commands.group(hidden=True, invoke_without_command=True, aliases=["ky", "kay", "k"])
    async def kaylynn(self, ctx):
        pass

    @kaylynn.command(name="time", hidden=True)
    @is_in_esolangs
    async def _time2(self, ctx):
        await self.bot.get_command("time")(ctx, user=ctx.guild.get_member(636797375184240640))

    @kaylynn.command(hidden=True)
    async def cute(self, ctx):
        if ctx.guild.id == 346530916832903169:
            await ctx.send("yeah!")

    @commands.group(hidden=True, invoke_without_command=True)
    async def soup(self, ctx):
        pass

    @soup.command(name="time", hidden=True)
    @is_in_esolangs
    @is_olivia
    async def _time3(self, ctx):
        await ctx.send("<@636797375184240640> <@309787486278909952> <@319753218592866315> <@224379582785126401> <@166910808305958914> <@275982450432147456> soup time !!")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user and len(message.content.split(" ")) == 10:
            self.last_10 = message.created_at
        if self.last_10 and message.author.id == 509849474647064576 and len(message.content.split(" ")) == 10 and (message.created_at - self.last_10).total_seconds() < 1.0:
            await message.delete()

        if message.author.id == 319753218592866315 and message.content.count("night") >= 10:
            msg = ""
            c = 0
            for idx, word in enumerate(message.content.split(), start=1):
                if word == "night":
                    c += 1
                else:
                    msg += f"Word {idx} is misspelled: ``{word}``\n"
            msg += f"That's {c}."
            await message.channel.send(msg)

        if (parts := message.content.split(' ', maxsplit=1))[0] == "?chairinfo":
            from unicodedata import name
            string = ""
            for c in parts[1]:
                string+=f"\n`\\U{ord(c):>08}`: {c} "
                if (m := re.fullmatch(r"(.*)LATIN SMALL LETTER (.*)\bH (.*)", name(c, "")+" ")):
                    string += f"{m[1]+m[2]}CHAIR {m[3]}".strip()
                    continue
                if (m := re.fullmatch(r"CYRILLIC (.*)LETTER (.*)CHE (.*)", name(c, "")+" ")):
                    string += f"TURNED {m[1].replace('CAPITAL','BIG')+m[2]}CHAIR {m[3]}".strip()
                    continue
                string += {
                    "🪑": "CHAIR", "💺": "CHAIR", "🛋️": "DOUBLE CHAIR", "⑁": "OPTICAL CHARACTER RECOGNIZABLE CHAIR",
                    "♿": "SYMBOLIC WHEELED CHAIR", "🦽": "MANUAL WHEELED CHAIR", "🦼": "AUTOMATIC WHEELED CHAIR",
                    "µ": "VERTICALLY-FLIPPED CHAIR", "ɥ": "TURNED CHAIR", "ɰ": "DOUBLE TURNED CHAIR",
                    "ꜧ": "UNEVEN CHAIR", "ћ": "SLAVIC CHAIR WITH STROKE", "ђ": "UNEVEN CHAIR WITH STROKE",
                    "Һ": "SLAVIC BIG CHAIR", "һ": "SLAVIC SMALL CHAIR",
                    "Ꚕ": "SLAVIC BIG CHAIR WITH HOOK", "ꚕ": "SLAVIC SMALL CHAIR WITH HOOK",
                    "Ԧ": "SLAVIC BIG CHAIR WITH DESCENDER", "ԧ": "SLAVIC SMALL CHAIR WITH DESCENDER",
                    "Ի": "BIG CHAIR WITH SHORT LEG", "ի": "SMALL CHAIR WITH LONG LEG",
                    "Կ": "TURNED BIG CHAIR WITH SHORT LEG", "կ": "TURNED SMALL CHAIR WITH LONG LEG",
                    "Ϧ": "FANCY CHAIR", "փ": "ABOMINATION",
                    "Ⴗ": "GEORGIAN TURNED CHAIR",
                    "۲": "NUMERIC VERTICALLY-FLIPPED CHAIR", "ށ": "CURSIVE VERTICALLY-FLIPPED CHAIR",
                    "Ꮒ": "BIG CHAIR", "Ꮵ": "FANCY CHAIR",
                    "ᖹ": "HORIZONTALLY-FLIPPED SYLLABIC CHAIR", "ᖺ": "SYLLABIC CHAIR", "ᖻ": "TURNED SYLLABIC CHAIR",
                    "ᚴ": "VERTICALLY-FLIPPED NORDIC CHAIR",
                    "ℎ": "ITALIC CHAIR", "ℏ": "ITALIC CHAIR WITH STROKE"
                }.get(c, "NOT A CHAIR")
        await message.channel.send(string)

async def setup(bot):
    await bot.add_cog(Temporary(bot))
