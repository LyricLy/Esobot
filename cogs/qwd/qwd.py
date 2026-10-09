import asyncio
import functools
from collections import defaultdict

import discord
from discord.ext import commands

from . import QwdBase, chitterclass, only
from utils import l, aggressive_normalize, pronoun_sets, third_person_pronoun_sets, HandledConversionFailure


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
        await self.message.edit(content="Hello?", view=self)

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
        if ctx.guild == self.qwd:
            table = Aliases.table
        elif ctx.guild.id == 1414789939773833238:
            table = defaultdict(list, {
                "xyz": [ctx.guild.get_member(5908674421653504)],
                "alex": [ctx.guild.get_member(712918252799524945), ctx.guild.get_member(236831708354314240)],
                "femgirl": [ctx.guild.get_member(712918252799524945)],
                "femgal": [ctx.guild.get_member(712918252799524945)],
                "tomboy": [ctx.guild.get_member(712918252799524945)],
                "femgallium": [ctx.guild.get_member(712918252799524945)],
                "bean": [ctx.guild.get_member(1150987229762686986)],
                "beany": [ctx.guild.get_member(1150987229762686986)],
                "ben": [ctx.guild.get_member(806339848368685076)],
                "crox": [ctx.guild.get_member(719895026078842902)],
                "cyan": [ctx.guild.get_member(699039991208345751)],
                "danman": [ctx.guild.get_member(765591187213385739)],
                "infy": [ctx.guild.get_member(1006535466138480681)],
                "iphony": [ctx.guild.get_member(193708921985302528)],
                "kai": [ctx.guild.get_member(1016343277814956154)],
                "koko": [ctx.guild.get_member(697876621373210664)],
                "lyric": [ctx.guild.get_member(319753218592866315)],
                "maverick": [ctx.guild.get_member(908846708715302983)],
                "mavie": [ctx.guild.get_member(908846708715302983)],
                "nath": [ctx.guild.get_member(539942597486051329)],
                "night": [ctx.guild.get_member(693443838370381874)],
                "olus": [ctx.guild.get_member(339009650592710656)],
                "pineclones": [ctx.guild.get_member(830399029161885757)],
                "sammy": [ctx.guild.get_member(1129179243620872265)],
                "sprite": [ctx.guild.get_member(1345139493321310249)],
                "sue": [ctx.guild.get_member(754541960181841962)],
                "suethegov": [ctx.guild.get_member(754541960181841962)],
                "temp": [ctx.guild.get_member(703645091901866044)],
                "umni": [ctx.guild.get_member(236831708354314240)],
                "ungealz": [ctx.guild.get_member(856312866436022272)],
                "whis": [ctx.guild.get_member(723464246935027733)],
                "whys": [ctx.guild.get_member(723464246935027733)],
                "wickedmoon": [ctx.guild.get_member(834527934572265493)],
                "wickedmoon42": [ctx.guild.get_member(834527934572265493)],
                "zz": [ctx.guild.get_member(267341224409563147)],
            })
        else:
            return await self.old_convert(converter, ctx, argument)

        choices = set()

        thought = argument.removeprefix("<@").removeprefix("!").removesuffix(">")
        if thought.isdigit() and (user := ctx.guild.get_member(int(thought))):
            choices.add(user)

        # ignore any attempt at a discrim
        arg = argument.casefold().split("#", 1)[0]

        choices.update([
       # band for band
            m for m in ctx.guild.members if arg in (m.name.casefold(), m.global_name and m.global_name.casefold(), m.display_name.casefold())
        ])

        choices.update([x for x in table[arg] if isinstance(x, discord.Member)])

        if arg.rstrip("e") == "m" and len(arg) >= 2:
            choices.add(ctx.author)
        elif arg.rstrip("u") == "yo" and len(arg) >= 3:
            # do not consider any other bot calling itself "you"
            choices = {choice for choice in choices if not choice.bot}
            choices.add(ctx.me)
        elif p := discord.utils.get(pronoun_sets.values(), obj=arg):
            async for msg in ctx.history(limit=15):
                if msg.author not in (ctx.author, ctx.me) and p in third_person_pronoun_sets(msg.author):
                    choices.add(msg.author)

        if not choices:
            raise commands.MemberNotFound(argument)
        if len(choices) == 1:
            return choices.pop()

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
        if not view.chosen:
            raise HandledConversionFailure()

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
