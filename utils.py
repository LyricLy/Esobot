import asyncio
import discord
import json
import logging
import traceback

from constants import colors, emoji, paths

l = logging.getLogger("bot")


def clean(text):
    """Clean a string for use in a multi-line code block."""
    return text.replace("```", "`\u200b``")


class EmbedPaginator:
    def __init__(self):
        self.current_page = []
        self.count = 0
        self._embeds = []
        self.current_embed = discord.Embed()

    @property
    def _max_size(self):
        if not self.current_embed.description:
            return 2048
        return 1024

    def close_page(self):
        if len(self.current_embed) + self.count > 6000 or len(self.current_embed.fields) == 25:
            self.close_embed()

        if not self.current_embed.description:
            self.current_embed.description = "\n".join(self.current_page)
        else:
            self.current_embed.add_field(name="\u200b", value="\n".join(self.current_page))

        self.current_page.clear()
        self.count = 0

    def close_embed(self):
        self._embeds.append(self.current_embed)
        self.current_embed = discord.Embed()

    def add_line(self, line):
        if len(line) > self._max_size:
            raise RuntimeError(f"Line exceeds maximum page size {self._max_size}")

        if self.count + len(line) + 1 > self._max_size:
            self.close_page()
        self.count += len(line) + 1
        self.current_page.append(line)

    @property
    def embeds(self):
        if self.current_page:
            self.close_page()
        if self.current_embed.description:
            self.close_embed()
        return self._embeds


def make_embed(*, fields=[], footer_text=None, **kwargs):
    embed = discord.Embed(**kwargs)
    for field in fields:
        if len(field) > 2:
            embed.add_field(name=field[0], value=field[1], inline=field[2])
        else:
            embed.add_field(name=field[0], value=field[1], inline=False)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed


async def react_yes_no(ctx, m, timeout=30):
    # TODO Allow user to type '!confirm'/'!y' or '!cancel'/'!n' in addition to reactions
    await m.add_reaction(emoji.CONFIRM)
    await m.add_reaction(emoji.CANCEL)
    try:
        reaction, _ = await ctx.bot.wait_for(
            "reaction_add",
            check=lambda reaction, user: (
                reaction.emoji in (emoji.CONFIRM, emoji.CANCEL)
                and reaction.message.id
                == m.id  # not sure why I need to compare the IDs
                and user == ctx.message.author
            ),
            timeout=timeout,
        )
        result = "ny"[reaction.emoji == emoji.CONFIRM]
    except asyncio.TimeoutError:
        result = "t"
    await m.remove_reaction(emoji.CONFIRM, ctx.me)
    await m.remove_reaction(emoji.CANCEL, ctx.me)
    return result


async def report_error(ctx, exc, *args, bot=None, **kwargs):
    if ctx:
        if isinstance(ctx.channel, discord.DMChannel):
            guild_name = "N/A"
            channel_name = "DM"
        elif isinstance(ctx.channel, discord.GroupChannel):
            guild_name = "N/A"
            channel_name = f"Group with {len(ctx.channel.recipients)} members (id={ctx.channel.id})"
        else:
            guild_name = ctx.guild.name
            channel_name = f"#{ctx.channel.name}"
        user = ctx.author
        fields = [
            ("Guild", guild_name, True),
            ("Channel", channel_name, True),
            ("User", f"{user.name}#{user.discriminator} (A.K.A. {user.display_name})"),
            ("Message Content", f"{ctx.message.content}"),
        ]
    else:
        fields = []
    tb = clean("".join(traceback.format_tb(exc.__traceback__, limit=5)))
    fields += [
        ("Args", f"```\n{repr(args)}\n```" if args else "None", True),
        ("Keyword Args", f"```\n{repr(kwargs)}\n```" if kwargs else "None", True),
        ("Traceback", f"```\n{tb}\n```"),
    ]
    if not bot:
        bot = ctx.bot
    if not bot.get_user(bot.owner_id):
        return

    await bot.get_user(bot.owner_id).send(
        embed=make_embed(
            color=colors.EMBED_ERROR,
            title="Error",
            description=f"`{str(exc)}`",
            fields=fields,
        )
    )


class ShowErrorException(Exception):
    pass


async def show_error(ctx, message, title="Error"):
    await ctx.send(
        embed=make_embed(title=title, description=message, color=colors.EMBED_ERROR)
    )
    raise ShowErrorException()


def load_json(name):
    with open(paths.CONFIG_FOLDER + "/" + name) as f:
        return json.load(f)


def save_json(name, data):
    with open(paths.CONFIG_FOLDER + "/" + name, "w+") as f:
        json.dump(data, f)
