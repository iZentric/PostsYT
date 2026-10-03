"""Trend Scout: youtube.com/gaming/trending + viteza clipurilor competitorilor."""
from __future__ import annotations

from datetime import timezone
from typing import Optional

from .models import Trend
from .util import (extract_yt_initial_data, http_get, parse_relative_time_ro,
                   parse_yt_count, runs_to_text, utcnow, walk_find, deep_get)

GAMING_TRENDING_URL = "https://www.youtube.com/gaming/trending"


def scrape_gaming_trending(limit: int = 25) -> list[Trend]:
    """Extrage videoRenderer-urile din pagina de trending gaming (ytInitialData)."""
    try:
        page = http_get(GAMING_TRENDING_URL)
    except Exception:
        return []
    data = extract_yt_initial_data(page)
    if not data:
        return []
    out: list[Trend] = []
    now = utcnow()
    for vr in walk_find(data, "videoRenderer"):
        if not isinstance(vr, dict):
            continue
        vid = vr.get("videoId")
        if not vid:
            continue
        title = runs_to_text(vr.get("title", {}))
        views = parse_yt_count(runs_to_text(vr.get("viewCountText", {}))) or \
            parse_yt_count(runs_to_text(vr.get("shortViewCountText", {})))
        published_txt = runs_to_text(vr.get("publishedTimeText", {}))
        published = parse_relative_time_ro(published_txt, now)
        age_h = 1.0
        if published:
            age_h = max(1.0, (now - published.astimezone(timezone.utc)).total_seconds() / 3600)
        channel = runs_to_text(deep_get(vr, "ownerText", default={}) or
                               deep_get(vr, "shortBylineText", default={}))
        vph = (views or 0) / age_h
        out.append(Trend(
            source="gaming_trending", channel=channel or "?",
            title=title, url=f"https://www.youtube.com/watch?v={vid}",
            views=views, vph=vph, score=vph, fetched_at=now,
        ))
        if len(out) >= limit:
            break
    return out


def competitor_hot_videos(videos_by_channel: dict[str, list], now=None) -> list[Trend]:
    """Din feedurile competitorilor: calculează viteza (views/oră) și scotocă outliere."""
    now = now or utcnow()
    trends: list[Trend] = []
    for channel_name, videos in videos_by_channel.items():
        for v in videos[:5]:
            age_h = 8.0
            if v.published:
                age_h = max(2.0, (now - v.published.astimezone(timezone.utc)).total_seconds() / 3600)
            vph = (v.views or 0) / age_h
            trends.append(Trend(
                source=f"competitor:{channel_name}",
                channel=channel_name, title=v.title, url=v.url,
                views=v.views, vph=vph, score=vph, fetched_at=now,
            ))
    trends.sort(key=lambda t: t.score, reverse=True)
    return trends


STOPWORDS = {
    "the", "and", "for", "with", "din", "care", "mai", "este", "sunt", "acum",
    "that", "this", "am", "pe", "de", "la", "in", "un", "o", "ce", "sa", "să",
    "si", "și", "cu", "nu", "ca", "că", "sunt", "tot", "cel", "o",
}


def topic_keywords(titles: list[str], top: int = 6) -> list[str]:
    """Cuvinte-cheie fierbinți din titlurile trendate (pentru morphing)."""
    import re
    from collections import Counter
    words: Counter = Counter()
    for t in titles:
        for w in re.findall(r"[A-Za-zĂÂÎȘȚăâîșț0-9]{4,}", t):
            lw = w.lower()
            if lw not in STOPWORDS:
                words[lw] += 1
    return [w for w, _ in words.most_common(top)]
