import asyncio
import discord
import json
import random
import string
import logging
import traceback

from unidecode import unidecode

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
            return 4096
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


class PromptOption(discord.ui.Button):
    async def callback(self, interaction):
        self.view._response = self.label
        self.view.event.set()
        for child in self.view.children:
            child.disabled = True
        await interaction.response.edit_message(view=self.view)

class Prompt(discord.ui.View):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.event = asyncio.Event()
        self._response = None

    async def interaction_check(self, interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your interaction to interact with.")
            return False
        return True

    def add_option(self, label, style):
        self.add_item(PromptOption(label=label, style=style))

    async def response(self):
        await self.event.wait()
        return self._response

def aggressive_normalize(s):
    return "".join([x for x in unidecode(s.casefold()) if x in string.ascii_letters + string.digits])


class Pronouns:
    def __init__(self, subj, obj, pos_det, pos_noun, refl, plural):
        self.subj = subj
        self.obj = obj
        self.pos_det = pos_det
        self.pos_noun = pos_noun
        self.refl = refl
        self.plural = plural

    def Subj(self):
        return self.subj.capitalize()

    def are(self):
        if self.subj == "I":
            return "I'm"
        return self.Subj() + ("'re" if self.plural else "'s")

    def plr(self, a, b):
        return a + b*(not self.plural)

    def plrnt(self, a, b):
        return self.plr(a, b) + "n't"

    def they_do_not(self):
        return f'{self.Subj()} {self.plrnt("do", "es")}'


pronoun_sets = {
    "he/him": Pronouns("he", "him", "his", "his", "himself", False),
    "she/her": Pronouns("she", "her", "her", "hers", "herself", False),
    "it/its": Pronouns("it", "it", "its", "its", "itself", False),
    "they/them": Pronouns("they", "them", "their", "theirs", "themselves", True),
    "fae/faer": Pronouns("fae", "faer", "faer", "faers", "faerself", False),
}

def get_pronouns(member):
    if member.id == 435756251205468160:
        return Pronouns("I", "me", "my", "mine", "myself", True)
    roles = [role.name for guild in member.mutual_guilds if guild.id in (346530916832903169, 800373244162867231, 1047299292492206101) for role in guild.get_member(member.id).roles]
    pronouns = []
    for s, p in pronoun_sets.items():
        if s in roles:
            pronouns.append(p)
    if not pronouns:
        pronouns.append(pronoun_sets["they/them"])
        if "any pronouns" in roles:
            pronouns.append(pronoun_sets["he/him"])
            pronouns.append(pronoun_sets["she/her"])
    return random.choice(pronouns)


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
