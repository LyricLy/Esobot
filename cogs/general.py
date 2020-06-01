import asyncio
import discord
import random
import time
import datetime
import subprocess

from discord.ext import commands
from utils import l, make_embed
from constants import colors, info, emoji
from typing import Optional


def get_command_signature(command):
    # almost entirely copied from within discord.ext.commands, but ignores aliases
    result = command.qualified_name
    if command.usage:
        result += " " + command.usage
    elif command.clean_params:
        # l.warning(f"Command {command.name} has parameters but no 'usage'.")
        result = command.qualified_name
        params = command.clean_params
        if params:
            for name, param in command.clean_params.items():
                if param.default is not param.empty:
                    if param.default not in (None, ""):
                        result += f" [{name}={param.default}]"
                    else:
                        result += f" [{name}]"
                elif param.kind == param.VAR_POSITIONAL:
                    result += f" [{name}\N{HORIZONTAL ELLIPSIS}]"
                else:
                    result += f" <{name}>"
    return result


async def get_message_guild(guild, id, priority_channel=None):
    channels = guild.text_channels
    if priority_channel:
        channels.remove(priority_channel)
        try:
            return await priority_channel.fetch_message(id)
        except discord.NotFound:
            pass
    for channel in channels:
        try:
            return await channel.fetch_message(id)
        except discord.NotFound:
            pass


class General(commands.Cog):
    """General-purpose commands."""

    def __init__(self, bot):
        self.bot = bot
        bot.original_help = bot.get_command("help")
        bot.remove_command("help")
        self.words = None

    def cog_unload(self):
        self.bot.add_command(self.bot.original_help)

    @commands.command(aliases=["h", "man"])
    async def help(self, ctx, *, command_name: str = None):
        """Display a list of all commands or display information about a specific command."""
        prefixes = await self.bot.get_prefix(ctx.message)
        if command_name:
            command = self.bot.get_command(command_name)
            if command is None:
                await ctx.send(
                    embed=make_embed(
                        color=colors.EMBED_ERROR,
                        title="Command help",
                        description=f"Could not find command `{command_name}`.",
                    )
                )
            elif await command.can_run(ctx):
                fields = []
                if command.usage or command.clean_params:
                    fields.append(
                        ("Synopsis", f"`{get_command_signature(command)}`", True)
                    )
                if command.aliases:
                    aliases = ", ".join(f"`{alias}`" for alias in command.aliases)
                    fields.append(("Aliases", aliases, True))
                if command.help:
                    fields.append(("Description", command.help))
                if hasattr(command, "commands"):
                    subcommands = [
                        f"`{get_command_signature(x)}`" + f" \N{EM DASH} {x.short_doc}"
                        if x.short_doc
                        else ""
                        for x in command.commands
                    ]
                    fields.append(("Subcommands", "\n".join(subcommands)))
                misc = ""
                if not command.enabled:
                    misc += "This command is currently disabled.\n"
                if command.hidden:
                    misc += "This command is usually hidden.\n"
                if misc:
                    fields.append(("Miscellaneous", misc))
                await ctx.send(
                    embed=make_embed(
                        color=colors.EMBED_HELP,
                        title="Command help",
                        description=f"`{command.name}`",
                        fields=fields,
                    )
                )
            else:
                await ctx.send(
                    embed=make_embed(
                        color=colors.EMBED_ERROR,
                        title="Command help",
                        description=f"You have insufficient permission to access `{command_name}`.",
                    )
                )
        else:
            cog_names = []
            ungrouped_commands = []
            for command in self.bot.commands:
                if command.cog_name and command.cog_name not in cog_names:
                    cog_names.append(command.cog_name)
            fields = []
            for cog_name in sorted(cog_names):
                lines = []
                for command in sorted(
                    self.bot.get_cog(cog_name).get_commands(), key=lambda cmd: cmd.name
                ):
                    if not command.hidden and (await command.can_run(ctx)):
                        line = f"\N{BULLET} **`{get_command_signature(command)}`**"
                        if command.short_doc:
                            line += f" \N{EM DASH} {command.short_doc}"
                        lines.append(line)
                if lines:
                    fields.append((cog_name, "\n".join(lines)))
            await ctx.send(
                embed=make_embed(
                    color=colors.EMBED_HELP,
                    title="Command list",
                    description=f"Invoke a command by prefixing it with {','.join(prefixes[:-1])} or {prefixes[-1]}. Use `{ctx.command.name} [command]` to get help on a specific command.",
                    fields=fields,
                )
            )

    @commands.command(aliases=["i", "info"])
    async def about(self, ctx):
        """Information about the bot."""
        await ctx.send(
            embed=make_embed(
                title=f"About {info.NAME}",
                description=info.ABOUT_TEXT,
                fields=[
                    ("Author", f"[{info.AUTHOR}]({info.AUTHOR_LINK})", True),
                    ("GitHub Repository", info.GITHUB_LINK, True),
                ],
                footer_text=f"{info.NAME} v{info.VERSION}",
            )
        )

    @commands.command()
    @commands.guild_only()
    async def quote(self, ctx, message_id: int = None):
        """Quote a previous message."""
        if not message_id:
            quote_message = await ctx.send(
                embed=make_embed(
                    title="No message",
                    description=f"React to a message with {emoji.QUOTE}.",
                )
            )

            try:
                payload = await self.bot.wait_for(
                    "raw_reaction_add",
                    check=lambda m: m.guild_id == ctx.guild.id and m.emoji.name == emoji.QUOTE and m.user_id == ctx.author.id,
                    timeout=60,
                )
            except asyncio.TimeoutError:
                await quote_message.edit(
                    embed=make_embed(
                        title="No message", description=f"No reaction given."
                    )
                )
                return

            channel = ctx.guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
        else:
            message = await get_message_guild(ctx.guild, message_id, ctx.channel)
            if not message:
                await ctx.send(
                    embed=make_embed(
                        title="No message", description="Bad message ID given."
                    )
                )
                return
            quote_message = ctx.channel
        embed = make_embed(
            description=message.content,
            timestamp=message.edited_at or message.created_at,
            footer_text="#" + message.channel.name,
        )
        embed.set_author(name=message.author.name, icon_url=message.author.avatar_url)
        if message.attachments:
            filename = message.attachments[0].filename
            if (
                filename.endswith(".png")
                or filename.endswith(".jpg")
                or filename.endswith(".jpeg")
            ):
                embed.set_image(url=message.attachments[0].url)

        if hasattr(quote_message, "send"):
            await quote_message.send(embed=embed)
        else:
            await quote_message.edit(embed=embed)

    @commands.command(aliases=["tr", "type", "race"])
    @commands.guild_only()
    async def typerace(self, ctx, words: int = 15):
        if not 1 <= words <= 50:
            return await ctx.send("Use between 1 and 50 words.")
        if not self.words:
            async with self.bot.session.get("https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt") as resp:
                self.words = (await resp.text()).splitlines()
        await ctx.send("Type race begins in 10 seconds. Get ready!")
        await asyncio.sleep(10)
        prompt = " ".join(random.choices(self.words, k=words))
        zwsp = "\u200b"
        start = await ctx.send(zwsp.join(list(prompt.translate(str.maketrans({
            "a": "а",
            "c": "с",
            "e": "е",
            "s": "ѕ",
            "i": "і",
            "j": "ј",
            "o": "о",
            "p": "р",
            "y": "у",
            "x": "х"
        })))))
        winners = {}
        running = [True]
        timeout = False
        while running[0]:
            msg = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.content == prompt and not m.author.bot and m.author not in winners)
            await msg.delete()
            winners[msg.author] = (msg.created_at - start.created_at).total_seconds()
            if not timeout:
                timeout = True
                async def ender():
                    await asyncio.sleep(10)
                    running[0] = False
                await ctx.send(f"{msg.author.name.replace('@', '@' + zwsp)} wins. Other participants have 10 seconds to finish.")
                await self.bot.loop.create_task(ender())
        await ctx.send("\n".join(f"{i + 1}. {u.name.replace('@', '@' + zwsp)} - {t:.4f} seconds ({len(prompt) / t * 12:.2f}WPM)" for i, (u, t) in enumerate(winners.items())))

def setup(bot):
    bot.add_cog(General(bot))
