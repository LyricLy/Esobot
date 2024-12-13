import asyncio
import time
import os
import random
import datetime
from typing import Union, Optional

import discord
from discord.ext import commands, tasks


Targets = commands.Greedy[discord.Member]
HackTargets = commands.Greedy[Union[discord.Member, int]]

LIME_PATH = "./assets/limes"

class Guild(commands.Cog):
    """Management of the server itself."""

    def __init__(self, bot):
        self.bot = bot
        self.pride_loop.start()

    def cog_unload(self):
        self.pride_loop.cancel()

    # 12PM UTC
    @tasks.loop(
        time=datetime.time(12),
    )
    async def pride_loop(self):
        async with self.bot.db.execute("SELECT filename FROM Limes ORDER BY RANDOM() LIMIT 1") as cur:
            r = await cur.fetchone()
        if r:
            name, = r
        else:
            l = os.listdir(LIME_PATH)
            for file in l:
                await self.bot.db.execute("INSERT INTO Limes (filename) VALUES (?)", (file,))
            name = random.choice(l)

        await self.bot.db.execute("DELETE FROM Limes WHERE filename = ?", (name,))
        await self.bot.db.commit()
        with open(f"{LIME_PATH}/{name}", "rb") as f:
            d = f.read()
        await self.bot.get_guild(346530916832903169).edit(icon=d)

    @pride_loop.before_loop
    async def before_pride_loop(self):
        await self.bot.wait_until_ready()

    async def confirm(self, ctx, targets, reason, verb, *, forbidden_fail=True):
        ss = [str(x) if isinstance(x, int) else x.mention for x in targets]
        if len(targets) == 1:
            users = f"the user {ss[0]}"
        else:
            users = f"{len(targets)} users ({', '.join(ss)})"

        embed = discord.Embed(title="Are you sure?", description=f"You are about to {ctx.command.name} {users}. Please confirm the following things.")

        embed.add_field(name="Warned?", value="Have you given the users due warning? If their infractions are minor, consider a verbal caution before taking action.")
        embed.add_field(name="Legitimacy", value=f"Take care not to {ctx.command.name} for insincere reasons such as jokes, as intimidation or due to corruption. \
                                                   Ensure your punishment is proportional to the severity of the rule violation you are punishing.")

        if not reason:
            embed.add_field(name="No reason?", value="Consider adding a reason for your action. This will inform the users of your reasoning, as well as storing it in the audit log for future reference.")
        embed.set_footer(text="If you're certain you want to proceed, click the checkmark emoji below. If you've rethought your decision, click the X.")

        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        r, _ = await self.bot.wait_for("reaction_add", check=lambda r, u: str(r.emoji) in ("✅", "❌") and r.message.id == msg.id and u == ctx.author)

        await msg.delete()
        if str(r.emoji) == "✅":
            if reason:
                good = []
                for target in targets:
                    if isinstance(target, int):
                        good.append(discord.Object(id=target))
                    else:
                        try:
                            await target.send(f"You've been {verb} for the following reason: {reason}")
                        except discord.Forbidden:
                            msg = f"Couldn't DM {target}."
                            if forbidden_fail:
                                await ctx.send(msg)
                                continue
                            elif target not in ctx.message.mentions:
                                msg += f" Mentioning instead: {target.mention}"
                                await ctx.send(msg)
                        good.append(target)
                return good
            else:
                return targets
        else:
            return []

    async def perform(self, ctx, unconfirmed_targets, method, verb, reason, confirm=True, **kwargs):
        if confirm:
            targets = await self.confirm(ctx, unconfirmed_targets, reason, verb.lower())
        else:
            targets = unconfirmed_targets
        if not targets:
            return await ctx.send("Nothing to do. Stop.")

        message = []
        successful = []
        for target in targets:
            if isinstance(target, discord.Member) and ctx.author.top_role <= target.top_role:
                message.append(f"You're a lower rank than {target}.")
                continue
            try:
                await method(target, reason=reason, **kwargs)
            except discord.HTTPException as e:
                message.append(f"Operation failed on {target}: {e}")
            else:
                successful.append(target)

        if successful:
            if len(successful) == 1:
                message.append(f"{verb} {successful[0]}.")
            elif len(successful) == 2:
                message.append(f"{verb} {successful[0]} and {successful[1]}.")
            elif len(successful) < 5:
                message.append(f"{verb} {', '.join(successful[:-1])}, and {successful[-1]}.")
            else:
                message.append(f"{verb} {len(successful)} users.")
        await ctx.send("\n".join(message))

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, targets: HackTargets, *, reason=None):
        """Ban a member."""
        await self.perform(ctx, targets, ctx.guild.ban, "Banned", reason, delete_message_seconds=0)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, targets: HackTargets, *, reason=None):
        """Unban a user."""
        await self.perform(ctx, targets, ctx.guild.unban, "Unbanned", reason, confirm=False)

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, targets: Targets, *, reason=None):
        """Kick a user."""
        await self.perform(ctx, targets, ctx.guild.kick, "Kicked", reason)


async def setup(bot):
    await bot.add_cog(Guild(bot))
