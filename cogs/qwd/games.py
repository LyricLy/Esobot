import math
import re
import datetime
import random
import json
import functools
from collections import Counter

import discord
from discord.ext import commands
from PIL import ImageFont

from . import QwdBase
from utils import EmbedPaginator, rank_enumerate


def is_permutation_of(length, xs):
    return set(range(1, length+1)) == set(xs) and len(xs) == length

def to_numbers(s):
    return [int(x) for x in re.findall(r"\d+", s)]

def merge(xs, ys, key):
    inversions = 0
    i = 0
    j = 0
    r = []
    while i < len(xs) and j < len(ys):
        if key(xs[i]) > key(ys[j]):
            r.append(ys[j])
            inversions += len(xs)-i
            j += 1
        else:
            r.append(xs[i])
            i += 1
    r += xs[i:]
    r += ys[j:]
    return r, inversions

def sort_inversions(xs, key=lambda x: x):
    if len(xs) <= 1:
        return xs, 0
    split = len(xs)//2
    left, left_inv = sort_inversions(xs[:split], key)
    right, right_inv = sort_inversions(xs[split:], key)
    r, inv = merge(left, right, key)
    return r, left_inv + right_inv + inv

def message_embed(message):
    embed = discord.Embed(description=message.content)
    embed.set_footer(text="#" + message.channel.name)
    embed.timestamp = message.edited_at or message.created_at
    embed.set_author(name=message.author.global_name or message.author.name, icon_url=message.author.display_avatar)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.filename.endswith((".png", ".jpg", ".jpeg")):
            embed.set_image(url=attachment.url)
    return embed


GG_SANS = ImageFont.truetype("constants/gg sans Medium.ttf", 16, layout_engine=ImageFont.Layout.RAQM)
SPACES = [(c, GG_SANS.getlength(c)) for c in [" ", " ", " ", " ", " ", " ", " "]]
LTR = "\N{LEFT-TO-RIGHT MARK}"
BUTTON_LENGTH = 80

def get_to_size(s, target, regret):
    diff = (target-GG_SANS.getlength(s)) / 2 + regret
    for space, length in SPACES:
        n, diff = divmod(diff, length)
        n = int(n)

        next_s = f"{space*n}{s}{space*n}"
        if len(next_s)+2 > BUTTON_LENGTH:
            break 
        s = next_s
    return f"{LTR}{s}{LTR}", diff

COLOURS = [("🟨", "Yellow"), ("🟩", "Green"), ("🟦", "Blue"), ("🟪", "Purple")]

class Connections(discord.ui.View):
    def __init__(self, owner, title, author, categories):
        super().__init__(timeout=None)
        self.owner = owner
        self.title = title
        self.author = author
        self.categories = categories
        self.cells = [(i, j) for i in range(len(categories)) for j in range(4)]
        random.shuffle(self.cells)
        self.cell_width = max(GG_SANS.getlength(word) for cat in categories for word in cat["words"])
        self.selected = set()
        self.solves = []
        self.guesses = []
        self.mistakes = 4
        self.core_items = self.children
        self.one_away = False
        self.just_submitted = False

    def render(self):
        self.clear_items()
        for item in self.core_items:
            self.add_item(item)

        can_submit = len(self.selected) == 4
        for i, cell in enumerate(self.cells):
            if not i % 4:
                regret = 0
            selected = cell in self.selected
            label, regret = get_to_size(self.categories[cell[0]]["words"][cell[1]], self.cell_width, regret)
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.blurple if selected else discord.ButtonStyle.grey,
                disabled=can_submit and not selected,
                row=i // 4,
            )
            button.callback = functools.partial(self.hit_button, cell)
            self.add_item(button)

        self.deselect.disabled = not self.selected
        self.submit.disabled = not can_submit or self.just_submitted

        embed = discord.Embed(title=self.title, description=f"**{self.mistakes}** mistakes remaining" + "\n## One away..." * self.one_away)
        if self.author:
            embed.set_author(name=self.author.global_name or self.author.name, icon_url=self.author.display_avatar)
        for idx, solve in enumerate(self.solves):
            if idx == 2:
                embed.add_field(name="\u200b", value="\u200b", inline=False)
            ce, cn = COLOURS[solve]
            category = self.categories[solve]
            embed.add_field(name=f"{ce} {cn}", value=f"{category["desc"]}\n{", ".join(category["words"])}")

        if not self.mistakes or len(self.solves) == 4:
            embed.description = [
                "# Next Time!",
                "# Phew!",
                "# Solid!",
                "# Great!",
                "# Perfect!",
            ][self.mistakes]
            embed.add_field(name="Share", value="\n".join(self.guesses), inline=False)
            self.stop()

        return embed

    async def interaction_check(self, interaction):
        if interaction.user != self.owner:
            await interaction.response.send_message("This widget doesn't belong to you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.blurple, row=4)
    async def shuffle(self, interaction, button):
        random.shuffle(self.cells)
        await self.redraw(interaction)

    @discord.ui.button(label="Deselect All", style=discord.ButtonStyle.blurple, row=4)
    async def deselect(self, interaction, button):
        self.selected.clear()
        await self.redraw(interaction)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green, row=4)
    async def submit(self, interaction, button):
        self.just_submitted = True
        self.guesses.append("".join(COLOURS[sel[0]][0] for sel in sorted(self.selected, key=lambda x: x[::-1])))
        (i, c), = Counter(sel[0] for sel in self.selected).most_common(1)
        self.one_away = c == 3
        self.mistakes -= c != 4
        if c == 4:
            self.selected.clear()
            for j in range(4):
                self.cells.remove((i, j))
            self.solves.append(i)
        await self.redraw(interaction)
        
    async def redraw(self, interaction):
        await interaction.response.edit_message(embed=self.render(), view=self if not self.is_finished() else None)

    async def hit_button(self, id, interaction):
        self.just_submitted = False
        if id in self.selected:
            self.selected.remove(id)
        else:
            self.selected.add(id)
        await self.redraw(interaction)


class QwdGames(QwdBase, name="Games (QWD)"):
    """Games for QWD."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    async def hwdyk(self, ctx):
        """How well do you know your friends?"""

    async def pick_random_message(self):
        base = datetime.datetime(year=2023, month=7, day=25)
        channel = self.qwd.get_channel(1133026989637382149 if random.random() < .909 else 1133027144512049223)

        # this doesn't uniformly pick a random message: it strongly prefers messages sent after longer pauses
        # however this is a trade-off for making it incredibly cheap to grab a message because we don't have to spam history calls or store any data
        t = base + datetime.timedelta(milliseconds=random.randint(0, int((datetime.datetime.utcnow() - base).total_seconds() * 1000)))
        async for message in channel.history(before=t):
            if message.content and message.content.count(" ") > 3 and message.author in message.guild.members:
                break

        return message

    @commands.guild_only()
    @hwdyk.group(aliases=["msg"], invoke_without_command=True)
    async def message(self, ctx):
        """Pick a random message. If you can guess who sent it, you win!"""

        message = await self.pick_random_message()
        real_embed = message_embed(message)
        hidden_embed = real_embed.copy()
        hidden_embed.set_footer(text="#??? • ??/??/????")
        hidden_embed.set_author(name="❓  ???")
        hidden_embed.timestamp = None
        bot_msg = await ctx.reply("Who sent this message?", embed=hidden_embed)

        while True:
            r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author)
            try:
                member = await commands.MemberConverter().convert(ctx, r.content)
            except commands.BadArgument:
                pass
            else:
                break

        # insert into stat db
        await self.bot.db.execute("INSERT INTO HwdykGames (player_id, guessed, actual) VALUES (?, ?, ?)", (ctx.author.id, member.id, message.author.id))
        await self.bot.db.commit()

        # reveal info
        await bot_msg.edit(embed=real_embed)

        if member == message.author:
            await r.reply("You were correct!")
        else:
            await r.reply("Too bad. Good luck with the next time!")

    @commands.guild_only()
    @message.command(aliases=["time"])
    async def when(self, ctx, difficulty: int = 4):
        """Pick some random messages. If you can guess what order they were sent in, you win!""" 

        if not 2 <= difficulty <= 8:
            return await ctx.send("Difficulty must be between 2 and 8.") 

        msgs = []
        for _ in range(difficulty):
            msgs.append(await self.pick_random_message())

        real_embeds = []
        hidden_embeds = []
        for idx, msg in enumerate(msgs, start=1):
            real_embed = message_embed(msg)
            real_embed.set_footer(text=f"Message {idx} • " + real_embed.footer.text)
            hidden_embed = real_embed.copy()
            hidden_embed.set_footer(text=hidden_embed.footer.text + " • ??/??/????")
            hidden_embed.timestamp = None
            real_embeds.append(real_embed)
            hidden_embeds.append(hidden_embed)

        bot_msg = await ctx.reply("In what order were these messages sent?", embeds=hidden_embeds)
        r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author and is_permutation_of(len(msgs), to_numbers(m.content)))
        guess = [msgs[i-1] for i in to_numbers(r.content)]

        real_embeds.sort(key=lambda e: e.timestamp)
        await bot_msg.edit(content="The true order.", embeds=real_embeds)

        _, inversions = sort_inversions(guess, key=lambda m: m.created_at)
        score = 1 - inversions / math.comb(difficulty, 2)
        if difficulty == 2 and not score:
            await r.reply("Aww, too bad. Try again next time!")
        elif difficulty == 2:
            await r.reply("You got it right! Well done!")
        elif score == 0.0:
            await r.reply("Huh. You know you're supposed to put them in *ascending* order, right?")
        elif score == 1.0:
            await r.reply("Perfect! Congratulations!")
        elif inversions == 1:
            await r.reply("Just one swap away from perfect! Good going.")
        elif score > 0.5:
            await r.reply(f"You were {score*100:.0f}% correct. Not bad.")
        else:
            await r.reply(f"You were {score*100:.0f}% correct. Try harder next time.")

    @hwdyk.command()
    async def stats(self, ctx, *, member: discord.Member = None):
        """See how well someone (or everyone) is doing."""

        embed = discord.Embed(title="`hwdyk msg` statistics", colour=discord.Colour(0x6b32a8))

        if not member:
            def key(r):
                return r["correct"] / r["total"]

            def render(rs):
                l = []
                for rank, (id, total, correct) in rs:
                    if rank > 5:
                        break
                    l.append(f"{rank}: <@{id}> - {correct}/{total} ({correct/total*100:.2f}%)")
                return "\n".join(l)

            async with self.bot.db.execute("SELECT player_id, COUNT(*) as total, SUM(actual = guessed) as correct FROM HwdykGames GROUP BY player_id HAVING total >= 35") as cur:
                embed.add_field(name="Best players", value=render(rank_enumerate(await cur.fetchall(), key=key)), inline=False)

            async with self.bot.db.execute("SELECT actual, COUNT(*) as total, SUM(actual = guessed) as correct FROM HwdykGames GROUP BY actual HAVING total >= 20") as cur:
                items = await cur.fetchall()
                embed.add_field(name="Hardest to guess", value=render(rank_enumerate(items, key=key, reverse=False)))
                embed.add_field(name="Easiest to guess", value=render(rank_enumerate(items, key=key, reverse=True)))

        else:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

            async with self.bot.db.execute("SELECT COUNT(*), SUM(actual = guessed) FROM HwdykGames WHERE player_id = ?", (member.id,)) as cur:
                total, correct = await cur.fetchone()

            async with self.bot.db.execute("SELECT COUNT(*), SUM(actual = guessed) FROM HwdykGames WHERE actual = ?", (member.id,)) as cur:
                total_total, correct_total = await cur.fetchone()

            embed.add_field(name="Times played", value=str(total))
            if total:
                embed.add_field(name="Correct answers", value=f"{correct} ({correct/total*100:.2f}%)")
            if not total_total:
                embed.set_footer(text=f"No message by {member.display_name} has appeared yet")
            else:
                times = lambda x: f"{x} times" if x != 1 else "1 time"
                messages = "Messages" if total_total != 1 else "A message"
                embed.set_footer(text=f"{messages} by {member.display_name} have appeared {times(total_total)} and been guessed correctly {times(correct_total)} ({correct_total/total_total*100:.2f}%)")

        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    async def connections(self, ctx, id: int = None):
        """Play a Connections puzzle by ID, or a random one."""
        if id:
            async with self.bot.db.execute("SELECT * FROM ConnectionsPuzzles WHERE id = ?", (id,)) as cur:
                row = await cur.fetchone()
            if not row:
                return await ctx.send(f"No puzzle found with ID '{id}'.")
        else:
            async with self.bot.db.execute("""
                WITH RECURSIVE rand(i) AS (SELECT NULL UNION ALL SELECT ABS(RANDOM()) % ((SELECT MAX(rowid) FROM ConnectionsPuzzles) + 1) FROM rand)
                SELECT ConnectionsPuzzles.* FROM rand INNER JOIN ConnectionsPuzzles ON rowid = i LIMIT 1;
            """) as cur:
                row = await cur.fetchone()
        view = Connections(ctx.author, row["title"], self.bot.get_user(row["owner"]), json.loads(row["categories"]))
        await ctx.send(embed=view.render(), view=view)

    @commands.dm_only()
    @connections.command(name="create", aliases=["add", "new", "make"])
    async def connections_create(self, ctx, title, *, categories):
        """Make a new Connections puzzle."""
        DELIMITERS = ["\n", "|", ";", ",", " "]

        for coverer in ["()", "[]", "{}", "''", '""']:
            if categories.startswith(coverer[0]) and categories.endswith(coverer[1]):
                categories = categories[1:-1]
                break

        for delim in DELIMITERS:
            four = categories.split(delim)
            if len(four) == 4:
                break
        else:
            return await ctx.send("Wrong number of categories. There should be 4 sets of 4 words: `Letters: A B C D; Digits: 1 2 3 4; Symbols: $ % ^ &; Words: foo bar baz qux`.")

        all_had_desc = True
        finals = []
        for category in four:
            desc, _, word_blob = category.rpartition(":")
            word_blob = word_blob.strip()
            if not desc:
                all_had_desc = False

            for delim in DELIMITERS:
                words = [word.strip().strip("'\"").upper() for word in word_blob.split(delim)]
                if len(words) == 4:
                    break
            else:
                return await ctx.send(f"Wrong number of words in category (should be 4): {word_blob}")

            finals.append({"desc": desc.strip(), "words": words})

        async with self.bot.db.execute("INSERT INTO ConnectionsPuzzles (title, owner, categories) VALUES (?, ?, ?) RETURNING id", (title, ctx.author.id, json.dumps(finals))) as cur:
            id, = await cur.fetchone()
        await self.bot.db.commit()

        await ctx.send(f"Successfully created new puzzle (ID {id})." + "\nNote: Some categories were missing descriptions. You can add them with a colon before a category: `Letters: A B C D`."*(not all_had_desc))

    @connections.command(aliases=["all", "ls"])
    async def list(self, ctx, *, who = commands.Author):
        """List someone's Connections puzzles."""
        async with self.bot.db.execute("SELECT id, title FROM ConnectionsPuzzles WHERE owner = ?", (who.id,)) as cur:
            puzzles = await cur.fetchall()
        paginator = EmbedPaginator()
        if not puzzles:
            paginator.add_line(f"{ctx.get_pronouns(who).they_do_not()} have any!")
        else:
            for id, title in puzzles:
                paginator.add_line(f"- **{title}** ({id})")
        paginator.embeds[0].set_author(name=f"{who.global_name or who.name}'s Connectionses", icon_url=who.display_avatar)
        for embed in paginator.embeds:
            await ctx.send(embed=embed)

    @connections.command(aliases=["delete", "minus", "-", "86", "nix", "unmake", "destroy", "rm", "un", "cull", "zero", "0"])
    async def remove(self, ctx, id: int):
        """Delete one of your Connections puzzles."""
        async with self.bot.db.execute("DELETE FROM ConnectionsPuzzles WHERE id = ? AND owner = ? RETURNING title", (id, ctx.author.id)) as cur:
            deleted = await cur.fetchone()
        await self.bot.db.commit()
        if not deleted:
            return await ctx.send("Deleted nothing. Silly you.")
        await ctx.send(f"Deleting **{deleted[0]}**. There it goes...")


async def setup(bot):
    await bot.add_cog(QwdGames(bot))
