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
            return openai, "gpt-4.1"
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


def aggressive_normalize(s, extra=""):
    return "".join([x for x in unidecode(s.casefold()) if x in string.ascii_letters + string.digits + extra + "_"])

def rank_enumerate(xs, *, key, reverse=True):
    cur_idx = None
    cur_key = None
    for idx, x in enumerate(sorted(xs, key=key, reverse=reverse), start=1):
        if cur_key is None or key(x) != cur_key:
            cur_idx = idx
            cur_key = key(x)
        yield (cur_idx, x)

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

class HandledConversionFailure(commands.UserInputError):
    pass
