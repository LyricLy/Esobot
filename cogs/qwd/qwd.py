import asyncio
import functools
from collections import defaultdict

import discord
from discord.ext import commands

from . import QwdBase, chitterclass, only
from utils import l, aggressive_normalize, pronoun_sets, third_person_pronoun_sets


async def circularize(img_data):
    proc = await asyncio.create_subprocess_shell(
        r"magick - -write mpr:img null: \( mpr:img -alpha extract -coalesce null: assets/circle.png -compose multiply -layers composite \) -compose copy_alpha -layers composite -",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate(img_data)
    return stdout


class MemberChooser(discord.ui.View):
    def __init__(self, bot, owner):
        super().__init__()
        self.bot = bot
        self.owner = owner
        self.chosen = None

    async def avatar_emoji(self, member):
        emoji_name = aggressive_normalize(member.name)
    
        async with self.bot.db.execute("SELECT hash, id, animated FROM AvatarEmoji WHERE user_id = ?", (member.id,)) as cur:
            cached = await cur.fetchone()

        if cached and cached["hash"] == member.avatar.key:
            # hit
            _, emoji_id, animated = cached
            yield discord.PartialEmoji.from_str("a:"*animated + f"{emoji_name}:{emoji_id}")
            return

        # miss
        yield discord.PartialEmoji.from_str("<a:loading:1395166109673455688>")

        asset = member.avatar.with_format("webp").with_size(128)
        # Danny what the fuck
        asset._url += "&animated=true"*asset.is_animated()
        cropped = await circularize(await asset.read())

        if cached:
            # dpy makes us fetch first
            old = await self.bot.fetch_application_emoji(cached["id"])
            await old.delete()
        emoji = await self.bot.create_application_emoji(name=emoji_name, image=cropped)

        await self.bot.db.execute("INSERT OR REPLACE INTO AvatarEmoji (user_id, hash, id, animated) VALUES (?, ?, ?, ?)", (member.id, member.avatar.key, emoji.id, emoji.animated))
        await self.bot.db.commit()

        yield emoji

    async def fill(self, members):
        remaining_emoji = []
        for member in members:
            emoji = self.avatar_emoji(member)
            button = discord.ui.Button(
                label=member.name,
                emoji=await anext(emoji),
            )
            button.callback = functools.partial(self.select, member, button)
            remaining_emoji.append((emoji, button))
            self.add_item(button)
        asyncio.create_task(self.complete_emoji(remaining_emoji))

    async def complete_one_emoji(self, iterator, button):
        try:
            emoji = await anext(iterator)
        except StopAsyncIteration:
            return
        except Exception:
            return l.exception("error making avatar emoji")
        button.emoji = emoji

    async def complete_emoji(self, remaining):
        async with asyncio.TaskGroup() as tg:
            for pair in remaining:
                tg.create_task(self.complete_one_emoji(*pair))
        if not self.is_finished() and hasattr(self, "message"):
            await self.message.edit(view=self)

    async def select(self, member, button, interaction):
        button.style = discord.ButtonStyle.blurple
        self.chosen = member
        self.resolve()
        await interaction.response.edit_message(content="I see." + " I'll remember that."*self.will_remember, view=self)

    @discord.ui.button(label="Remember my choice", row=4)
    async def remember(self, interaction, button):
        button.style = discord.ButtonStyle(button.style.value ^ 3)
        await interaction.response.edit_message(view=self)

    @property
    def will_remember(self):
        return self.remember.style == discord.ButtonStyle.blurple

    def resolve(self):
        self.remove_item(self.remember)
        for item in self.children:
            item.disabled = True
        self.stop()

    async def on_timeout(self):
        self.resolve()
        await self.message.edit(content="Timed out.", view=self)

    async def interaction_check(self, interaction):
        if interaction.user != self.owner:
            await interaction.response.send_message("I wasn't asking you.", ephemeral=True)
            return False
        return True


@chitterclass(1394575943049281626, listen_to=only(750944057794101298))
class Aliases:
    user: discord.Member
    alias: str

    table = defaultdict(list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_seen(self):
        self.table[self.alias.casefold()].append(self.user)

    def on_delete(self):
        self.table[self.alias.casefold()].remove(self.user)


class Qwd(QwdBase, name="QWD"):
    """General QWD-specific functionality."""

    async def cog_load(self):
        await super().cog_load()
        await Aliases.sync(self.bot)
        self.old_convert = commands.MemberConverter.convert
        commands.MemberConverter.convert = lambda *args, **kwargs: self.convert(*args, **kwargs)

    def cog_unload(self):
        commands.MemberConverter.convert = self.old_convert

    async def convert(self, converter, ctx, argument):
        if ctx.guild != self.qwd:
            return await self.old_convert(converter, ctx, argument)

        choices = []

        thought = argument.removeprefix("<@").removeprefix("!").removesuffix(">")
        if thought.isdigit() and (user := self.qwd.get_member(int(thought))):
            choices.append(user)

        # ignore any attempt at a discrim
        arg = argument.casefold().split("#", 1)[0]

        choices.extend([
       # band for band
            m for m in self.qwd.members if arg in (m.name.casefold(), m.global_name and m.global_name.casefold(), m.display_name.casefold())
        ])

        choices.extend(Aliases.table[arg])

        if arg.rstrip("e") == "m" and len(arg) >= 2:
            choices.append(ctx.author)
        elif arg.rstrip("u") == "yo" and len(arg) >= 3:
            choices.append(ctx.me)
        elif p := discord.utils.get(pronoun_sets.values(), obj=arg):
            async for msg in ctx.history(limit=15):
                if msg.author not in (ctx.author, ctx.me) and p in third_person_pronoun_sets(msg.author):
                    choices.append(msg.author)

        if not choices:
            raise commands.MemberNotFound(argument)
        if len(choices) == 1:
            return choices[0]

        # can we find a choice in memory that beats all the others?
        for choice in choices:
            async with self.bot.db.execute("SELECT loser FROM SolvedAmbiguities WHERE user_id = ? AND alias = ? AND winner = ?", (ctx.author.id, arg, choice.id)) as cur:
                beats_rows = await cur.fetchall()
            beats = set(beaten for beaten, in beats_rows)
            beats.add(choice.id)
            if all(challenger.id in beats for challenger in choices):
                return choice

        # if not, we have to ask
        view = MemberChooser(self.bot, ctx.author)
        await view.fill(choices)
        view.message = await ctx.send("Yes. But which one?", view=view)
        await view.wait()

        if view.will_remember:
            for choice in choices:
                if choice != view.chosen:
                    await self.bot.db.execute("DELETE FROM SolvedAmbiguities WHERE user_id = ? AND alias = ? AND winner = ? AND loser = ?", (ctx.author.id, arg, choice.id, view.chosen.id))
                    await self.bot.db.execute("INSERT OR IGNORE INTO SolvedAmbiguities (user_id, alias, winner, loser) VALUES (?, ?, ?, ?)", (ctx.author.id, arg, view.chosen.id, choice.id))
            await self.bot.db.commit()

        return view.chosen

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
