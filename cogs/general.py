import asyncio
import discord
import io
from typing import Optional
from PIL import Image, ImageOps

from discord.ext import commands
from constants import colors, info, emoji


class EsobotHelp(commands.MinimalHelpCommand):
    def add_bot_commands_formatting(self, commands, heading):
        if commands:
            self.paginator.add_line(f"**{heading}**")
            self.paginator.add_line("\n".join(f"• ``{c.name}``{' — ' + c.short_doc if c.short_doc else ''}" for c in commands))

    async def send_pages(self):
        dest = self.get_destination()
        for page in self.paginator.pages:
            await dest.send(embed=discord.Embed(title="Help", description=page, color=colors.EMBED_HELP))

    def add_aliases_formatting(self, aliases):
        self.paginator.add_line(f"**Aliases:** ``{'``, ``'.join(aliases)}``", empty=True)

    def add_command_formatting(self, command):
        if command.description:
            self.paginator.add_line(command.description, empty=True)

        signature = self.get_command_signature(command)
        if command.aliases:
            self.paginator.add_line(f"``{signature}``")
            self.add_aliases_formatting(command.aliases)
        else:
            self.paginator.add_line(f"``{signature}``", empty=True)

        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()


class General(commands.Cog):
    """General-purpose commands."""

    def __init__(self, bot):
        self.bot = bot
        self.original_help = bot.help_command
        bot.help_command = EsobotHelp(command_attrs={"brief": "Show this message.", "help": "Show information for all commands or for specific commands, like this."})
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.original_help

    @commands.command(aliases=["i", "info"])
    async def about(self, ctx):
        """Information about the bot."""
        await ctx.send(
            embed=discord.Embed(
                title=f"About {info.NAME}",
                description=info.ABOUT_TEXT,
            ).add_field(name="Author", value=f"[{info.AUTHOR}]({info.AUTHOR_LINK})")
             .add_field(name="GitHub", value=info.GITHUB_LINK)
             .set_footer(text=f"{info.NAME} v{info.VERSION}")
        )

    @commands.command()
    async def identicon(self, ctx, username: str, color: Optional[discord.Colour] = discord.Colour(0xF0F0F0), alpha: float = 0.0):
        """Send someone's GitHub identicon. `color` and `alpha` control the background colour.

        To the late kappanneo, the identitalian
        """

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


async def setup(bot):
    await bot.add_cog(General(bot))
