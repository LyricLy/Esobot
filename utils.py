import asyncio
import re
import os
import json
import random
import string
import logging
import traceback

import discord
from unidecode import unidecode
from discord.ext import commands
from openai import AsyncOpenAI

from constants import colors, emoji


l = logging.getLogger("bot")
openai = AsyncOpenAI()
deepseek = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

async def preferred_model(ctx):
    await ctx.bot.db.execute("INSERT OR IGNORE INTO PreferredModels (user_id) VALUES (?)", (ctx.author.id,))
    async with ctx.bot.db.execute("SELECT model FROM PreferredModels WHERE user_id = ?", (ctx.author.id,)) as cur:
        model, = await cur.fetchone()
    match model:
        case "openai":
            return openai, "gpt-4o"
        case "deepseek":
            return deepseek, "deepseek-chat"


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

def urls_of_message(message):
    attached = [a.url for a in message.attachments if "image" in a.content_type]
    embedded = [e.url for e in message.embeds if e.type == "image"]
    return attached + embedded

def message_to_openai(content, urls):
    images = [{"type": "image_url", "image_url": {"url": url}} for url in urls]
    return {"role": "user", "content": [{"type": "text", "text": content}, *images]}


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

    def __str__(self):
        return f"{self.subj}/{self.obj if self.obj != self.subj else self.pos_det}"


pronoun_sets = {
    "he/him": Pronouns("he", "him", "his", "his", "himself", False),
    "she/her": Pronouns("she", "her", "her", "hers", "herself", False),
    "it/its": Pronouns("it", "it", "its", "its", "itself", False),
    "they/them": Pronouns("they", "them", "their", "theirs", "themselves", True),
    "fae/faer": Pronouns("fae", "faer", "faer", "faers", "faerself", False),
}

def third_person_pronoun_sets(member):
    roles = [role.name for guild in member.mutual_guilds for role in guild.get_member(member.id).roles]
    pronouns = []
    for s, p in pronoun_sets.items():
        if s in roles:
            pronouns.append(p)
    if not pronouns:
        pronouns.append(pronoun_sets["they/them"])
        if "any pronouns" in roles:
            pronouns.append(pronoun_sets["he/him"])
            pronouns.append(pronoun_sets["she/her"])
    return pronouns

def get_pronouns(member, *, you=None):
    if member.id == 435756251205468160:
        return Pronouns("I", "me", "my", "mine", "myself", True)
    elif member == you:
        return Pronouns("you", "you", "your", "yours", "yourself", True)
    return random.choice(third_person_pronoun_sets(member))

commands.Context.get_pronouns = lambda self, arg: get_pronouns(arg, you=self.author)

async def show_error(ctx, message, title="Error"):
    await ctx.send(
        embed=discord.Embed(title=title, description=message, color=colors.EMBED_ERROR)
    )

NICKNAMES = {
    "pyro": 261243340752814085,
    "emma": 354579932837445635,
    "emily": 269509329298653186,
    "gnu": 578808799842926592,
    "olus": 339009650592710656,
    "hb": 331320482047721472,
    "lyric": 319753218592866315,
    "ari": 196391696907501570,
    "liz": 320947758959820801,
    "coltrans": 241757436720054273,
    "sofia": 275982450432147456,
    "beat": 621813788609347628,
    "abby": 1272986424857202856,
    "ry": 361263860730036225,
    "makefile": 390874788006199296,
    "edgex": 257604541300604928,
    "you": 435756251205468160,
    "peach": 666489957992497182,
    "mat": 199151261604380672,
    "iso": 559418497734803470,
    "wren": 160206124635783168,
    "sa": 358359026083430410,
    "lights": 95171735548067840,
    "enna": 323622666412228608,
    "tassie": 322724805201756181,
}

old_convert = commands.MemberConverter.convert
async def new_convert(self, ctx, argument):
    try:
        return await old_convert(self, ctx, argument)
    except commands.MemberNotFound:
        if not ctx.guild or ctx.guild.id != 1133026989637382144:
            raise
        argument = argument.lower()
        if argument == "me":
            return ctx.author
        if p := discord.utils.get(pronoun_sets.values(), obj=argument):
            async for msg in ctx.history(limit=20):
                if msg.author not in (ctx.author, ctx.me) and p in third_person_pronoun_sets(msg.author):
                    return msg.author
            raise commands.BadArgument(f"To which user with pronouns '{p}' are you referring?")
        if (id := NICKNAMES.get(argument)) and (m := ctx.guild.get_member(id)):
            return m
        if m := discord.utils.find(lambda m: argument in (m.name.lower(), m.global_name.lower() if m.global_name else None, m.display_name.lower()), ctx.guild.members):
            return m
        raise
commands.MemberConverter.convert = new_convert
