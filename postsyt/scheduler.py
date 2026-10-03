"""Programare: sloturi orare, quiet hours, jitter, caps, mirror-delays."""
from __future__ import annotations

import random
from datetime import datetime, time as dtime, timedelta
from typing import Optional


def _local_now(cfg) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(cfg.timezone))
    except Exception:
        return datetime.now()


def in_quiet_hours(now: datetime, quiet: list[int]) -> bool:
    if not quiet or len(quiet) < 2:
        return False
    start, end = quiet[0], quiet[1]
    h = now.hour
    if start <= end:
        return start <= h < end
    return h >= start or h < end  # ex 23-7 trece peste miezul nopții


def next_slot(cfg, hours: list[int], after: Optional[datetime] = None,
              jitter_min: int = 20) -> datetime:
    """Următorul slot local din `hours` (cu jitter), după `after`."""
    now = after or _local_now(cfg)
    candidates = []
    for day_off in range(0, 3):
        for h in sorted(set(hours)):
            cand = now.replace(hour=h, minute=0, second=0, microsecond=0) + timedelta(days=day_off)
            cand += timedelta(minutes=random.randint(-jitter_min, jitter_min))
            if cand > now:
                candidates.append(cand)
    return min(candidates) if candidates else now + timedelta(hours=1)


def can_publish_now(store, cfg, now: Optional[datetime] = None) -> tuple[bool, str]:
    """Respectă max/zi, gap minim și quiet hours."""
    now = now or _local_now(cfg)
    if in_quiet_hours(now, cfg.quiet_hours):
        return False, "quiet hours (nu postăm noaptea)"
    if store.published_today() >= cfg.max_posts_per_day:
        return False, f"limita zilnică atinsă ({cfg.max_posts_per_day})"
    last = store.last_publish_time()
    if last:
        gap = (datetime.now(last.tzinfo) - last).total_seconds() / 60
        if gap < cfg.min_gap_minutes:
            return False, f"gap minim {cfg.min_gap_minutes} min (au trecut {int(gap)})"
    return True, "ok"


RO_DAYS = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]


def is_live_day(cfg, now: Optional[datetime] = None) -> bool:
    now = now or _local_now(cfg)
    return RO_DAYS[now.weekday()] in (cfg.live_days or [])
