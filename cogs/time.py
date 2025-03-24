import asyncio
import datetime
import discord
import json
import pytz
import time
import traceback
import itertools

from constants import colors, channels
from discord.ext import commands, tasks
from utils import EmbedPaginator, clean, show_error, get_pronouns


class Time(commands.Cog):
    """Commands related to time and delaying messages."""

    def __init__(self, bot):
        self.bot = bot
        self.time_loop.start()

    def cog_unload(self):
        self.time_loop.cancel()

    @staticmethod
    def get_time(timezone_name):
        timezone = pytz.timezone(timezone_name)
        now = datetime.datetime.now().astimezone(timezone)
        t = now + datetime.timedelta(minutes=15)
        emoji = chr(ord("🕐") + (t.hour-1)%12 + 12*(t.minute > 30))
        return now.strftime(f"{emoji} **%H:%M** (**%I:%M%p**) on %A (%Z, UTC%z)")

    @commands.group(aliases=["tz", "when", "t"], invoke_without_command=True)
    async def time(self, ctx, *, user: discord.Member = None):
        """Get a user's time."""
        user = ctx.author if not user else user
        async with self.bot.db.execute("SELECT timezone FROM Timezones WHERE user_id = ?", (user.id,)) as cur:
            t = await cur.fetchone()
        if not t:
            p = ctx.get_pronouns(user)
            message = f'{p.they_do_not()} have a timezone set.'
            return await show_error(ctx, message, "Timezone not set")
        time = Time.get_time(t[0])
        embed = discord.Embed(
            title=f"{discord.utils.escape_markdown(user.display_name)}'s time",
            description=time,
            color=colors.EMBED_SUCCESS,
        )
        if user.id == 319753218592866315:
            p = get_pronouns(user)
            embed.add_field(name="Warning", value=f"This user's schedule is unstable and rather arbitrary. Apply caution before using {p.pos_det} current time to extrapolate information.")
        await ctx.send(embed=embed)

    @time.command()
    async def set(self, ctx, timezone=None):
        """Set a timezone for you in the database."""
        url = "https://github.com/sdispater/pytzdata/blob/master/pytzdata/_timezones.py"
        if not timezone:
            return await show_error(ctx, message=f"You can see a list of valid timezone names [here]({url}).", title="No timezone passed")
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            return await show_error(
                ctx,
                message=f"Read a list of valid timezone names [here]({url}).",
                title="Invalid timezone",
            )
        await self.bot.db.execute("INSERT OR REPLACE INTO Timezones (user_id, timezone) VALUES (?, ?)", (ctx.author.id, timezone))
        await self.bot.db.commit()
        await self.update_times()

        await ctx.send(
            embed=discord.Embed(
                title="Set timezone",
                description=f"Your timezone is now {timezone}.",
                color=colors.EMBED_SUCCESS,
            )
        )


    @time.command(aliases=["remove"])
    async def unset(self, ctx):
        """Remove your timezone from the database."""
        async with self.bot.db.execute("DELETE FROM Timezones WHERE user_id = ? RETURNING 1", (ctx.author.id,)) as cur:
            if not (await cur.fetchone()):
                return await show_error(ctx, "You don't have a timezone set.")
        await self.bot.db.commit()
        await self.update_times()

        await ctx.send(
            embed=discord.Embed(
                title="Unset timezone",
                description="Your timezone is now unset.",
                color=colors.EMBED_SUCCESS,
            )
        )

    async def update_times(self):
        channel = self.bot.get_channel(channels.TIME_CHANNEL)
        paginator = EmbedPaginator()
        time_config_members = {}
        async with self.bot.db.execute("SELECT * FROM Timezones") as cur:
            async for user_id, timezone in cur:
                m = channel.guild.get_member(user_id)
                if m:
                    time_config_members[m] = timezone
        now = datetime.datetime.now()
        groups = itertools.groupby(
            sorted(
                time_config_members.items(),
                key=lambda m: (
                    n := now.astimezone(pytz.timezone(m[1])).replace(tzinfo=None)
                ) and (n, str(m[0])),
            ),
            lambda x: Time.get_time(x[1]),
        )
        for key, group in groups:
            if not key:
                continue
            group_message = [key]
            for member, _ in group:
                group_message.append(member.mention)
            paginator.add_line("\n￭ ".join(group_message))

        paginator.embeds[0].title = "Times"
        paginator.embeds[-1].set_footer(text="The timezones and current times for every user on the server who has opted in, in order of UTC offset.")
        to_send = paginator.embeds

        own_messages = [x async for x in channel.history(oldest_first=True)]
        if len(own_messages) > len(to_send):
            await channel.purge(limit=len(own_messages) - len(to_send))
        if len(to_send) > len(own_messages) and (on_messages[-1].created_at - datetime.datetime.utcnow()).total_seconds() > 7 * 60:
            # there's going to be a break in the messages so we have to delete the old ones
            await channel.purge(limit=len(own_messages))
            own_messages.clear()

        for i, e in enumerate(to_send):
            try:
                await own_messages[i].edit(embed=e)
            except IndexError:
                await channel.send(embed=e)

    @tasks.loop(minutes=1)
    async def time_loop(self):
        await self.update_times()
    time_loop.add_exception_type(discord.HTTPException)

    @time_loop.before_loop
    async def before_time(self):
        await self.bot.wait_until_ready()
        now = datetime.datetime.utcnow()
        await asyncio.sleep(60 - (now.second + now.microsecond/1_000_000))


async def setup(bot):
    await bot.add_cog(Time(bot))
