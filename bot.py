"""
Uma role picker bot for Racecraft Discord.

Posts a button per group of characters (split into "Playable Umas" and
"NPCs" sections, wherever characters.txt breaks alphabetical order). Clicking
a button opens a private (ephemeral) set of dropdowns, pre-checked to match
whatever roles that member already holds, so what they see always matches
what they actually have. Submitting syncs their roles to the checkboxes.

Setup:
  1. pip install -r requirements.txt
  2. Fill in BOT_TOKEN, SERVER_ID, and ALLOWED_ROLE_IDS below.
     (Right-click a role in Server Settings > Roles with Developer Mode on
     to Copy Role ID.)
  3. Have characters.txt in this same folder, one name per line.
  4. Run: python bot.py
  5. In your server, run /post-role-menus in the channel where you want the
     pickers to appear. Only members with one of ALLOWED_ROLE_IDS can run it.
"""

import discord
from discord import app_commands
from discord.ext import commands

# ==== CONFIGURATION — fill these in ====
BOT_TOKEN = "PLACEHOLDER"
SERVER_ID = 1403091108602576966
ALLOWED_ROLE_IDS = [1450886692960604170, 1465857407195418886]  # members with ANY of these roles can run /post-role-menus
CHARACTER_NAMES_FILE = "characters.txt"
MAX_OPTIONS_PER_MENU = 25       # Discord's hard limit per select menu
MAX_MENUS_PER_MESSAGE = 5       # Discord's hard limit: 5 component rows per message

# ==== SETUP — no need to edit below this line ====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def load_all_names() -> list[str]:
    with open(CHARACTER_NAMES_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def split_playable_and_npc(names: list[str]) -> tuple[list[str], list[str]]:
    """Split at the first point alphabetical order breaks. Everything before
    that point is treated as playable Umas, everything after as NPCs."""
    for i in range(1, len(names)):
        if names[i].lower() < names[i - 1].lower():
            return names[:i], names[i:]
    return names, []  # order never breaks — treat everything as playable


def chunk(names: list[str], size: int) -> list[list[str]]:
    return [names[i:i + size] for i in range(0, len(names), size)]


def group_chunks_into_messages(chunks: list, size: int) -> list:
    return [chunks[i:i + size] for i in range(0, len(chunks), size)]


def group_letter_range_label(chunk_group: list[list[str]]) -> str:
    first_letter = chunk_group[0][0][0].upper()
    last_letter = chunk_group[-1][-1][0].upper()
    if first_letter == last_letter:
        return f"Open picker ({first_letter})"
    return f"Open picker ({first_letter}–{last_letter})"


def build_sections():
    """Returns [(section_title, [chunk, chunk, ...], id_prefix), ...]."""
    all_names = load_all_names()
    playable, npc = split_playable_and_npc(all_names)

    sections = []
    if playable:
        sections.append(("Playable Umas", chunk(playable, MAX_OPTIONS_PER_MENU), "playable"))
    if npc:
        sections.append(("NPCs", chunk(npc, MAX_OPTIONS_PER_MENU), "npc"))
    return sections


class CharacterSelect(discord.ui.Select):
    """One dropdown covering up to 25 characters, pre-checked to reflect the
    roles this specific member already holds. Submitting syncs their roles to
    match exactly what's checked in this dropdown — other dropdowns are
    untouched."""

    def __init__(self, custom_id_suffix: str, names: list[str], guild: discord.Guild, member: discord.Member):
        self.role_by_value: dict[str, discord.Role] = {}
        options = []
        for name in names:
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                print(f"⚠️  No role found matching '{name}' — skipping from menu.")
                continue
            self.role_by_value[str(role.id)] = role
            options.append(discord.SelectOption(
                label=name,
                value=str(role.id),
                default=role in member.roles,
            ))

        first_num_label = names[0][0].upper()
        last_num_label = names[-1][0].upper()
        placeholder = (
            f"Characters {first_num_label}"
            if first_num_label == last_num_label
            else f"Characters {first_num_label}–{last_num_label}"
        )

        super().__init__(
            custom_id=f"char_select_{custom_id_suffix}",
            placeholder=placeholder,
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


def build_ephemeral_dropdown_view(chunk_group: list[list[str]], guild: discord.Guild, member: discord.Member) -> discord.ui.View:
    """A short-lived view (not persisted across restarts) shown privately to
    one member, with each dropdown pre-checked to match their current roles."""
    view = discord.ui.View(timeout=180)
    for offset, names in enumerate(chunk_group):
        view.add_item(CharacterSelect(f"eph_{offset}_{member.id}", names, guild, member))
    return view


class OpenMenuButton(discord.ui.Button):
    """Persistent button that opens a private, personalized set of dropdowns
    for whoever clicks it."""

    def __init__(self, custom_id: str, label: str, chunk_group: list[list[str]]):
        super().__init__(style=discord.ButtonStyle.primary, label=label, custom_id=custom_id)
        self.chunk_group = chunk_group

    async def callback(self, interaction: discord.Interaction):
        view = build_ephemeral_dropdown_view(self.chunk_group, interaction.guild, interaction.user)
        await interaction.response.send_message(
            "Select as many as you want from each dropdown below. "
            "Already-checked options match roles you currently have.",
            view=view,
            ephemeral=True,
        )


def build_button_view(prefix: str, m_index: int, chunk_group: list[list[str]]) -> discord.ui.View:
    """Persistent view holding the one button for a message group."""
    view = discord.ui.View(timeout=None)
    view.add_item(OpenMenuButton(
        custom_id=f"open_menu_{prefix}_{m_index}",
        label=group_letter_range_label(chunk_group),
        chunk_group=chunk_group,
    ))
    return view


@bot.event
async def on_ready():
    guild = bot.get_guild(SERVER_ID)
    sections = build_sections()

    # Re-register a persistent view for every posted button so they keep
    # working after a restart.
    for _, chunks, prefix in sections:
        message_groups = group_chunks_into_messages(chunks, MAX_MENUS_PER_MESSAGE)
        for m_index, group in enumerate(message_groups):
            bot.add_view(build_button_view(prefix, m_index, group))

    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user}. Ready in {guild.name}.")


@bot.tree.command(
    name="post-role-menus",
    description="Post the character role picker buttons in this channel.",
    guild=discord.Object(id=SERVER_ID),
)
@app_commands.checks.has_any_role(*ALLOWED_ROLE_IDS)
async def post_role_menus(interaction: discord.Interaction):
    sections = build_sections()

    await interaction.response.send_message("Posting role pickers...", ephemeral=True)

    for title, chunks, prefix in sections:
        message_groups = group_chunks_into_messages(chunks, MAX_MENUS_PER_MESSAGE)
        for m_index, group in enumerate(message_groups):
            view = build_button_view(prefix, m_index, group)
            await interaction.channel.send(
                f"**{title} — part {m_index + 1}/{len(message_groups)}**\n"
                "Click the button below to pick your favorites from this group.",
                view=view,
            )


@post_role_menus.error
async def post_role_menus_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingAnyRole):
        await interaction.response.send_message(
            "You don't have permission to run this command.", ephemeral=True
        )
    else:
        raise error


if __name__ == "__main__":
    bot.run(BOT_TOKEN)
