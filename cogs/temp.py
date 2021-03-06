from textwrap import dedent
import io

import asyncio
import discord
from discord.ext import commands


class Temporary(commands.Cog):
    """Temporary, seasonal, random and miscellaneous poorly-written functionality. Things in here should probably be developed further or removed at some point."""

    def __init__(self, bot):
        self.bot = bot

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


def setup(bot):
    bot.add_cog(Temporary(bot))
