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

ASSETS_DIR = Path(
    os.path.expanduser(os.environ.get("ASSETS_DIR", "~/assets"))
).resolve()

ENABLED_CATEGORIES = {
    c.strip().lower()
    for c in os.environ.get(
        "CATEGORIES", "screenshots,photos,videos,sounds"
    ).split(",")
    if c.strip()
}

# Each category maps to a base file type. Image subcategories share the
# image bucket — the classifier picks between whichever are enabled.
CATEGORY_TYPES = {
    "screenshots": "image",
    "photos": "image",
    "memes": "image",
    "thumbnails": "image",
    "videos": "video",
    "sounds": "audio",
}

CATEGORY_DIRS = {c: ASSETS_DIR / c for c in ENABLED_CATEGORIES}
for d in CATEGORY_DIRS.values():
    d.mkdir(parents=True, exist_ok=True)


def image_categories() -> list[str]:
    """Enabled image subcategories, in classifier preference order."""
    order = ["screenshot", "photo", "meme", "thumbnail"]
    return [c for c in order if f"{c}s" in ENABLED_CATEGORIES]


def default_image_dir() -> Path | None:
    """Default folder for images that don't match a specific subcategory."""
    for c in ("photos", "screenshots", "memes", "thumbnails"):
        if c in ENABLED_CATEGORIES:
            return CATEGORY_DIRS[c]
    return None


def category_dir(label: str) -> Path | None:
    """Map a singular label ('screenshot') to its enabled folder."""
    plural = f"{label}s"
    return CATEGORY_DIRS.get(plural)


ALLOWED_SLACK_USERS = {
    u.strip()
    for u in os.environ.get("ALLOWED_SLACK_USERS", "").split(",")
    if u.strip()
}
ALLOW_WORKSPACE = os.environ.get("ALLOW_WORKSPACE", "").lower() in (
    "1",
    "true",
    "yes",
)
AUTO_NAME_IMAGES = os.environ.get("AUTO_NAME_IMAGES", "true").lower() in (
    "1",
    "true",
    "yes",
)

GENERIC_NAME_PREFIXES = (
    "cleanshot",
    "screenshot",
    "screen_shot",
    "screen-shot",
    "screen shot",
    "untitled",
    "image",
    "img_",
    "img-",
    "photo_",
    "photo-",
    "snip",
    "capture",
    "download",
    "unnamed",
)


def is_generic_image_name(name: str) -> bool:
    stem = Path(name).stem.lower()
    return any(stem.startswith(p) for p in GENERIC_NAME_PREFIXES)

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
PROJECT_RE = re.compile(
    r"project\s*[:=]\s*([^\n<>|]+?)\s*(?:\n|$)",
    re.IGNORECASE,
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


def _slugify(value: str) -> str | None:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    return slug or None


def extract_project(text: str) -> str | None:
    """Pick out an explicit `project: foo` directive."""
    m = PROJECT_RE.search(text or "")
    if not m:
        return None
    candidate = m.group(1).strip()
    candidate = URL_RE.sub("", candidate).strip()
    return _slugify(candidate) if candidate else None


def extract_caption_as_project(text: str) -> str | None:
    """Treat a short caption (no keywords, no URLs) as an implicit project name.

    Examples:
      'morning routine video' -> 'morning-routine-video'
      'kanye launch'          -> 'kanye-launch'
      'lol this is so funny'  -> 'lol-this-is-so-funny' (yes, this is a project)
      'check this out https://...'   -> None (URL present)
      'name: foo'                    -> None (rename directive)
      'a long sentence with more than six words is probably commentary' -> None
    """
    if not text:
        return None
    cleaned = URL_RE.sub("", text)
    cleaned = RENAME_INLINE_RE.sub("", cleaned)
    cleaned = RENAME_START_RE.sub("", cleaned)
    cleaned = PROJECT_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    words = cleaned.split()
    if not (1 <= len(words) <= 6):
        return None
    return _slugify(cleaned)


def project_dir(category_dir_path: Path, project: str | None) -> Path:
    """Return the right folder for `category_dir_path`, scoped to `project`.

    Without a project: returns the category dir as-is.
    With a project: returns ASSETS_DIR/projects/<project>/<category>/.
    """
    if not project:
        return category_dir_path
    target = ASSETS_DIR / "projects" / project / category_dir_path.name
    target.mkdir(parents=True, exist_ok=True)
    return target


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
        return default_image_dir()
    if mimetype.startswith("video/"):
        return CATEGORY_DIRS.get("videos")
    if mimetype.startswith("audio/"):
        return CATEGORY_DIRS.get("sounds")
    return None


SCREENSHOT_NAME_RE = re.compile(
    r"^(cleanshot|screenshot|screen[\s_-]?shot|screencap|scrnshot)",
    re.IGNORECASE,
)


CATEGORY_DESCRIPTIONS = {
    "screenshot": "a capture of a computer or phone interface",
    "photo": "a real-world picture or a designed image",
    "meme": "a reaction image, GIF macro, or joke image with text overlay",
    "thumbnail": "a designed cover image for video content (16:9 with overlaid text, faces, bold styling)",
}


def classify_by_filename(path: Path) -> str | None:
    if "screenshots" in ENABLED_CATEGORIES and SCREENSHOT_NAME_RE.match(path.name):
        return "screenshot"
    return None


def classify_image(path: Path) -> str | None:
    """Pick the best enabled image subcategory for `path`.

    1. Filename heuristic (fast, free) catches CleanShot/Screenshot prefixes.
    2. Otherwise shell out to the `claude` CLI for vision classification.
    3. Falls back to the first enabled image category if claude isn't
       installed or the call fails. Returns None if no image category enabled.
    """
    enabled = image_categories()
    if not enabled:
        return None

    if label := classify_by_filename(path):
        log.info("classified %s -> %s (filename)", path.name, label)
        return label

    if len(enabled) == 1:
        return enabled[0]

    if not shutil.which("claude"):
        fallback = "photo" if "photo" in enabled else enabled[0]
        log.info("claude CLI not on PATH, defaulting %s -> %s", path.name, fallback)
        return fallback

    options = ", ".join(enabled)
    definitions = ". ".join(
        f"A {c} is {CATEGORY_DESCRIPTIONS[c]}" for c in enabled
    )
    prompt = (
        f"Classify the image at {path} as exactly one of these labels: "
        f"{options}. {definitions}. "
        "Reply with ONLY the single lowercase word, nothing else."
    )
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--tools",
                "Read",
                "--permission-mode",
                "bypassPermissions",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (result.stdout or "").strip().lower().splitlines()
        label = out[-1].strip() if out else ""
        if label in enabled:
            log.info("classified %s -> %s (claude)", path.name, label)
            return label
        log.warning("classifier returned unexpected output: %r", result.stdout)
    except Exception as e:
        log.error("classifier failed: %s", e)
    return "photo" if "photo" in enabled else enabled[0]


def auto_name_image(path: Path) -> str | None:
    """Ask claude vision for a short descriptive filename slug for an image.

    Returns a slug like 'kanye_west_laughing' or None if claude isn't
    available or the call fails. The slug is sanitized to [a-z0-9_].
    """
    if not shutil.which("claude"):
        return None
    prompt = (
        f"Look at the image at {path} and describe its main subject in 2 to "
        "5 lowercase words separated by underscores. This will be used as a "
        "filename so an AI assistant can find it later by name. Examples: "
        "kanye_west_laughing, drake_pointing, team_dashboard, "
        "iphone_settings_menu, pink_grass_field, distracted_boyfriend_meme. "
        "Reply with ONLY the slug, no extension, no quotes, no other text."
    )
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--tools",
                "Read",
                "--permission-mode",
                "bypassPermissions",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (result.stdout or "").strip().lower().splitlines()
        candidate = out[-1].strip() if out else ""
        slug = re.sub(r"[^a-z0-9_]+", "_", candidate).strip("_")
        if 2 <= len(slug) <= 80 and "_" in slug or 2 <= len(slug) <= 30:
            log.info("auto-named %s -> %s", path.name, slug)
            return slug
        log.warning("auto-name returned unusable slug: %r", candidate)
    except Exception as e:
        log.error("auto-name failed: %s", e)
    return None


def reclassify_if_image(
    path: Path, mimetype: str | None, project: str | None = None
) -> Path:
    """For images: pick the right category folder, optionally rename via claude."""
    if not mimetype or not mimetype.startswith("image/"):
        return path
    label = classify_image(path)
    category_path = category_dir(label) if label else path.parent
    target = project_dir(category_path, project) if category_path else path.parent

    final_name = path.name
    if AUTO_NAME_IMAGES and is_generic_image_name(path.name):
        if slug := auto_name_image(path):
            final_name = slug + path.suffix

    if target == path.parent and final_name == path.name:
        return path
    new_path = unique_path(target or path.parent, final_name)
    path.rename(new_path)
    log.info("placed %s -> %s", path.name, new_path)
    return new_path


def download_slack_file(
    file_obj: dict, rename: str | None = None, project: str | None = None
) -> Path | None:
    url = file_obj.get("url_private_download") or file_obj.get("url_private")
    if not url:
        return None
    target = route_by_mime(file_obj.get("mimetype"))
    if not target:
        log.info("skipping file, unsupported mimetype: %s", file_obj.get("mimetype"))
        return None
    target = project_dir(target, project)
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
    path = reclassify_if_image(path, file_obj.get("mimetype"), project=project)
    return path


def download_youtube(
    url: str, rename: str | None = None, project: str | None = None
) -> tuple[Path | None, Path | None]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    videos_dir = CATEGORY_DIRS.get("videos")
    sounds_dir = CATEGORY_DIRS.get("sounds")
    if videos_dir:
        videos_dir = project_dir(videos_dir, project)
    if sounds_dir:
        sounds_dir = project_dir(sounds_dir, project)

    video_path: Path | None = None
    if videos_dir:
        video_tmpl = str(
            videos_dir / (f"{rename}.%(ext)s" if rename else f"%(title)s__{stamp}.%(ext)s")
        )
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
        if video_proc.returncode == 0:
            out = video_proc.stdout.strip().splitlines()
            if out:
                video_path = Path(out[-1])
                log.info("saved youtube video -> %s", video_path)
        else:
            log.error("yt-dlp video failed: %s", video_proc.stderr.strip()[-500:])

    if not sounds_dir:
        return video_path, None

    audio_tmpl = str(
        sounds_dir / (f"{rename}.%(ext)s" if rename else f"%(title)s__{stamp}.%(ext)s")
    )
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


def download_generic_url(
    url: str, rename: str | None = None, project: str | None = None
) -> Path | None:
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
    target = project_dir(target, project)

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
    path = reclassify_if_image(path, content_type, project=project)
    return path


def process_message(event: dict, say) -> None:
    text = event.get("text", "") or ""
    files = event.get("files", []) or []
    thread_ts = event.get("ts")
    rename = extract_rename(text)
    project = extract_project(text)
    if not project and files:
        project = extract_caption_as_project(text)
    saved: list[str] = []
    errors: list[str] = []

    for f in files:
        try:
            p = download_slack_file(f, rename=rename, project=project)
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
            v, a = download_youtube(url, rename=rename, project=project)
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
            p = download_generic_url(url, rename=rename, project=project)
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
    if not ALLOW_WORKSPACE:
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
