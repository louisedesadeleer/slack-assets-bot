# slack-assets-bot

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
- **Private to you** — only Slack user IDs you authorize in `.env` can use the bot. Anyone else gets a polite refusal.

## Image classification

Uploaded images get classified into `screenshots/` or `photos/`:

1. **Filename pre-check** (free, instant) — `CleanShot*`, `Screenshot*`, etc. → `screenshots/`
2. **`claude` CLI vision call** — if Claude Code is installed, the bot shells out to `claude -p` for everything else. Uses your Claude Pro/Max subscription, no extra API cost. ~10s per image.
3. **Fallback** — if neither matches, images land in `photos/`.

Don't have Claude Code? Skip step 2 — the bot still works, you just won't get the screenshot/photo split.

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

### 4. Authorize yourself

The bot installs at the workspace level, which means anyone in your Slack workspace can DM it. To prevent that, every message is checked against `ALLOWED_SLACK_USERS` in `.env` — empty by default, so the bot refuses all messages until you add your ID.

1. DM the bot anything (e.g. "hi").
2. It'll reply with `Your Slack user ID is U01234ABCD`.
3. Paste that ID into `.env` as `ALLOWED_SLACK_USERS=U01234ABCD` (comma-separated to authorize multiple people).
4. Restart the bot.

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

## Rename syntax

| You type | Result |
|---|---|
| `name: kanye_laugh` | File saved as `kanye_laugh.ext` |
| `rename: drake_pointing` | Same |
| `save as: best_meme_ever` | Same |
| `name=spongebob_yelling` | Same |
| `save as kanye_laugh` *(at start of message, no colon)* | Same |

Multiple files in one message with the same rename get `_1`, `_2` suffixes. YouTube uses the same name for both the `.mp4` and `.mp3`.

## Folder layout

The folder you picked during setup gets one subfolder per category you enabled. Example with the defaults:

```
~/assets/
├── screenshots/   # CleanShot, Screenshot, anything classified as UI
├── photos/        # everything else: real-world shots, memes, designed images
├── videos/        # .mp4 from YouTube + any video file uploads
└── sounds/        # .mp3 from YouTube + any audio file uploads
```

If you opt into `memes` or `thumbnails`, those folders are added and the Claude classifier learns to route to them too.

## License

MIT
