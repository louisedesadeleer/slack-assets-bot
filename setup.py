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
import subprocess
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
    ("logos", "Brand marks, wordmarks, app icons (needs Claude classifier)", False),
]

REPO_DIR = Path(__file__).resolve().parent
ENV_PATH = REPO_DIR / ".env"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.assetsbot.plist"

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.assetsbot</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>{bot_py}</string>
  </array>
  <key>WorkingDirectory</key><string>{repo}</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def install_launchagent() -> bool:
    """Write plist, (re)load it. Returns True on success."""
    venv_python = REPO_DIR / ".venv" / "bin" / "python"
    python_path = str(venv_python) if venv_python.exists() else sys.executable
    plist_xml = PLIST_TEMPLATE.format(
        python=python_path,
        bot_py=REPO_DIR / "bot.py",
        repo=REPO_DIR,
        log=REPO_DIR / "bot.log",
        home=Path.home(),
    )
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_xml)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"\n  ⚠️  launchctl load failed: {result.stderr.strip()}")
        print(f"      plist saved at {PLIST_PATH}")
        print(f"      load manually with: launchctl load {PLIST_PATH}")
        return False
    return True


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

    print(
        "\n  ⚠️  Anyone in your Slack workspace can DM the bot. Since the\n"
        "      bot saves files to YOUR computer, you probably want to lock\n"
        "      it down to just you (or specific teammates).\n"
    )
    scope = questionary.select(
        "Who should be able to use this bot?",
        choices=[
            questionary.Choice(
                "Just me (private) — bot refuses everyone else",
                value="private",
            ),
            questionary.Choice(
                "Me + specific teammates — I'll paste their Slack user IDs",
                value="allowlist",
            ),
            questionary.Choice(
                "Anyone in my Slack workspace (NOT recommended unless solo workspace)",
                value="workspace",
            ),
        ],
    ).ask()

    allow_workspace = "true" if scope == "workspace" else ""
    if scope == "workspace":
        confirm = questionary.confirm(
            "Are you sure? Every workspace member will be able to drop files "
            "onto your machine.",
            default=False,
        ).ask()
        if not confirm:
            scope = "private"
            allow_workspace = ""

    if scope == "private":
        print(
            "\n  Tip: leave the field below empty if you don't know your\n"
            "  Slack user ID — DM the bot once and it'll tell you.\n"
        )
        allowed_users = questionary.text(
            "Your Slack user ID (e.g. U01234ABCD)",
            default=env.get("ALLOWED_SLACK_USERS", ""),
        ).ask() or ""
    elif scope == "allowlist":
        print(
            "\n  Find a user's Slack ID: open their profile in Slack →\n"
            "  ⋮ menu → 'Copy member ID'.\n"
        )
        allowed_users = questionary.text(
            "Slack user IDs, comma-separated",
            default=env.get("ALLOWED_SLACK_USERS", ""),
        ).ask() or ""
    else:
        allowed_users = ""

    auto_name = questionary.confirm(
        "Auto-name images using Claude vision? (e.g. CleanShot_2026...png "
        "becomes team_dashboard.png so you can find it later by saying "
        "'use the team dashboard image')",
        default=True,
    ).ask()

    install_agent = False
    if sys.platform == "darwin":
        install_agent = questionary.confirm(
            "Run the bot automatically at login + auto-restart if it dies? "
            "(installs a macOS LaunchAgent so the bot never goes down silently)",
            default=True,
        ).ask()

    env_text = "\n".join(
        [
            f"SLACK_BOT_TOKEN={bot_token}",
            f"SLACK_APP_TOKEN={app_token}",
            f"ALLOWED_SLACK_USERS={allowed_users}",
            f"ALLOW_WORKSPACE={allow_workspace}",
            f"ASSETS_DIR={assets_dir}",
            f"CATEGORIES={','.join(selected)}",
            f"AUTO_NAME_IMAGES={'true' if auto_name else 'false'}",
            "",
        ]
    )
    ENV_PATH.write_text(env_text)

    assets_dir.mkdir(parents=True, exist_ok=True)
    for cat in selected:
        (assets_dir / cat).mkdir(parents=True, exist_ok=True)

    print(f"\n  ✓ wrote {ENV_PATH}")
    print(f"  ✓ created {assets_dir}/{{{','.join(selected)}}}/")

    agent_running = False
    if install_agent:
        agent_running = install_launchagent()
        if agent_running:
            print(f"  ✓ LaunchAgent installed — bot is running now, will auto-start at login")
            print(f"  → tail logs:  tail -f {REPO_DIR / 'bot.log'}")
            print(f"  → stop:       launchctl unload {PLIST_PATH}")

    if not agent_running:
        print("\n  next: run `python bot.py`")
    if not allowed_users:
        print("  then DM the bot — it'll reply with your user ID to add to ALLOWED_SLACK_USERS")

    if sys.platform == "darwin":
        print(
            f"\n  💡 pro tip: drag {assets_dir} into Finder's sidebar Favorites\n"
            f"     so you can drop files into it from any save dialog or window in one click."
        )
        open_finder = questionary.confirm(
            "Open the folder in Finder now so you can drag it into Favorites?",
            default=True,
        ).ask()
        if open_finder:
            subprocess.run(["open", str(assets_dir)])
    print()


if __name__ == "__main__":
    main()
