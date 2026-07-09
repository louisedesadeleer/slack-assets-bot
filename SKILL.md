---
name: assets-bot
description: File any asset the user drops in chat (image, video, audio, YouTube link, image URL) into their organized local asset library (~/assets by default) — classified by type, auto-named by content, optionally tagged to a project. Use when the user sends a file or media link with no other instruction, or says "save this", "file this", "add to my assets", "name: <x>", or "project: <x>". The agent-runtime sibling of the standalone Slack bot in this repo.
---

# Assets Bot (skill mode)

Turn any chat with your agent into an asset library inbox. The user drops a file, a YouTube link, or an image URL — you file it into their asset folder, categorized, named so it can be found later by description. **Your curated taste — memes, screenshots, sounds, clips — is what makes your work feel like yours. This keeps it at hand.**

This SKILL.md is runtime-agnostic: it works in **Hermes**, **OpenClaw**, and **Claude Code** (see INSTALL.md for the standalone Slack-bot alternative). Wherever your agent sees your messages — Telegram, Slack, WhatsApp, the terminal — dropping an asset triggers the same filing behavior.

## First run — setup (once)

If no config exists at `~/.assets-bot.env` (also accept an existing `.env` from the standalone bot if the user points at one), ask the user:

1. **Where should assets live?** (default `~/assets`)
2. **Which categories?** Default 4: `screenshots, photos, videos, sounds`. Opt-in extras: `memes, thumbnails, logos`.

Write the answers to `~/.assets-bot.env`:
```
ASSETS_DIR=~/assets
CATEGORIES=screenshots,photos,videos,sounds
AUTO_NAME_IMAGES=true
```
Create the folders. Suggest (macOS): drag the assets folder into Finder's sidebar Favorites so it shows up in every save dialog.

## Filing rules (the spec — match the standalone bot exactly)

### Routing by type
- **Images** → two-step classification:
  1. Filename pre-check: `CleanShot*`, `Screenshot*`, `SCR-*`, etc. → `screenshots/`; names containing `logo`, `wordmark`, `favicon`, `app-icon` → `logos/` (if enabled)
  2. Otherwise LOOK at the image and pick from the enabled image categories (`screenshots/photos/memes/thumbnails/logos`). Fallback: `photos/`.
- **Videos** → `videos/` · **Audio** → `sounds/`
- **YouTube links** → download BOTH: `yt-dlp` the `.mp4` into `videos/` AND extract `.mp3` into `sounds/` (same basename).
- **Other URLs** → fetch headers, route by `Content-Type` (image/video/audio). Plain web pages: ignore, tell the user why.

### Naming
- `name: foo` / `rename: foo` / `save as foo` / `name=foo` in the message → save as `foo.<ext>`. Multiple files in one message: `foo_1`, `foo_2`. YouTube: same name for mp4 + mp3.
- No rename + generic filename (`CleanShot_…`, `Screenshot…`, `IMG_1234`, `Untitled…`) → **look at the image and name it descriptively in 2–5 words**, snake_case: `team_dashboard.png`, `kanye_west_laughing.png`. This is what makes the library agent-searchable later ("use the kanye meme").
- Otherwise keep the original filename. Dedupe with `_1`, `_2` — never overwrite.

### Project tagging
- `project: kanye-launch` (or `project=`) anywhere in the message → file under `<ASSETS_DIR>/projects/kanye-launch/<category>/` instead of the top-level category. Slugify: lowercase, non-alphanumeric → `-`.
- **Smart detection:** a file with a short caption (1–6 words, no URLs, no `name:` directive) → the caption IS the project name. URL-only messages need the explicit `project:` keyword (so "check this out" doesn't create a project).
- Combine freely: `project: kanye-launch name: opening-shot` + video → `projects/kanye-launch/videos/opening-shot.mp4`.

### Reply contract
After filing, confirm with the saved path(s), compactly:
```
✓ ~/assets/screenshots/team_dashboard.png
✓ ~/assets/projects/kanye-launch/videos/opening-shot.mp4 + sounds/opening-shot.mp3
```
If something was skipped (webpage URL, unsupported type), say so in one line.

## Tools needed
- `yt-dlp` + `ffmpeg` on PATH (`brew install yt-dlp ffmpeg`). If missing on first YouTube link, offer to install.
- Your own vision for image classification/naming — no external API needed.

## Taste rules
- **Never overwrite** — dedupe with numeric suffixes.
- **Fast and quiet** — file it, confirm the path, done. No essays.
- **When unsure between categories, prefer the more specific one** the user enabled (a meme goes to `memes/` if enabled, else `photos/`).
- Filing is the default action for a bare dropped file — don't ask "what would you like me to do with this?"
