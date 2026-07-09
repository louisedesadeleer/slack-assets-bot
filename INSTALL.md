# Install — pick your runtime

This repo ships **one asset-filing brain, two bodies**:

- **Skill mode** (`SKILL.md`) — for people who already run an agent that lives in their chats. The agent itself files your assets; no bot process, no Slack app, no tokens.
- **Standalone Slack bot** (`bot.py`) — a dedicated Python bot for people who don't run an agent. Full setup in the [README](./README.md#setup).

> **Agent instructions:** if an agent is reading this because the user said "install this" — ASK THE USER which option they want (1–4 below), then execute that section. Don't guess.

---

## 1. Hermes

Hermes already sees your Telegram/Slack/WhatsApp messages, so the skill is all you need:

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git /tmp/assets-bot
mkdir -p ~/.hermes/skills/assets-bot
cp /tmp/assets-bot/SKILL.md ~/.hermes/skills/assets-bot/SKILL.md
```

Then tell Hermes: *"read your assets-bot skill and set it up"* — it'll ask for your folder + categories (first-run setup in the skill). From then on, any file you drop in any connected chat gets filed.

## 2. OpenClaw

Same deal — OpenClaw's gateway sits in your DMs already:

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git /tmp/assets-bot
mkdir -p ~/.openclaw/skills/assets-bot
cp /tmp/assets-bot/SKILL.md ~/.openclaw/skills/assets-bot/SKILL.md
```

Then message your agent: *"set up the assets-bot skill"*.

## 3. Claude Code

```bash
git clone https://github.com/louisedesadeleer/slack-assets-bot.git ~/.claude/skills/assets-bot
```

Then in any session: drop a file path / YouTube link and say "file this", or run the first-time setup with *"set up assets-bot"*. (No chat inbox here — this mode shines for filing things you already have locally, and for letting other skills *read* the library.)

## 4. Standalone Slack bot (no agent required)

The original: a dedicated Slack app + always-on Python process on your machine. DM it files/links from anywhere — phone included — and they land on your computer.

Follow the [README setup](./README.md#setup): create the Slack app from `manifest.yml`, then `python setup.py` (wizard: folder, categories, tokens, allowlist, optional LaunchAgent so it survives reboots).

---

## Which one should I pick?

| You… | Pick |
|---|---|
| run Hermes or OpenClaw already | **Skill mode** (1/2) — zero extra infrastructure |
| live in Claude Code, assets are mostly local | **Claude Code skill** (3) |
| don't run any agent / want phone → laptop drops without an agent in the loop | **Standalone bot** (4) |
| want both: agent files things AND a phone inbox | 1/2 **and** 4 — they share the same folder taxonomy, so they compose |
