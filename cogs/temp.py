import datetime
import io
import os
import random
import uuid
import re
import unicodedata
from typing import Optional

import discord
from discord.ext import commands, tasks
from PIL import Image, ImageOps


@commands.check
def is_in_esolangs(ctx):
    if ctx.guild.id != 346530916832903169:
        raise commands.CommandNotFound()
    return True

@commands.check
def is_olivia(ctx):
    if ctx.author.id not in (156021301654454272, 319753218592866315):
        raise commands.CommandNotFound()
    return True

class Temporary(commands.Cog):
    """Temporary, seasonal, random and miscellaneous poorly-written functionality. Things in here should probably be developed further or removed at some point."""

    def __init__(self, bot):
        self.bot = bot
        self.last_10 = None
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

        if (parts := message.content.split(" ", 1))[0] == "?chairinfo":
            lines = []
            for c in parts[1]:
                name = unicodedata.name(c, "")
                if m := re.fullmatch(r"(.*)LATIN SMALL LETTER (.*)\bH\b(.*)", name):
                    title = f"{m[1]}{m[2]}CHAIR{m[3]}"
                elif m := re.fullmatch(r"CYRILLIC (.*)LETTER (.*)\bCHE\b(.*)", name):
                    title = f"TURNED {m[1].replace('CAPITAL', 'BIG')}{m[2]}CHAIR{m[3]}"
                else:
                    title = {
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
                lines.append(f"`\\U{ord(c):>08x}`: {title} - {c}")
            await message.channel.send("\n".join(lines))

async def setup(bot):
    await bot.add_cog(Temporary(bot))
