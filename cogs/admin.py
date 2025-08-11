import asyncio
import discord
import random
import io
import traceback

from . import get_extensions
from discord.ext import commands
from subprocess import PIPE
from constants import colors, emoji, info
from utils import l


class Admin(commands.Cog):
    """Admin-only commands."""

    def __init__(self, bot):
        self.bot = bot
        self.emoji_map = None

    async def cog_check(self, ctx):
        return await commands.is_owner().predicate(ctx)

    @commands.command(aliases=["ise"])
    async def ize(self, ctx, emoji: discord.PartialEmoji | str, *, code):
        if isinstance(emoji, str):
            name = "-".join(f"{ord(c):x}" for c in emoji)
            img_url = f"https://raw.githubusercontent.com/jdecked/twemoji/refs/heads/main/assets/svg/{name}.svg"
        else:
            # DANNY
            img_url = (emoji.url.rsplit(".", 1)[0] + ".webp") + "?animated=true"*emoji.animated

        async with self.bot.session.get(img_url) as resp:
            if resp.status == 404:
                return await ctx.send("That's not an emoji...")
            img = await resp.read()

        proc = await asyncio.create_subprocess_shell(f"magick -background none -density 512 - {code} webp:-", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate(img)

        name = f"ized_{random.randrange(10000)}"
        emoji = await self.bot.get_guild(318633320890236930).create_custom_emoji(name=name, image=out)
        await ctx.send(f"{emoji}")

    @commands.command(aliases=["shutdown!"], hidden=True)
    async def shutdown(self, ctx):
        """Shut down the bot without asking for confirmation."""
        await ctx.send(
            embed=discord.Embed(
                color=colors.EMBED_INFO,
                title="Shutting down..."
            )
        )
        l.info(
            f"Shutting down at the command of {ctx.message.author.display_name}..."
        )
        await self.bot.close()

    @commands.command()
    async def update(self, ctx):
        """Run `git pull` to update the bot."""
        subproc = await asyncio.create_subprocess_shell("git fetch && git log ..@{u} && git merge", stdout=PIPE, stderr=PIPE)
        embed = discord.Embed(color=colors.EMBED_INFO, title="Running `git pull`")
        m = await ctx.send(embed=embed)
        returncode = await subproc.wait()
        embed.color = colors.EMBED_ERROR if returncode else colors.EMBED_SUCCESS
        stdout, stderr = await subproc.communicate()
        fields = []
        if stdout:
            embed.add_field(
                name="stdout", value=f"```\n{stdout.decode()}\n```", inline=False
            )
        if stderr:
            embed.add_field(
                name="stderr", value=f"```\n{stderr.decode()}\n```", inline=False
            )
        await m.edit(embed=embed)
        await self.reload_(ctx, "*")

    @commands.command(aliases=["r"])
    async def reload(self, ctx, *, extensions: str = "*"):
        """Reload an extension.

        Use `reload *` to reload all extensions.

        This command is automatically run by `update`.
        """
        await self.reload_(ctx, *extensions.split())

    async def reload_(self, ctx, *extensions):
        if "*" in extensions:
            title = "Reloading all extensions"
        elif len(extensions) > 1:
            title = "Reloading extensions"
        else:
            title = f"Reloading `{extensions[0]}`"
        embed = discord.Embed(color=colors.EMBED_INFO, title=title)
        m = await ctx.send(embed=embed)
        color = colors.EMBED_SUCCESS
        description = ""
        if "*" in extensions:
            extensions = get_extensions()
        for extension in extensions:
            try:
                await self.bot.unload_extension("cogs." + extension)
            except commands.ExtensionNotLoaded:
                pass
            try:
                await self.bot.load_extension("cogs." + extension)
                description += f"Successfully loaded `{extension}`.\n"
            except Exception as exc:
                color = colors.EMBED_ERROR
                description += f"Failed to load `{extension}`: {exc}\n"
        description += "Done."
        await m.edit(
            embed=discord.Embed(
                color=color, title=title.replace("ing", "ed"), description=description
            )
        )


async def setup(bot):
    await bot.add_cog(Admin(bot))
