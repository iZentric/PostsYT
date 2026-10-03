"""RSS/Atom feeds YouTube + rezolvare handle -> channelId. Doar stdlib."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from .models import Video
from .util import http_get, parse_iso, extract_ytcfg

ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def parse_feed(xml_text: str) -> list[Video]:
    """Parsează feedul Atom YouTube (stdlib ElementTree)."""
    videos: list[Video] = []
    root = ET.fromstring(xml_text)
    for entry in root.findall(f"{ATOM}entry"):
        vid = entry.findtext(f"{YT}videoId") or ""
        cid = entry.findtext(f"{YT}channelId") or ""
        title = entry.findtext(f"{ATOM}title") or ""
        author = entry.find(f"{ATOM}author")
        author_name = author.findtext(f"{ATOM}name") if author is not None else ""
        published = parse_iso(entry.findtext(f"{ATOM}published") or "")
        # vizualizări din media:community/media:statistics
        views = None
        stats = entry.find(f"{MEDIA}group/{MEDIA}community/{MEDIA}statistics")
        if stats is not None and stats.get("views"):
            try:
                views = int(stats.get("views"))
            except ValueError:
                views = None
        low = title.lower()
        is_short = "#shorts" in low or " #short" in low
        is_live = title.strip().startswith("🔴") or " live" in low or "transmis" in low
        videos.append(Video(
            video_id=vid, channel_id=cid, channel_title=author_name or "",
            title=title.strip(), url=f"https://www.youtube.com/watch?v={vid}",
            published=published, views=views, is_live=is_live, is_short=is_short,
        ))
    return videos


def fetch_feed(channel_id: str) -> list[Video]:
    return parse_feed(http_get(feed_url(channel_id)))


def resolve_handle(handle: str) -> Optional[str]:
    """@nume -> UCxxxxxxxxxxxxx citind pagina canalului."""
    handle = handle.strip()
    if handle.startswith("UC") and len(handle) == 24:
        return handle
    url = handle if handle.startswith("http") else f"https://www.youtube.com/{handle}"
    try:
        page = http_get(url)
    except Exception:
        return None
    m = re.search(r'"externalId"\s*:\s*"(UC[\w-]{22})"', page)
    if m:
        return m.group(1)
    m = re.search(r'<link rel="canonical" href="/channel/(UC[\w-]{22})"', page)
    if m:
        return m.group(1)
    m = re.search(r'channel/(UC[\w-]{22})', page)
    return m.group(1) if m else None


def resolve_handles(handles: list[str]) -> dict[str, Optional[str]]:
    return {h: resolve_handle(h) for h in handles}
