# slack-assets-bot

![slack-assets-bot](./banner.png)

In an age of agentic video editing and AI-generated content, the thing that makes your work feel like *yours* is the taste you bring to your videos and content. The niche meme you remembered. The screenshot of that one tweet. The song only your audience will know. The sound effect that always lands.

**This bot is a low-friction way to keep that library at hand.** Drop anything into a Slack DM — files, YouTube links, image URLs — and it lands organized on your machine, named so Claude (or you) can find it later. Build the asset bank, then let the agents do the editing.

---

A personal Slack bot that turns your DMs into an asset library. Drop a file, paste a YouTube link, send any image URL — it sorts everything into category folders on your machine. You pick the categories during setup.

```
you  → 📎 screenshot.png        bot → ✓ ~/assets/screenshots/screenshot.png
you  → https://youtu.be/abc     bot → ✓ ~/assets/videos/title.mp4
                                      ✓ ~/assets/sounds/title.mp3
you  → name: kanye_laugh
       📎 reaction.png           bot → ✓ ~/assets/photos/kanye_laugh.png
```

## What it does

- **Files** route by mimetype — images go through a classifier (screenshot vs photo), videos to `videos/`, audio to `sounds/`.
- **YouTube links** download both the `.mp4` (videos/) and the `.mp3` (sounds/).
- **Other URLs** route by `Content-Type` — direct image/video/audio links work, web pages are ignored.
- **Rename on the fly** by typing `name: foo` / `rename: foo` / `save as foo` in the message. Extension added automatically.
- **Project tagging** — typing `project: kanye-launch` in the message routes the asset to `~/assets/projects/kanye-launch/<category>/` instead of the top-level category folder. Build asset bundles per video/campaign on the fly.
- **Auto-naming for images** — files with generic names (`CleanShot_…`, `Screenshot…`, `IMG_…`) get a descriptive slug from Claude vision (e.g. `team_dashboard.png`, `kanye_west_laughing.png`) so AI assistants can find them later by name. Skipped when you provide a manual rename.
- **Private by default** — the setup wizard asks who can use the bot (just you / specific teammates / whole workspace) and locks it down accordingly.

## Image classification & auto-naming

Uploaded images get two passes:

**Where to put it** (folder):
1. Filename pre-check — `CleanShot*`, `Screenshot*`, etc. → `screenshots/`
2. `claude` CLI vision call for everything else → `screenshots/` or `photos/`
3. Fallback: `photos/`

**What to call it** (filename), when `AUTO_NAME_IMAGES=true`:
1. If you typed `name: foo` in the message → `foo.ext`
2. If the original filename looks generic (`CleanShot_2026…`, `IMG_1234`, `screenshot.png`) → `claude` describes the image in 2–5 words → `team_dashboard.png`, `kanye_west_laughing.png`, `iphone_settings_menu.png`
3. Otherwise the original name is kept

This makes the asset library searchable by content. Later, when editing in another tool, you (or another agent) can say *"use the kanye meme"* and it finds the file by name.

Don't have Claude Code? Both steps degrade — images all land in `photos/` with original filenames. The bot still works.

## Requirements

- macOS or Linux (untested on Windows)
- Python 3.10+
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`ffmpeg`](https://ffmpeg.org/) on PATH (`brew install yt-dlp ffmpeg`)
- A Slack workspace where you can install custom apps
- *Optional:* [Claude Code](https://claude.com/claude-code) for image classification

## Setup

### 1. Create the Slack app

1. Go to https://api.slack.com/apps → **Create New App** → **From manifest** → pick your workspace.
2. Paste the contents of [`manifest.yml`](./manifest.yml). Click **Create**.
3. **Basic Information** → scroll to **App-Level Tokens** → **Generate Token and Scopes** → add `connections:write` → name it → copy the `xapp-...` token. That's your `SLACK_APP_TOKEN`.
4. **Install App** → install to your workspace → copy the **Bot User OAuth Token** (`xoxb-...`). That's your `SLACK_BOT_TOKEN`.
5. **App Home** → toggle **Messages Tab ON** and tick **"Allow users to send Slash commands and messages from the messages tab"**.
6. In Slack, find the bot in your sidebar and open a DM with it.

### 2. Install and configure

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git
cd slack-assets-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python setup.py
```

The setup wizard asks you:
- **What to name your assets folder** (default: `~/assets`)
- **Which categories you want** — checkbox list. Default 4: screenshots, photos, videos, sounds. Opt-in extras: memes, thumbnails. Pick whichever fits how you organize stuff.
- **Your Slack tokens** (from step 1)
- **Authorized Slack user IDs** — leave empty for now if you don't know yours

It writes `.env` and creates the chosen folders.

### 3. Run the bot

```bash
python bot.py
```

You should see `assets bot starting, saving to ...`.

### 4. Authorize yourself (if you picked "private" or "allowlist")

When a Slack app is installed in a workspace, **any workspace member can DM it** by default. Since this bot saves files to **your** computer, you almost certainly want to gate that. The setup wizard already asked which mode you want; here's how each one behaves:

| Mode | `.env` config | Behavior |
|---|---|---|
| **Private (just me)** | `ALLOWED_SLACK_USERS=U01234ABCD` | Only listed user IDs can use the bot. Everyone else gets a polite refusal. |
| **Specific teammates** | `ALLOWED_SLACK_USERS=U01234,U05678,U09012` | Same as above with multiple IDs. |
| **Workspace-wide** | `ALLOW_WORKSPACE=true` | Skips the check entirely. Use only if you're alone in the workspace. |

If you don't know your Slack user ID:
1. Start the bot with `ALLOWED_SLACK_USERS=` empty.
2. DM the bot anything (e.g. "hi").
3. It'll reply with `Your Slack user ID is U01234ABCD`.
4. Paste that ID into `.env`, restart the bot.

To find a teammate's ID: open their profile in Slack → ⋮ menu → **Copy member ID**.

Now DM the bot a file or a link — it'll reply in-thread with the saved path.

### 5. Keep it running in the background (macOS)

```bash
cat > ~/Library/LaunchAgents/com.assetsbot.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.assetsbot</string>
  <key>ProgramArguments</key>
  <array>
    <string>REPLACE_WITH_REPO_PATH/.venv/bin/python</string>
    <string>REPLACE_WITH_REPO_PATH/bot.py</string>
  </array>
  <key>WorkingDirectory</key><string>REPLACE_WITH_REPO_PATH</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>REPLACE_WITH_REPO_PATH/bot.log</string>
  <key>StandardErrorPath</key><string>REPLACE_WITH_REPO_PATH/bot.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.assetsbot.plist
```

Replace `REPLACE_WITH_REPO_PATH` with the absolute path to your clone. Logs live at `bot.log`.

Stop with `launchctl unload ~/Library/LaunchAgents/com.assetsbot.plist`.

## Message syntax

### Rename

| You type | Result |
|---|---|
| `name: kanye_laugh` | File saved as `kanye_laugh.ext` |
| `rename: drake_pointing` | Same |
| `save as: best_meme_ever` | Same |
| `name=spongebob_yelling` | Same |
| `save as kanye_laugh` *(at start of message, no colon)* | Same |

Multiple files in one message with the same rename get `_1`, `_2` suffixes. YouTube uses the same name for both the `.mp4` and `.mp3`.

### Project tagging

| You type | Result |
|---|---|
| `project: kanye-launch` + 📎 screenshot.png | `~/assets/projects/kanye-launch/screenshots/screenshot.png` |
| `project: Q4 Brand Refresh` + YouTube link | `~/assets/projects/q4-brand-refresh/videos/...mp4` + `.../sounds/...mp3` |
| `project=demo-2026` + image URL | `~/assets/projects/demo-2026/photos/...` |

Project names are slug-ified (lowercased, non-alphanumeric → `-`). Folders are created on demand. Combine freely with `name:` and `project:`:

```
project: kanye-launch  name: opening-shot
📎 hero.mp4
→ ~/assets/projects/kanye-launch/videos/opening-shot.mp4
```

## Folder layout

The folder you picked during setup gets one subfolder per category you enabled, plus a `projects/` namespace for project-tagged assets:

```
~/assets/
├── screenshots/                # untagged screenshots
├── photos/                     # untagged photos
├── videos/                     # untagged videos
├── sounds/                     # untagged sounds
└── projects/
    ├── kanye-launch/
    │   ├── screenshots/
    │   ├── videos/
    │   └── sounds/
    └── q4-brand-refresh/
        └── photos/
```

If you opt into `memes` or `thumbnails` during setup, those folders are added too. Project folders mirror whichever categories you enabled.

## License

MIT
