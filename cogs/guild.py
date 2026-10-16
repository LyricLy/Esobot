import datetime

from discord.ext import commands, tasks


class Guild(commands.Cog):
    """Management of the server itself."""

    def __init__(self, bot):
        self.bot = bot
        self.moodle_loop.start()

    def cog_unload(self):
        self.moodle_loop.cancel()

    # 5AM UTC
    @tasks.loop(
        time=datetime.time(5),
    )
    async def moodle_loop(self):
        channel = self.bot.get_channel(1414822354101604444)
        await channel.send("<@319753218592866315> <@712918252799524945> do moodles (geniuses)")

    @moodle_loop.before_loop
    async def before_moodle_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Guild(bot))
