"""Slack assets bot.

DM a file or paste a link and it lands in ~/assets/{photos,videos,sounds}/.
YouTube links download both the video (videos/) and the audio (sounds/).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

ASSETS_DIR = Path.home() / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"
SCREENSHOTS_DIR = ASSETS_DIR / "screenshots"
VIDEOS_DIR = ASSETS_DIR / "videos"
SOUNDS_DIR = ASSETS_DIR / "sounds"
for d in (PHOTOS_DIR, SCREENSHOTS_DIR, VIDEOS_DIR, SOUNDS_DIR):
    d.mkdir(parents=True, exist_ok=True)

IMAGE_CATEGORIES = {
    "screenshot": SCREENSHOTS_DIR,
    "photo": PHOTOS_DIR,
}

ALLOWED_SLACK_USERS = {
    u.strip()
    for u in os.environ.get("ALLOWED_SLACK_USERS", "").split(",")
    if u.strip()
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("assets-bot")

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

app = App(token=SLACK_BOT_TOKEN)

YOUTUBE_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?[^\s<>|]+|shorts/[\w-]+)|youtu\.be/[\w-]+)[^\s<>|]*"
)
URL_RE = re.compile(r"https?://[^\s<>|]+")
RENAME_INLINE_RE = re.compile(
    r"(?:save\s+as|rename|name)\s*[:=]\s*([^\n<>|]+?)\s*(?:\n|$)",
    re.IGNORECASE,
)
RENAME_START_RE = re.compile(
    r"^\s*(?:save\s+as|rename|name)\s+([^\n<>|]+?)\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def extract_rename(text: str) -> str | None:
    m = RENAME_INLINE_RE.search(text or "") or RENAME_START_RE.search(text or "")
    if not m:
        return None
    candidate = m.group(1).strip()
    candidate = URL_RE.sub("", candidate).strip()
    if not candidate:
        return None
    return safe_name(candidate)


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_")
    return cleaned or "file"


def unique_path(directory: Path, filename: str) -> Path:
    p = directory / filename
    if not p.exists():
        return p
    stem, ext = p.stem, p.suffix
    i = 1
    while True:
        candidate = directory / f"{stem}_{i}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def route_by_mime(mimetype: str | None) -> Path | None:
    if not mimetype:
        return None
    if mimetype.startswith("image/"):
        return PHOTOS_DIR
    if mimetype.startswith("video/"):
        return VIDEOS_DIR
    if mimetype.startswith("audio/"):
        return SOUNDS_DIR
    return None


SCREENSHOT_NAME_RE = re.compile(
    r"^(cleanshot|screenshot|screen[\s_-]?shot|screencap|scrnshot)",
    re.IGNORECASE,
)


def classify_by_filename(path: Path) -> str | None:
    if SCREENSHOT_NAME_RE.match(path.name):
        return "screenshot"
    return None


def classify_image(path: Path) -> str:
    """Label image as screenshot/photo/thumbnail.

    1. Filename heuristic (fast, free) catches CleanShot/Screenshot prefixes.
    2. Otherwise shell out to the `claude` CLI for vision classification.
    3. Falls back to 'photo' if claude isn't installed or the call fails.
    """
    if label := classify_by_filename(path):
        log.info("classified %s -> %s (filename)", path.name, label)
        return label

    if not shutil.which("claude"):
        log.info("claude CLI not on PATH, defaulting %s -> photo", path.name)
        return "photo"

    prompt = (
        f"Classify the image at {path} as exactly one of these two labels: "
        "screenshot, photo. A screenshot is a capture of a computer or phone "
        "interface. A photo is anything else (a real-world picture, a meme, "
        "a designed image, artwork, a cover image). "
        "Reply with ONLY the single lowercase word, nothing else."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (result.stdout or "").strip().lower().splitlines()
        label = out[-1].strip() if out else ""
        if label in IMAGE_CATEGORIES:
            log.info("classified %s -> %s (claude)", path.name, label)
            return label
        log.warning("classifier returned unexpected output: %r", result.stdout)
    except Exception as e:
        log.error("classifier failed: %s", e)
    return "photo"


def reclassify_if_image(path: Path, mimetype: str | None) -> Path:
    """If path is an image saved to PHOTOS_DIR, classify and move if needed."""
    if not mimetype or not mimetype.startswith("image/"):
        return path
    if path.parent != PHOTOS_DIR:
        return path
    label = classify_image(path)
    target = IMAGE_CATEGORIES[label]
    if target == path.parent:
        return path
    new_path = unique_path(target, path.name)
    path.rename(new_path)
    log.info("moved %s -> %s", path.name, new_path)
    return new_path


def download_slack_file(file_obj: dict, rename: str | None = None) -> Path | None:
    url = file_obj.get("url_private_download") or file_obj.get("url_private")
    if not url:
        return None
    target = route_by_mime(file_obj.get("mimetype"))
    if not target:
        log.info("skipping file, unsupported mimetype: %s", file_obj.get("mimetype"))
        return None
    original = file_obj.get("name") or "file"
    if rename:
        ext = Path(original).suffix
        name = rename + ext if ext and not Path(rename).suffix else rename
    else:
        name = safe_name(original)
    path = unique_path(target, name)
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    log.info("saved slack file -> %s", path)
    path = reclassify_if_image(path, file_obj.get("mimetype"))
    return path


def download_youtube(
    url: str, rename: str | None = None
) -> tuple[Path | None, Path | None]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if rename:
        video_tmpl = str(VIDEOS_DIR / f"{rename}.%(ext)s")
        audio_tmpl = str(SOUNDS_DIR / f"{rename}.%(ext)s")
    else:
        video_tmpl = str(VIDEOS_DIR / f"%(title)s__{stamp}.%(ext)s")
        audio_tmpl = str(SOUNDS_DIR / f"%(title)s__{stamp}.%(ext)s")
    video_proc = subprocess.run(
        [
            "yt-dlp",
            "-f",
            "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/best[vcodec!=none]",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "--print",
            "after_move:filepath",
            "-o",
            video_tmpl,
            url,
        ],
        capture_output=True,
        text=True,
    )
    video_path: Path | None = None
    if video_proc.returncode == 0:
        out = video_proc.stdout.strip().splitlines()
        if out:
            video_path = Path(out[-1])
            log.info("saved youtube video -> %s", video_path)
    else:
        log.error("yt-dlp video failed: %s", video_proc.stderr.strip()[-500:])

    audio_proc = subprocess.run(
        [
            "yt-dlp",
            "-x",
            "--audio-format",
            "mp3",
            "--print",
            "after_move:filepath",
            "-o",
            audio_tmpl,
            url,
        ],
        capture_output=True,
        text=True,
    )
    audio_path: Path | None = None
    if audio_proc.returncode == 0:
        out = audio_proc.stdout.strip().splitlines()
        if out:
            audio_path = Path(out[-1])
            log.info("saved youtube audio -> %s", audio_path)
    else:
        log.error("yt-dlp audio failed: %s", audio_proc.stderr.strip()[-500:])

    return video_path, audio_path


def download_generic_url(url: str, rename: str | None = None) -> Path | None:
    try:
        head = requests.head(url, allow_redirects=True, timeout=15)
        content_type = head.headers.get("Content-Type", "").split(";")[0].strip()
    except Exception as e:
        log.error("HEAD failed for %s: %s", url, e)
        content_type = ""

    target = route_by_mime(content_type)
    if not target:
        guessed, _ = mimetypes.guess_type(url)
        target = route_by_mime(guessed)
    if not target:
        log.info("unknown content type for %s (got %s)", url, content_type)
        return None

    if rename:
        name = rename
    else:
        name = safe_name(Path(urlparse(url).path).name or "download")
    if not Path(name).suffix:
        ext = mimetypes.guess_extension(content_type) if content_type else None
        if not ext:
            ext = Path(urlparse(url).path).suffix
        if ext:
            name += ext
    path = unique_path(target, name)
    r = requests.get(url, stream=True, timeout=300)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    log.info("saved url -> %s", path)
    path = reclassify_if_image(path, content_type)
    return path


def process_message(event: dict, say) -> None:
    text = event.get("text", "") or ""
    files = event.get("files", []) or []
    thread_ts = event.get("ts")
    rename = extract_rename(text)
    saved: list[str] = []
    errors: list[str] = []

    for f in files:
        try:
            p = download_slack_file(f, rename=rename)
            if p:
                saved.append(f"`{p}`")
            else:
                errors.append(f"skipped `{f.get('name')}` (unsupported type)")
        except Exception as e:
            log.exception("file download failed")
            errors.append(f"failed `{f.get('name')}`: {e}")

    yt_urls = list(dict.fromkeys(YOUTUBE_RE.findall(text)))
    for url in yt_urls:
        try:
            v, a = download_youtube(url, rename=rename)
            if v:
                saved.append(f"`{v}`")
            if a:
                saved.append(f"`{a}`")
            if not v and not a:
                errors.append(f"yt-dlp failed for {url}")
        except Exception as e:
            log.exception("youtube failed")
            errors.append(f"youtube error: {e}")

    other_urls = [u for u in URL_RE.findall(text) if u not in yt_urls]
    for url in other_urls:
        try:
            p = download_generic_url(url, rename=rename)
            if p:
                saved.append(f"`{p}`")
            else:
                errors.append(f"skipped {url} (couldn't tell what it is)")
        except Exception as e:
            log.exception("url download failed")
            errors.append(f"failed {url}: {e}")

    if not saved and not errors:
        return

    lines = []
    if saved:
        lines.extend(f"saved {s}" for s in saved)
    if errors:
        lines.extend(f"problem: {e}" for e in errors)
    try:
        say(text="\n".join(lines), thread_ts=thread_ts)
    except Exception:
        log.exception("failed to post reply")


@app.event("message")
def handle_message(event, say):
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return
    if event.get("channel_type") != "im":
        return
    user_id = event.get("user")
    if not user_id:
        return
    if not ALLOWED_SLACK_USERS:
        log.warning(
            "ALLOWED_SLACK_USERS is empty — refusing message from %s. "
            "Set ALLOWED_SLACK_USERS in .env to authorize yourself.",
            user_id,
        )
        say(
            text=(
                f"Hi! This bot is private and doesn't have any authorized "
                f"users yet.\nYour Slack user ID is `{user_id}` — the owner "
                f"can add it to `ALLOWED_SLACK_USERS` in `.env` to authorize "
                f"you, then restart the bot."
            ),
            thread_ts=event.get("ts"),
        )
        return
    if user_id not in ALLOWED_SLACK_USERS:
        log.warning("unauthorized message from %s", user_id)
        say(
            text=(
                f"Hi! This bot is private and not configured to handle "
                f"requests from your account. Your Slack user ID for "
                f"reference: `{user_id}`."
            ),
            thread_ts=event.get("ts"),
        )
        return
    log.info("message from %s in %s", user_id, event.get("channel"))
    threading.Thread(
        target=process_message, args=(event, say), daemon=True
    ).start()


@app.event("file_shared")
def handle_file_shared(event, logger):
    logger.debug("file_shared (handled via message.im): %s", event.get("file_id"))


def main() -> None:
    log.info("assets bot starting, saving to %s", ASSETS_DIR)
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
