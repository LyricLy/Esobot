import datetime
import asyncio

import discord
from discord.ext import commands
from typing import Optional

from . import QwdBase


class QwdInterp(QwdBase, name="Interpretation (QWD)"):
    """Interpreting content for the benefit of all QWD!"""

    @commands.Cog.listener("on_message")
    async def cc_watchfox(self, message):
        if message.guild != self.qwd:
            return
        if not any(attachment.content_type.startswith(("audio", "video")) for attachment in message.attachments):
            await asyncio.sleep(1)
            try:
                await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return
            if not any(embed.video.url and embed.type != "gifv" for embed in message.embeds):
                return
        await self.bot.db.execute("INSERT INTO CCReacts (message_id) VALUES (?)", (message.id,))
        await self.bot.db.commit()
        await message.add_reaction("<:missing_captions:1358721100695076944>")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.id != 1358721100695076944 or payload.guild_id != self.qwd.id or payload.member == self.bot.user:
            return
        part_msg = self.bot.get_partial_messageable(payload.channel_id).get_partial_message(payload.message_id)
        await part_msg.remove_reaction(payload.emoji, self.bot.user)
        await part_msg.remove_reaction(payload.emoji, payload.member)
        await self.bot.db.execute(
            "UPDATE CCReacts SET cleared_by = COALESCE(cleared_by, ?), cleared_at = COALESCE(cleared_at, ?) WHERE message_id = ?",
            (payload.member.id, datetime.datetime.now(datetime.timezone.utc), part_msg.id),
        )
        await self.bot.db.commit()

    @commands.command()
    async def watchfox(self, ctx, *, message: discord.Message = None):
        """Ask Cici about a particular message."""
        message = message or (r := ctx.message.reference) and r.resolved
        if not message:
            return await ctx.send("Please reply to a message or provide a message ID.")
        async with self.bot.db.execute("SELECT cleared_by, cleared_at FROM CCReacts WHERE message_id = ?", (message.id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return await ctx.send("I never reacted with <:missing_captions:1358721100695076944> to that message.")
        cleared_by, cleared_at = row
        if not cleared_by:
            return await ctx.send("My reaction is still there, silly!")
        await ctx.send(
            f"I reacted with <:missing_captions:1358721100695076944> to that message, and <@{cleared_by}> cleared it on {discord.utils.format_dt(cleared_at)}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(QwdInterp(bot))
