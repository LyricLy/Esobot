import asyncio
import discord
import asyncio
import os

from discord.ext import commands, menus

from utils import show_error


def format_jp_entry(entry):
    try:
        return f"{entry['word']}【{entry['reading']}】"
    except KeyError:
        try:
            return entry["reading"]
        except KeyError:
            try:
                return entry["word"]
            except KeyError:
                return "???"

class DictSource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entry):
        e = discord.Embed(
            title = f"Result #{menu.current_page + 1}",
            description = format_jp_entry(entry['japanese'][0])
        )
        if tags := [
            *["common"]*entry.get("is_common", False),
            *sorted(f"JLPT {x.partition('-')[2]}" for x in entry.get("jlpt", []))[-1:],
        ]:
            e.title += f" ({', '.join(tags)})"
        for i, sense in enumerate(entry["senses"], start=1):
            e.add_field(
                name = ", ".join(sense["parts_of_speech"]) if sense["parts_of_speech"] else "\u200b",
                value = " | ".join([
                    f"{i}. " + "; ".join(sense["english_definitions"]),
                    *filter(None, [", ".join(f"*{x}*" for x in sense["tags"] + sense["info"])]),
                ]),
                inline=False
            )
        if len(entry["japanese"]) > 1:
            e.add_field(name = "Other forms", value = "\n".join(format_jp_entry(x) for x in entry["japanese"][1:]), inline=False)
        return e

class Japanese(commands.Cog):
    """Weeb stuff."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["jp", "jsh", "dictionary", "dict"])
    async def jisho(self, ctx, *, query):
        """Look things up in the Jisho dictionary."""
        async with self.bot.session.get("https://jisho.org/api/v1/search/words", params={"keyword": query}) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                data = None
        if not data["data"]:
            return await show_error(ctx, "That query returned no results.")
        pages = menus.MenuPages(source=DictSource(data["data"]), clear_reactions_after=True)
        await pages.start(ctx)

    @commands.group(
        invoke_without_command=True,
        aliases=[
            "what", "unlyric", "undweeb", ";)", "otherlanguagesscareme",
            "機械翻訳", "ifyouhaveajapaneseimewhyareyouusingashittygptcommand",
        ],
    )
    async def unweeb(self, ctx, *, lyric_quote: commands.clean_content = ""):
        """Translate Japanese."""
        if not lyric_quote and (r := ctx.message.reference):
            if not isinstance(r.resolved, discord.Message):
                return await ctx.send("Reply unavailable :(")
            lyric_quote = r.resolved.content
        if not lyric_quote:
            async for msg in ctx.history(limit=12):
                if any(0x3040 <= ord(c) <= 0x309F or 0x30A0 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in msg.content):
                    lyric_quote = msg.content
                    break
            else:
                return await ctx.send("What?")

        async with ctx.typing(), self.bot.session.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {os.environ['DEEPL_API_KEY']}"},
            json={"text": [lyric_quote], "source_lang": "JA", "target_lang": "EN-GB"},
        ) as resp:
            data = await resp.json()

        await ctx.reply(data["translations"][0]["text"])


async def setup(bot):
    await bot.add_cog(Japanese(bot))
