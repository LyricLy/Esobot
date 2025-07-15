from discord.ext import commands

from . import QwdBase


class Qwd(QwdBase, name="QWD"):
    """General QWD-specific functionality."""

    @commands.Cog.listener("on_message")
    async def mjau(self, message):
        if message.guild == self.qwd and message.content.startswith("!mja"):
            word1, word2 = message.content.split(" ", 1)
            try:
                n = int(word2.strip())
            except ValueError:
                return
            s = "mja" + word1.removeprefix("!mja") * n
            if len(s) >= 2000:
                return
            await message.channel.send(s)


async def setup(bot):
    await bot.add_cog(Qwd(bot))
