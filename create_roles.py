"""
Bulk-create Discord roles from a list of names.

Setup:
  1. pip install requests
  2. Fill in BOT_TOKEN and SERVER_ID below.
  3. Put one character name per line in characters.txt (same folder as this script).
  4. Run: python create_roles.py
"""

import time
import requests

# ==== CONFIGURATION — fill these in ====
BOT_TOKEN = "PLACEHOLDER"        # From Discord Developer Portal > Bot tab
SERVER_ID = "1403091108602576966"         # Right-click your server icon > Copy Server ID
CHARACTER_NAMES_FILE = "characters.txt"  # One character/role name per line

# ==== SCRIPT — no need to edit below this line ====
API_BASE = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json",
}


def get_existing_role_names() -> set[str]:
    """Fetch the server's current roles so we can skip ones that already exist."""
    url = f"{API_BASE}/guilds/{SERVER_ID}/roles"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return {role["name"] for role in response.json()}


def create_role(name: str) -> None:
    """Create a single role in the target server, retrying if rate-limited."""
    url = f"{API_BASE}/guilds/{SERVER_ID}/roles"
    payload = {"name": name, "mentionable": True}
    response = requests.post(url, headers=HEADERS, json=payload)

    if response.status_code in (200, 201):
        print(f"✅ Created role: {name}")
    elif response.status_code == 429:
        retry_after = response.json().get("retry_after", 1)
        print(f"⏳ Rate limited — waiting {retry_after}s before retrying '{name}'...")
        time.sleep(retry_after)
        create_role(name)
    else:
        print(f"❌ Failed to create '{name}': {response.status_code} {response.text}")


def main() -> None:
    with open(CHARACTER_NAMES_FILE, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]

    if not names:
        print(f"No names found in {CHARACTER_NAMES_FILE} — nothing to do.")
        return

    print("Checking which roles already exist...")
    existing_names = get_existing_role_names()

    to_create = [name for name in names if name not in existing_names]
    skipped = len(names) - len(to_create)

    if skipped:
        print(f"Skipping {skipped} role(s) that already exist.")

    if not to_create:
        print("Nothing left to create — all roles already exist.")
        return

    print(f"Creating {len(to_create)} role(s)...")
    for name in to_create:
        create_role(name)
        time.sleep(0.5)  # small buffer to stay comfortably under Discord's rate limits

    print("Done!")


if __name__ == "__main__":
    main()