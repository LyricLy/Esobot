import datetime
import asyncio

import discord
from discord.ext import commands
from typing import Optional

from . import QwdBase
from utils import preferred_model, message_to_openai, urls_of_message


REACT_PROMPTS = {
    "🪞": """
Your job is to "reflect" the meaning of a sentence, usually by replacing either its subject or its object with the word "YOU".
Assume the replacement sentence is being spoken by a different person than the original sentence, to the person who said the original sentence
(for example, if person A said the original sentence, person B is saying the replacement sentence to person A).
For this reason, it is usually incorrect to replace "I" with "YOU", as it would make the sentence equivalent to the original.
You should place the word to fit with the theme of "reversing" the sentence onto the person speaking. Do not say anything other than the result of the translation.
If you could change either the subject or the object, change the subject.

Here are some examples:
Ice cream is good -> YOU are good
I like ice cream -> I like YOU
oxford is fucking stupid -> YOU are fucking stupid
I am fucking stupid -> I am fucking YOU
idk why i didnt start using it earlier -> idk why i didnt start using YOU earlier
I love you -> I love YOU
nice -> YOU're nice
""",
    "🥄": """
Your job is to "reflect" the meaning of a sentence, usually by replacing either its subject or its object with the word "YOU", while also inverting its meaning.
Assume the replacement sentence is being spoken by a different person than the original sentence, to the person who said the original sentence
(for example, if person A said the original sentence, person B is saying the replacement sentence to person A).
For this reason, it is usually incorrect to replace "I" with "YOU", as it would make the sentence equivalent to the original.
You should place the word to fit with the theme of "reversing" the sentence onto the person speaking, then invert the meaning of the resulting sentence.
Do not say anything other than the result of the translation.
If you could change either the subject or the object, change the subject.

Here are some examples:
Ice cream is good -> YOU are not good
I like ice cream -> I do not like YOU
oxford is fucking stupid -> YOU are not fucking stupid
I am fucking stupid -> I am not fucking YOU
idk why i didnt start using it earlier -> I know why i didnt start using YOU earlier
I love you -> I don't love YOU
nice -> YOU aren't nice
""",
    "🪟": """
Your job is to "redirect" the meaning of a sentence onto the person talking, usually by replacing either its subject with "**I**" or its object with "ME".
Assume the replacement sentence is being spoken by a different person than the original sentence, to the person who said the original sentence
(for example, if person A said the original sentence, person B is saying the replacement sentence to person A).
For this reason, it is usually incorrect to replace "you" with "**I**", as it would make the sentence equivalent to the original.
You should place the word to fit with the theme of "redirecting" the sentence onto a different person. Do not say anything other than the result of the translation.
If you could change either the subject or the object, change the subject.

Here are some examples:
Ice cream is good -> **I** am good
I like ice cream -> **I** like ice cream
oxford is fucking stupid -> **I** am fucking stupid
I am fucking stupid -> **I** am fucking stupid
idk why oxford didnt start using it earlier -> idk why oxford didnt start using ME earlier
I love you -> **I** love you
nice -> **I**'m nice
""",
    "🔎": (_ := """
Your job is to "redirect" the meaning of a sentence onto the person talking, usually by replacing either its subject with "**I**" or its object with "ME", while also inverting its meaning.
Assume the replacement sentence is being spoken by a different person than the original sentence, to the person who said the original sentence
(for example, if person A said the original sentence, person B is saying the replacement sentence to person A).
For this reason, it is usually incorrect to replace "you" with "**I**", as it would make the sentence equivalent to the original.
You should place the word to fit with the theme of "redirecting" the sentence onto a different person, then invert the meaning of the resulting sentence.
Do not say anything other than the result of the translation.
If you could change either the subject or the object, change the subject.

Here are some examples:
Ice cream is good -> **I** am not good
I like ice cream -> **I** do not like ice cream
oxford is fucking stupid -> **I** am not fucking stupid
I am fucking stupid -> **I** am not fucking stupid
idk why oxford didnt start using it earlier -> I know why oxford didnt start using ME earlier
I love you -> **I** don't love you
nice -> **I**'m not nice
"""),
    "🔍": _,
    "\N{MIRROR BALL}": """
Your job is to "expand" the meaning of a sentence, usually by replacing either its subject or its object with the word "EVERYQWDIE".
Assume the replacement sentence is being spoken by a different person than the original sentence, to the person who said the original sentence
(for example, if person A said the original sentence, person B is saying the replacement sentence to person A).
You should place the word to fit with the theme of "expanding" the sentence to apply to every person. Do not say anything other than the result of the translation.
If you could change either the subject or the object, change the subject.

Here are some examples:
Ice cream is good -> EVERYQWDIE is good
I like ice cream -> I like EVERYQWDIE
oxford is fucking stupid -> EVERYQWDIE is fucking stupid
I am fucking stupid -> I am fucking EVERYQWDIE
idk why i didnt start using it earlier -> idk why EVERYQWDIE didnt start using it earlier
I love you -> EVERYQWDIE loves you
nice -> EVERYQWDIE is nice
""",
    "🆔": """
Your job is to "reify" the meaning of a sentence by changing its tense to indicate that something hypothesized or wished for is already the case.
If the input sentence does not indicate anything irreal, respond "DOMAIN ERROR".
Do not say anything other than the result of the translation.

Here are some examples:
I wish I could be prettier -> you already are pretty
if I was the cutest person in the world -> you are the cutest person in the world
I feel beautiful right now -> you are beautiful right now
can someone make me hot? -> you are hot
if only I was gay -> you are gay
I will never be a woman -> you are a woman
I love to spoon people -> DOMAIN ERROR
I am poor -> DOMAIN ERROR
I fucked up -> DOMAIN ERROR
I am going to be homeless tomorrow -> you are homeless
""",
}


class QwdInterp(QwdBase, name="Interpretation (QWD)"):
    """Interpreting content for the benefit of all QWD!"""

    @commands.Cog.listener("on_message")
    async def cc_watchfox(self, message):
        if message.guild != self.qwd:
            return
        if not any(attachment.content_type.startswith(("audio", "video")) for attachment in message.attachments):
            await asyncio.sleep(1)
            try:
                await message.channel.fetch_message(message.id)
            except discord.NotFound:
                return
            if not any(embed.video.url and embed.type != "gifv" for embed in message.embeds):
                return
        await self.bot.db.execute("INSERT INTO CCReacts (message_id) VALUES (?)", (message.id,))
        await self.bot.db.commit()
        await message.add_reaction("<:missing_captions:1358721100695076944>")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.id != 1358721100695076944 or payload.guild_id != self.qwd.id or payload.member == self.bot.user:
            return
        part_msg = self.bot.get_partial_messageable(payload.channel_id).get_partial_message(payload.message_id)
        await part_msg.remove_reaction(payload.emoji, self.bot.user)
        await part_msg.remove_reaction(payload.emoji, payload.member)
        await self.bot.db.execute(
            "UPDATE CCReacts SET cleared_by = COALESCE(cleared_by, ?), cleared_at = COALESCE(cleared_at, ?) WHERE message_id = ?",
            (payload.member.id, datetime.datetime.now(datetime.timezone.utc), part_msg.id),
        )
        await self.bot.db.commit()

    @commands.command()
    async def watchfox(self, ctx, *, message: discord.Message = None):
        """Ask Cici about a particular message."""
        message = message or (r := ctx.message.reference) and r.resolved
        if not message:
            return await ctx.send("Please reply to a message or provide a message ID.")
        async with self.bot.db.execute("SELECT cleared_by, cleared_at FROM CCReacts WHERE message_id = ?", (message.id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return await ctx.send("I never reacted with <:missing_captions:1358721100695076944> to that message.")
        cleared_by, cleared_at = row
        if not cleared_by:
            return await ctx.send("My reaction is still there, silly!")
        await ctx.send(
            f"I reacted with <:missing_captions:1358721100695076944> to that message, and <@{cleared_by}> cleared it at {discord.utils.format_dt(cleared_at)}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command()
    async def unreact(self, ctx, msg: Optional[discord.Message] = None, react=None, *, text=""):
        """Interpret the reactions on a message."""
        if react and react not in REACT_PROMPTS:
            return await ctx.send(f"I don't know the '{react}' react.")
        if not msg and ctx.message.reference:
            try:
                msg = ctx.message.reference.cached_message or await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except discord.NotFound:
                msg = None
        if not msg and not text:
            async for msg in ctx.history(limit=25):
                if any(react.emoji in REACT_PROMPTS for react in msg.reactions):
                    break
            else:
                return await ctx.send("Not sure what message you're referring to...")

        reacts = [react] if react else [react.emoji for react in msg.reactions if react.emoji in REACT_PROMPTS]
        if not reacts:
            return await ctx.send("That message doesn't have any reactions I know on it.")

        results = []
        for r in reacts:
            prompt = REACT_PROMPTS[r].strip("\n")
            lib, model = await preferred_model(ctx)
            completion = await lib.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    message_to_openai(msg.content if msg else text, urls_of_message(msg if msg else ctx.message)),
                ],
                max_completion_tokens=512,
            )
            results.append((r, completion.choices[0].message.content))

        if len(results) == 1:
            await ctx.reply(results[0][1])
        else:
            await ctx.reply("\n".join(f"- {r}: {t}" for r, t in results))


async def setup(bot):
    await bot.add_cog(QwdInterp(bot))
