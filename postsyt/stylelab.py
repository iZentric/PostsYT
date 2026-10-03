"""Style Lab: citește postările Community ale competitorilor (fără login).

- extrage exemplare de succes (text, like-uri, comentarii) => exemplare pentru AI
- observă orele de publicare (mirror schedule) — 'la aceeași oră cu el'
- detectează postări noi => trigger pentru postarea noastră (mirror trigger)
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Exemplar
from .util import (extract_yt_initial_data, http_get, parse_relative_time_ro,
                   parse_yt_count, runs_to_text, walk_find, deep_get)


def community_url(handle_or_id: str) -> str:
    if handle_or_id.startswith("UC"):
        return f"https://www.youtube.com/channel/{handle_or_id}/posts"
    if handle_or_id.startswith("http"):
        return handle_or_id.rstrip("/") + "/posts"
    return f"https://www.youtube.com/{handle_or_id}/posts"


def scrape_community_posts(handle_or_id: str, limit: int = 20) -> list[Exemplar]:
    """Parsează ytInitialData din pagina /posts a unui canal."""
    try:
        page = http_get(community_url(handle_or_id))
    except Exception:
        return []
    data = extract_yt_initial_data(page)
    if not data:
        return []
    out: list[Exemplar] = []
    for pr in walk_find(data, "backstagePostRenderer"):
        if not isinstance(pr, dict):
            continue
        text = runs_to_text(pr.get("contentText", {}))
        if not text.strip():
            continue
        post_id = pr.get("postId", "")
        likes = parse_yt_count(runs_to_text(pr.get("voteCount", {}))) or \
            parse_yt_count(deep_get(pr, "actionButtons", "commentActionButtonsRenderer",
                                    "likeButton", "toggleButtonRenderer",
                                    "accessibilityData", "accessibilityData", "label", default="") or "")
        comments = parse_yt_count(runs_to_text(deep_get(
            pr, "actionButtons", "commentActionButtonsRenderer",
            "commentButton", "commentCount", default={})))
        published_guess = parse_relative_time_ro(runs_to_text(pr.get("publishedTimeText", {})))
        out.append(Exemplar(
            source=handle_or_id, text=text.strip(), likes=likes,
            comments=comments, post_id=post_id, published_guess=published_guess,
        ))
        if len(out) >= limit:
            break
    return out


def learn_posting_hours(exemplar_hours: list[int], fallback: list[int]) -> list[int]:
    """Orele preferate din observații; completează cu fallback până la 4 sloturi."""
    if not exemplar_hours:
        return list(fallback)
    from collections import Counter
    top = [h for h, _ in Counter(exemplar_hours).most_common(4)]
    merged = sorted(set(top)) or list(fallback)
    for f in fallback:
        if len(merged) >= 4:
            break
        if f not in merged:
            merged.append(f)
    return sorted(merged)


SCHEDULE_RE = re.compile(r"ora\s+(\d{1,2})[:.](\d{2})", re.IGNORECASE)


def detect_announced_hour(text: str) -> Optional[tuple[int, int]]:
    """'ASTAZI LA ORA 20:00' => (20, 0) — program anunțat în postare."""
    m = SCHEDULE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None
