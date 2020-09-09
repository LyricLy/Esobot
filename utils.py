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
