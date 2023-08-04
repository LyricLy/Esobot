import discord
import requests
from discord.ext import commands
from ahocorasick import Automaton

import re
from constants import colors, paths, channels
from utils import make_embed, load_json, save_json, show_error


d = requests.get("https://gist.githubusercontent.com/Vexs/629488c4bb4126ad2a9909309ed6bd71/raw/416403f7080d1b353d8517dfef5acec9aafda6c3/emoji_map.json").json()
unicode = Automaton()
for emoji in d.values():
    unicode.add_word(emoji, emoji)
unicode.make_automaton()

custom = re.compile("<a?:[a-zA-Z0-9_]{2,32}:[0-9]{18,22}>")
role = re.compile(r'<@&([0-9]{18,22})>|`(.*?)`|"(.*?)"|\((.*?)\)|\*(.*?)\*|-\s*(.*?)$')

def get_emoji(s):
    emoji = []
    emoji.extend(unicode.iter(s))
    emoji.extend((m.end(), m.group(0)) for m in custom.finditer(s))
    emoji.sort(key=lambda x: x[0])

    out = []
    for end_pos, text in emoji:
        if m := role.search(s, end_pos):
            if m.group(1):
                r = int(m.group(1))
            else:
                for r in m.group(2, 3, 4, 5, 6):
                    if r:
                        break
            out.append((text, r))

    return out


class ReactionRoles(commands.Cog, name="Reaction roles"):
    """A cog for managing Esobot's reaction-based role system."""

    def __init__(self, bot):
        self.bot = bot
        self.messages = load_json(paths.REACTION_ROLE_SAVES)

    def save(self):
        save_json(paths.REACTION_ROLE_SAVES, self.messages)

    async def scan(self, msg, *, content=None, channel_id=None):
        msg_id = msg.id
        content = content or msg.content
        guild = msg.guild

        pairs = {}
        errors = []
        m = {}

        for emoji, role in get_emoji(content):
            if role_obj := discord.utils.get(guild.roles, name=role) or (isinstance(role, int) and guild.get_role(role)):
                pairs[emoji] = role_obj.id
                if role_obj >= guild.me.top_role:
                    errors.append(f"The '{role_obj.name}' role is too high for me to control.")
                if k := m.get(role_obj):
                    errors.append(f"{emoji} and {k} map to the same role. Maybe your formatting is wrong?")
                else:
                    m[role_obj] = emoji
            else:
                errors.append(f"Role '{role}' not found.")

        if not guild.me.guild_permissions.manage_roles:
            errors.append("I don't have the Manage Roles permission.")


        old_data = self.messages.get(str(msg_id))
        old_pairs = old_data and old_data["pairs"]
        if pairs != old_pairs:
            current_emoji = list(old_pairs) if old_pairs else []
            target_emoji = list(pairs)

            for emoji in current_emoji:
                try:
                    target_emoji.remove(emoji)
                except ValueError:
                    pass
            for emoji in target_emoji:
                await msg.add_reaction(emoji)

            if channel_id:
                self.messages[str(msg_id)] = {"origin": channel_id, "pairs": pairs}
            else:
                # this errors if there isn't already an entry, but this should never happen as we always pass channel_id when adding a new message
                self.messages[str(msg_id)]["pairs"] = pairs
            self.save()
            lines = [f"- {emoji}: <@&{role}>" for emoji, role in pairs.items()] if pairs else ["No reactions configured."]
            if errors:
                lines.append("")
                lines.append("Issues were found.")
                lines.extend("- " + e for e in errors)
            return "\n".join(lines)
        else:
            return None

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def rolewatch(self, ctx, *, msg: discord.Message):
        """Register a message for reaction role management."""
        m = await self.scan(msg, channel_id=ctx.channel.id)

        if m:
            await ctx.send(f"Data parsed and committed. I'm watching this message for reactions.\n\n{m}", allowed_mentions=discord.AllowedMentions.none())
        else:
            await ctx.send("Nothing has changed.")

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload):
        msg_id = payload.message_id
        if data := self.messages.get(str(msg_id)):
            guild = self.bot.get_guild(payload.guild_id)
            p = discord.PartialMessage(id=msg_id, channel=guild.get_channel(payload.channel_id))
            msg = await self.scan(p, content=payload.data["content"])
            if msg:
                channel = guild.get_channel(data["origin"])
                await channel.send(f"Detected changes to <https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{msg_id}>.\n\n{msg}", allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        self.messages.pop(str(payload.message_id), None)
        self.save()

    async def dry(self, method, payload):
        if data := self.messages.get(str(payload.message_id)):
            guild = self.bot.get_guild(payload.guild_id)
            role = guild.get_role(data["pairs"][str(payload.emoji)])
            try:
                await method(guild.get_member(payload.user_id), role)
            except discord.Forbidden:
                channel = guild.get_channel(data["origin"])
                await channel.send(f"I tried to change the role '{role.name}' on {payload.member}, but I don't have permission.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.dry(discord.Member.add_roles, payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.dry(discord.Member.remove_roles, payload)


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
