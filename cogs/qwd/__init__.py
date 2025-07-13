from discord.ext import commands


class QwdBase(commands.Cog):
    async def cog_load(self):
        await self.bot.wait_until_ready()
        QwdBase.qwd = self.bot.get_guild(1133026989637382144)

    def cog_check(self, ctx):
        return not ctx.guild and QwdBase.qwd.get_member(ctx.author.id) or ctx.guild == self.qwd
