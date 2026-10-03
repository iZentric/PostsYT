"""Modele de date pentru PostsYT."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# Tipurile de postări (regula de aur: hook + visual + link)
KIND_VIDEO = "A"      # anunț video live/nou
KIND_TREND = "B"      # trend morph de la alți creatori / gaming trending
KIND_POLL = "C"       # sondaj zilnic (engagement maxim)
KIND_MEME = "D"       # meme / imagine amuzantă (stil "Bober")
KIND_QUESTION = "E"   # întrebare pentru comunitate ("Facem episod cu X?")

KIND_LABELS = {
    KIND_VIDEO: "🎬 Anunț video",
    KIND_TREND: "🔥 Trend adaptat",
    KIND_POLL: "📊 Sondaj",
    KIND_MEME: "😂 Meme / imagine",
    KIND_QUESTION: "❓ Întrebare comunitate",
}

STATUS_DRAFT = "draft"
STATUS_APPROVED = "approved"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


@dataclass
class Video:
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    url: str
    published: Optional[datetime] = None
    views: Optional[int] = None
    is_live: bool = False
    is_short: bool = False

    @property
    def thumbnail(self) -> str:
        return f"https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg"


@dataclass
class Trend:
    source: str            # competitor / gaming_trending
    channel: str
    title: str
    url: str
    views: Optional[int] = None
    vph: float = 0.0       # views per hour (viteza)
    score: float = 0.0
    fetched_at: Optional[datetime] = None


@dataclass
class Exemplar:
    """O postare Community de succes a unui competitor (învățăm stilul din ea)."""
    source: str            # canal
    text: str
    likes: Optional[int] = None
    comments: Optional[int] = None
    post_id: str = ""
    published_guess: Optional[datetime] = None


@dataclass
class Draft:
    kind: str
    text: str
    link: str = ""
    poll_question: str = ""
    poll_options: list = field(default_factory=list)
    image_path: str = ""
    video_id: str = ""
    source: str = ""       # de ce a fost generată (trigger)
    id: Optional[int] = None
    status: str = STATUS_DRAFT
    scheduled_for: Optional[datetime] = None
    created_at: Optional[datetime] = None
    error: str = ""

    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)
