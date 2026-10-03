"""Stocare SQLite: videoclipuri văzute, drafturi, trenduri, exemplare, evenimente."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from .models import (Draft, Exemplar, STATUS_DRAFT, Video, Trend)
from .util import iso, parse_iso, utcnow, text_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    channel_id TEXT, channel_title TEXT, title TEXT, url TEXT,
    published TEXT, views INTEGER, is_live INTEGER, is_short INTEGER,
    first_seen TEXT, announced INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT, status TEXT, text TEXT, link TEXT,
    poll_question TEXT, poll_options TEXT, image_path TEXT, video_id TEXT,
    source TEXT, scheduled_for TEXT, created_at TEXT, published_at TEXT,
    yt_post_id TEXT, error TEXT, text_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE TABLE IF NOT EXISTS exemplars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, post_id TEXT, text TEXT, likes INTEGER, comments INTEGER,
    published_guess TEXT, first_seen TEXT,
    UNIQUE(source, post_id)
);
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, channel TEXT, title TEXT, url TEXT, views INTEGER,
    vph REAL, score REAL, fetched_at TEXT, title_hash TEXT,
    UNIQUE(title_hash)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, msg TEXT
);
"""


class Store:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------------- kv
    def get_kv(self, key: str, default=None):
        row = self.conn.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return json.loads(row["v"]) if row else default

    def set_kv(self, key: str, value) -> None:
        self.conn.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                          (key, json.dumps(value, ensure_ascii=False)))
        self.conn.commit()

    # ---------------- evenimente / log
    def log(self, msg: str, level: str = "INFO") -> None:
        self.conn.execute("INSERT INTO events(ts,level,msg) VALUES(?,?,?)",
                          (iso(utcnow()), level, msg))
        self.conn.commit()

    def recent_events(self, limit: int = 40) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts,level,msg FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---------------- videoclipuri
    def add_video(self, v: Video) -> bool:
        """Return True dacă e nou (nu exista)."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO videos
               (id,channel_id,channel_title,title,url,published,views,is_live,is_short,first_seen,announced)
               VALUES(?,?,?,?,?,?,?,?,?,?,0)""",
            (v.video_id, v.channel_id, v.channel_title, v.title, v.url,
             iso(v.published) if v.published else None, v.views,
             int(v.is_live), int(v.is_short), iso(utcnow())))
        self.conn.commit()
        return cur.rowcount > 0

    def update_views(self, video_id: str, views: Optional[int]) -> None:
        if views is not None:
            self.conn.execute("UPDATE videos SET views=? WHERE id=?", (views, video_id))
            self.conn.commit()

    def mark_announced(self, video_id: str) -> None:
        self.conn.execute("UPDATE videos SET announced=1 WHERE id=?", (video_id,))
        self.conn.commit()

    def unannounced_videos(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM videos WHERE announced=0 ORDER BY published DESC").fetchall()
        return [dict(r) for r in rows]

    def latest_video(self, own_only: bool = True, exclude_lives: bool = False) -> Optional[dict]:
        q = "SELECT * FROM videos"
        conds, args = [], []
        if exclude_lives:
            conds.append("is_live=0")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY published DESC LIMIT 1"
        row = self.conn.execute(q, args).fetchone()
        return dict(row) if row else None

    def best_evergreen_video(self) -> Optional[dict]:
        """Video vechi cu potențial: cele mai multe vizualizări, minim 2 zile vechime."""
        cutoff = iso(utcnow() - timedelta(days=2))
        row = self.conn.execute(
            """SELECT * FROM videos WHERE views IS NOT NULL AND published < ?
               ORDER BY views DESC LIMIT 1""", (cutoff,)).fetchone()
        return dict(row) if row else None

    def count_videos(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM videos").fetchone()["c"]

    # ---------------- drafturi
    def add_draft(self, d: Draft) -> Optional[int]:
        h = text_hash((d.poll_question or "") + " " + d.text)
        # dedupe: același text în ultimele 48h
        recent = self.conn.execute(
            """SELECT id FROM drafts WHERE text_hash=? AND created_at > ?""",
            (h, iso(utcnow() - timedelta(hours=48)))).fetchone()
        if recent:
            return None
        cur = self.conn.execute(
            """INSERT INTO drafts(kind,status,text,link,poll_question,poll_options,image_path,
                                  video_id,source,scheduled_for,created_at,text_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.kind, d.status, d.text, d.link, d.poll_question,
             json.dumps(d.poll_options, ensure_ascii=False), d.image_path, d.video_id,
             d.source, iso(d.scheduled_for) if d.scheduled_for else None,
             iso(d.created_at or utcnow()), h))
        self.conn.commit()
        return cur.lastrowid

    def update_draft(self, draft_id: int, **fields) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            if k == "poll_options":
                v = json.dumps(v, ensure_ascii=False)
            if k in ("scheduled_for", "created_at", "published_at") and isinstance(v, datetime):
                v = iso(v)
            cols.append(f"{k}=?")
            vals.append(v)
        vals.append(draft_id)
        self.conn.execute(f"UPDATE drafts SET {', '.join(cols)} WHERE id=?", vals)
        self.conn.commit()

    def get_draft(self, draft_id: int) -> Optional[Draft]:
        row = self.conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return self._row_to_draft(row) if row else None

    def drafts(self, status: Optional[str] = None, limit: int = 50) -> list[Draft]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM drafts WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM drafts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_draft(r) for r in rows]

    def due_approved(self, now: Optional[datetime] = None) -> list[Draft]:
        now = now or utcnow()
        rows = self.conn.execute(
            """SELECT * FROM drafts WHERE status='approved'
               AND (scheduled_for IS NULL OR scheduled_for <= ?) ORDER BY id""",
            (iso(now),)).fetchall()
        return [self._row_to_draft(r) for r in rows]

    def published_today(self) -> int:
        today = iso(utcnow())[:10]
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM drafts WHERE status='published' AND published_at LIKE ?",
            (today + "%",)).fetchone()
        return row["c"]

    def last_publish_time(self) -> Optional[datetime]:
        row = self.conn.execute(
            "SELECT published_at FROM drafts WHERE status='published' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return parse_iso(row["published_at"]) if row and row["published_at"] else None

    def published_of_kind_today(self, kind: str) -> int:
        today = iso(utcnow())[:10]
        return self.conn.execute(
            """SELECT COUNT(*) c FROM drafts WHERE kind=? AND status='published'
               AND published_at LIKE ?""", (kind, today + "%")).fetchone()["c"]

    def _row_to_draft(self, r: sqlite3.Row) -> Draft:
        return Draft(
            id=r["id"], kind=r["kind"], status=r["status"], text=r["text"],
            link=r["link"] or "", poll_question=r["poll_question"] or "",
            poll_options=json.loads(r["poll_options"] or "[]"),
            image_path=r["image_path"] or "", video_id=r["video_id"] or "",
            source=r["source"] or "",
            scheduled_for=parse_iso(r["scheduled_for"]),
            created_at=parse_iso(r["created_at"]),
            error=r["error"] or "",
        )

    # ---------------- exemplare competitori (stil)
    def add_exemplar(self, e: Exemplar) -> bool:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO exemplars
               (source,post_id,text,likes,comments,published_guess,first_seen)
               VALUES(?,?,?,?,?,?,?)""",
            (e.source, e.post_id or text_hash(e.text)[:12], e.text, e.likes,
             e.comments, iso(e.published_guess) if e.published_guess else None,
             iso(utcnow())))
        self.conn.commit()
        return cur.rowcount > 0

    def top_exemplars(self, limit: int = 12) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM exemplars ORDER BY (COALESCE(likes,0) + COALESCE(comments,0)*3) DESC
               LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def exemplar_hours(self, source: str) -> list[int]:
        """Orele la care au fost observate postările competitorului (aprox)."""
        rows = self.conn.execute(
            """SELECT published_guess, first_seen FROM exemplars WHERE source=?""",
            (source,)).fetchall()
        hours = []
        for r in rows:
            dt = parse_iso(r["published_guess"]) or parse_iso(r["first_seen"])
            if dt:
                hours.append(dt.hour)
        return hours

    # ---------------- trenduri
    def add_trend(self, t: Trend) -> bool:
        h = text_hash(t.title)
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO trends(source,channel,title,url,views,vph,score,fetched_at,title_hash)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (t.source, t.channel, t.title, t.url, t.views, t.vph, t.score,
             iso(t.fetched_at or utcnow()), h))
        if cur.rowcount == 0:
            # update viteza dacă există
            self.conn.execute(
                "UPDATE trends SET views=?, vph=?, score=?, fetched_at=? WHERE title_hash=?",
                (t.views, t.vph, t.score, iso(t.fetched_at or utcnow()), h))
        self.conn.commit()
        return cur.rowcount > 0

    def top_trends(self, limit: int = 15) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trends ORDER BY score DESC, fetched_at DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]
