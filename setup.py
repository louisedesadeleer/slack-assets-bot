"""Interactive setup wizard for slack-assets-bot.

Run once with `python setup.py`. Walks you through:
- Where to save assets on your machine
- Which categories you want
- Your Slack tokens
- Authorizing your Slack user ID

Writes everything to .env. Re-running rewrites it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import questionary
except ImportError:
    print("This wizard needs `questionary`. Install with: pip install -r requirements.txt")
    sys.exit(1)


CATEGORY_CHOICES = [
    ("screenshots", "CleanShot, Screenshot, app captures", True),
    ("photos", "Real-world photos, designed images, everything else", True),
    ("videos", ".mp4 from YouTube + any video file uploads", True),
    ("sounds", ".mp3 from YouTube + any audio file uploads", True),
    ("memes", "Reaction images, GIF macros (needs Claude classifier)", False),
    ("thumbnails", "YouTube/social cover art (needs Claude classifier)", False),
]

ENV_PATH = Path(__file__).resolve().parent / ".env"


def existing_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def main() -> None:
    print("\n  slack-assets-bot setup\n")
    env = existing_env()

    folder_name = questionary.text(
        "What do you want to call your assets folder?",
        default=env.get("ASSETS_DIR", "~/assets").replace(str(Path.home()), "~"),
    ).ask()
    if folder_name is None:
        sys.exit(1)
    assets_dir = Path(os.path.expanduser(folder_name)).resolve()

    selected = questionary.checkbox(
        "Which categories do you want? (space to toggle, enter to confirm)",
        choices=[
            questionary.Choice(f"{name} — {desc}", value=name, checked=default)
            for name, desc, default in CATEGORY_CHOICES
        ],
    ).ask()
    if not selected:
        print("\n  You need to pick at least one category. Try again.")
        sys.exit(1)

    bot_token = questionary.password(
        "Slack Bot Token (xoxb-...)",
        default=env.get("SLACK_BOT_TOKEN", ""),
    ).ask() or ""
    app_token = questionary.password(
        "Slack App-Level Token (xapp-...)",
        default=env.get("SLACK_APP_TOKEN", ""),
    ).ask() or ""

    allowed_users = questionary.text(
        "Slack user IDs allowed to use this bot, comma-separated "
        "(leave empty to discover yours by DMing the bot once)",
        default=env.get("ALLOWED_SLACK_USERS", ""),
    ).ask() or ""

    env_text = "\n".join(
        [
            f"SLACK_BOT_TOKEN={bot_token}",
            f"SLACK_APP_TOKEN={app_token}",
            f"ALLOWED_SLACK_USERS={allowed_users}",
            f"ASSETS_DIR={assets_dir}",
            f"CATEGORIES={','.join(selected)}",
            "",
        ]
    )
    ENV_PATH.write_text(env_text)

    assets_dir.mkdir(parents=True, exist_ok=True)
    for cat in selected:
        (assets_dir / cat).mkdir(parents=True, exist_ok=True)

    print(f"\n  ✓ wrote {ENV_PATH}")
    print(f"  ✓ created {assets_dir}/{{{','.join(selected)}}}/")
    print("\n  next: run `python bot.py`")
    if not allowed_users:
        print("  then DM the bot — it'll reply with your user ID to add to ALLOWED_SLACK_USERS")
    print()


if __name__ == "__main__":
    main()
