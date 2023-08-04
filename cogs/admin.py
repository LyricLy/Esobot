import asyncio
import io
import traceback

from . import get_extensions
from discord.ext import commands
from subprocess import PIPE
from constants import colors, emoji, info
from utils import l, make_embed, report_error


class Admin(commands.Cog):
    """Admin-only commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await commands.is_owner().predicate(ctx)

    @commands.command(aliases=["shutdown!"], hidden=True)
    async def shutdown(self, ctx):
        """Shut down the bot without asking for confirmation."""
        await ctx.send(
            embed=make_embed(
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
        embed = make_embed(color=colors.EMBED_INFO, title="Running `git pull`")
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
        embed = make_embed(color=colors.EMBED_INFO, title=title)
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
                description += f"Failed to load `{extension}`.\n"
                if not isinstance(exc, ImportError):
                    await report_error(ctx, exc, *extensions)
        description += "Done."
        await m.edit(
            embed=make_embed(
                color=color, title=title.replace("ing", "ed"), description=description
            )
        )


async def setup(bot):
    await bot.add_cog(Admin(bot))
