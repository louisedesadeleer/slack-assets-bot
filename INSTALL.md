# Install — pick your runtime

This repo ships **one asset-filing brain, two bodies**:

- **The Slack bot, kept alive by a LaunchAgent** *(default — recommended for everyone)* — a dedicated always-on process on your machine. DM it from your phone, files land on your computer. Survives reboots, crashes, and sleep without you thinking about it.
- **Skill mode** (`SKILL.md`) — for people who already run an agent that lives in their chats (Hermes, OpenClaw, Claude Code). The agent itself files your assets.

> **Agent instructions:** if an agent is reading this because the user said "install this" — **default to option 1 (the Slack bot)** unless the user says they run Hermes/OpenClaw and prefer skill mode. If unsure, ask; don't guess.

---

## 1. The Slack bot + LaunchAgent (DEFAULT)

The reliable path. Two steps:

**a) Create the Slack app** (~5 min, one time): follow the [README setup](./README.md#setup) — create the app from `manifest.yml`, grab the two tokens.

**b) Install + run:**
```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git
cd slack-assets-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python setup.py     # wizard: folder, categories, tokens, allowlist — say YES to the LaunchAgent
```

Saying yes to the LaunchAgent at the end is what makes it **always-on**: it starts now, starts at every login, and restarts itself within seconds if it ever dies. You never think about it again. (How it works: [below](#how-the-launchagent-works).)

Linux: no launchd — run `bot.py` under systemd with `Restart=always`.

## 2. Hermes (skill mode)

Hermes already sees your Telegram/Slack/WhatsApp messages, so the skill is all it needs:

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git /tmp/assets-bot
mkdir -p ~/.hermes/skills/assets-bot
cp /tmp/assets-bot/SKILL.md ~/.hermes/skills/assets-bot/SKILL.md
```

Then tell Hermes: *"read your assets-bot skill and set it up"*. Always-on **if** your Hermes gateway runs 24/7 (VPS etc.) — the skill is exactly as alive as your agent.

## 3. OpenClaw (skill mode)

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git /tmp/assets-bot
mkdir -p ~/.openclaw/skills/assets-bot
cp /tmp/assets-bot/SKILL.md ~/.openclaw/skills/assets-bot/SKILL.md
```

Then message your agent: *"set up the assets-bot skill"*. Same always-on caveat as Hermes.

## 4. Claude Code (skill mode — not an inbox)

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git ~/.claude/skills/assets-bot
```

Claude Code sessions are on-demand, so this is **not** an always-on inbox — it's for filing things you already have locally, and for letting other skills *read* the library. Pair it with option 1.

---

## How the LaunchAgent works

macOS has a built-in process supervisor called **launchd** — the same thing that keeps system services alive. `setup.py` writes one small config file, `~/Library/LaunchAgents/com.assetsbot.plist`, that tells launchd three things:

1. **What to run** — your venv's Python + `bot.py`, from the repo directory
2. **`RunAtLoad`** — start it immediately, and at every login
3. **`KeepAlive`** — if the process exits *for any reason* (crash, killed, Mac woke from sleep and the socket died), relaunch it within seconds

Logs go to `bot.log` in the repo. Pause it: `launchctl unload ~/Library/LaunchAgents/com.assetsbot.plist` · resume: `launchctl load ...` (or re-run `python setup.py`, it's idempotent). No cron, no Docker, no cloud — the OS itself is the babysitter.

## Which one should I pick?

| You… | Pick |
|---|---|
| want "it just always works" (most people) | **1 — Slack bot + LaunchAgent** |
| run Hermes or OpenClaw 24/7 already | **2/3** — zero extra infrastructure |
| live in Claude Code, assets are mostly local | **4**, ideally paired with 1 |
| want both a phone inbox AND an agent that files | **1 + skill mode** — same folder taxonomy, they compose: the bot catches, the agent uses |

## The always-on truth

| Mode | Always-on? | Kept alive by |
|---|---|---|
| **Slack bot + LaunchAgent** (1) | ✅ yes | launchd — starts at login, auto-restarts on crash/sleep/death |
| **Hermes / OpenClaw skill** (2/3) | ✅ *if* your gateway runs 24/7 | the agent's own gateway daemon. Laptop-only gateway that sleeps = inbox that sleeps |
| **Claude Code skill** (4) | ❌ no | nothing — on-demand only, not an inbox |

One known gap in mode 1: Socket Mode doesn't redeliver messages sent while your machine was asleep — they stay in the Slack chat but aren't filed until you resend. (Startup backfill is on the roadmap.)
