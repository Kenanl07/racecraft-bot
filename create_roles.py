"""
Character role picker bot for Discord.

Presents members with dropdown menus (one per group of up to 25 characters)
so they can self-select any number of "favorite character" roles.

Setup:
  1. pip install -r requirements.txt
  2. Fill in BOT_TOKEN and SERVER_ID below
  3. Have characters.txt file with umas
  4. Run: python bot.py
  5. In server, run the /post-role-menus command in the channel
"""

import discord
from discord import app_commands
from discord.ext import commands

# ==== CONFIGURATION ====
BOT_TOKEN = "PLACEHOLDER"
SERVER_ID = 1403091108602576966
CHARACTER_NAMES_FILE = "characters.txt"
MAX_OPTIONS_PER_MENU = 25
MAX_MENUS_PER_MESSAGE = 5

# ==== SETUP ====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def load_character_chunks() -> list[list[str]]:
    """Read characters.txt and split it into chunks of MAX_OPTIONS_PER_MENU."""
    with open(CHARACTER_NAMES_FILE, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    return [
        names[i:i + MAX_OPTIONS_PER_MENU]
        for i in range(0, len(names), MAX_OPTIONS_PER_MENU)
    ]


def group_chunks_into_messages(chunks: list[list[str]]) -> list[list[list[str]]]:
    """Group chunks into batches of up to MAX_MENUS_PER_MESSAGE dropdowns each."""
    return [
        chunks[i:i + MAX_MENUS_PER_MESSAGE]
        for i in range(0, len(chunks), MAX_MENUS_PER_MESSAGE)
    ]


class CharacterSelect(discord.ui.Select):
    """One dropdown covering up to 25 characters. Submitting it syncs your
    roles to match exactly what's checked in THIS dropdown — other dropdowns
    are untouched."""

    def __init__(self, chunk_index: int, names: list[str], server: discord.server):
        self.role_by_value: dict[str, discord.Role] = {}
        options = []
        for name in names:
            role = discord.utils.get(server.roles, name=name)
            if role is None:
                print(f"No role found matching '{name}' — skipping from menu.")
                continue
            self.role_by_value[str(role.id)] = role
            options.append(discord.SelectOption(label=name, value=str(role.id)))

        first_num = chunk_index * MAX_OPTIONS_PER_MENU + 1
        last_num = chunk_index * MAX_OPTIONS_PER_MENU + len(options)

        super().__init__(
            custom_id=f"char_role_menu_{chunk_index}",
            placeholder=f"Characters {first_num}–{last_num}",
            min_values=0,
            max_values=len(options) if options else 1,
            options=options or [discord.SelectOption(label="(no roles found)", value="none")],
        )

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        selected_ids = set(self.values)
        to_add, to_remove = [], []

        for value, role in self.role_by_value.items():
            has_role = role in member.roles
            if value in selected_ids and not has_role:
                to_add.append(role)
            elif value not in selected_ids and has_role:
                to_remove.append(role)

        if to_add:
            await member.add_roles(*to_add, reason="Character role picker")
        if to_remove:
            await member.remove_roles(*to_remove, reason="Character role picker")

        summary_parts = []
        if to_add:
            summary_parts.append("Added: " + ", ".join(r.name for r in to_add))
        if to_remove:
            summary_parts.append("Removed: " + ", ".join(r.name for r in to_remove))
        summary = "\n".join(summary_parts) if summary_parts else "No changes."

        await interaction.response.send_message(summary, ephemeral=True)


class CharacterRoleView(discord.ui.View):
    """A persistent view holding up to 5 dropdowns for one message."""

    def __init__(self, chunk_group: list[list[str]], start_index: int, server: discord.server):
        super().__init__(timeout=None)
        for offset, names in enumerate(chunk_group):
            self.add_item(CharacterSelect(start_index + offset, names, server))


@bot.event
async def on_ready():
    server = bot.get_server(SERVER_ID)
    chunks = load_character_chunks()
    message_groups = group_chunks_into_messages(chunks)

    # Re-register a persistent view for every message group so dropdowns
    # posted before a restart keep working afterward.
    start_index = 0
    for group in message_groups:
        bot.add_view(CharacterRoleView(group, start_index, server))
        start_index += len(group)

    await bot.tree.sync(server=server)
    print(f"✅ Logged in as {bot.user}. Ready in {server.name}.")


@bot.tree.command(
    name="post-role-menus",
    description="Post the character role picker dropdowns in this channel.",
    server=discord.Object(id=SERVER_ID),
)
@app_commands.checks.has_permissions(manage_roles=True)
async def post_role_menus(interaction: discord.Interaction):
    server = interaction.server
    chunks = load_character_chunks()
    message_groups = group_chunks_into_messages(chunks)

    await interaction.response.send_message(
        f"Posting {len(message_groups)} message(s) with role pickers...",
        ephemeral=True,
    )

    start_index = 0
    for i, group in enumerate(message_groups, start=1):
        view = CharacterRoleView(group, start_index, server)
        await interaction.channel.send(
            f"**Pick your favorite characters — part {i}/{len(message_groups)}**\n"
            "Select as many as you want from each dropdown below.",
            view=view,
        )
        start_index += len(group)


if __name__ == "__main__":
    bot.run(BOT_TOKEN)