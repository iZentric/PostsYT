"""Agent — orchestrația completă PostsYT.

Pipeline (la fiecare tick):
  1. Scanare feed propriu -> video nou        -> Draft A (imagine card cu titlul)
  2. Scanare /posts competitor mirror         -> postare nouă la el -> Draft E/C la +delay
  3. Scanare feeduri + trending gaming        -> trenduri -> Draft B (morphing, dacă e fierbinte)
  4. Sondaj zilnic la orele configurate       -> Draft C (+ card sondaj)
  5. Meme/întrebare la sloturile de seară     -> Draft D/E
  6. Tiză pre-live în zilele de live          -> Draft A (ora live-ului)
  7. Publicare approved dacă caps permit
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from .brain import Brain, LLM
from .models import (Draft, Exemplar, KIND_MEME, KIND_POLL, KIND_QUESTION, KIND_RECAP,
                     KIND_SCHEDULE, KIND_TREND, KIND_VIDEO, STATUS_APPROVED, STATUS_DRAFT, Video)
from .scheduler import RO_DAYS
from .imagemaker import ImageMaker
from . import feeds as feedmod
from . import stylelab, trends as trendmod
from .scheduler import _local_now, can_publish_now, is_live_day, next_slot


class Agent:
    def __init__(self, cfg, store, log=print):
        self.cfg, self.store, self.log = cfg, store, log
        self.brain = Brain(cfg, self._make_llm())
        self.images = ImageMaker(cfg.images_dir)
        from .bridge_hub import BridgeHub
        from .publisher import Publisher
        self.hub = BridgeHub(getattr(cfg, "bridge_secret", ""))
        self.publisher = Publisher(cfg, store, log=log)
        self.publisher.set_hub(self.hub)

    def _make_llm(self) -> Optional[LLM]:
        import os
        key = os.environ.get(self.cfg.llm_api_key_env, "")
        if self.cfg.llm_enabled and key:
            return LLM(self.cfg.llm_base_url, key, self.cfg.llm_model,
                       self.cfg.llm_max_chars)
        return None

    # ------------------------------------------------------------ helpers
    def _own_link(self) -> str:
        v = self.store.latest_video()
        if v:
            return v["url"]
        return f"https://www.youtube.com/{self.cfg.own_handle}"

    def _save_draft(self, d: Draft, image_kind: str = "", seed: int = 0) -> Optional[int]:
        """Atașează o imagine (dacă n-are) și salvează în DB."""
        try:
            if not d.image_path:
                first_line = (d.poll_question or d.text).split("\n")[0][:120]
                if d.kind == KIND_POLL:
                    d.image_path = self.images.for_poll(d.poll_question, d.poll_options, seed)
                elif d.kind == KIND_MEME and hasattr(d, "image_prompt"):
                    top, bottom = d.image_prompt
                    d.image_path = self.images.for_meme(top, bottom, seed)
                elif d.kind == KIND_QUESTION:
                    d.image_path = self.images.for_question(first_line, seed)
                elif d.kind == KIND_RECAP:
                    d.image_path = self.images.for_recap(first_line, seed)
                elif d.kind == KIND_SCHEDULE:
                    d.image_path = self.images.for_schedule(first_line, seed)
                elif d.kind == KIND_TREND:
                    d.image_path = self.images.for_trend(first_line, seed)
                else:
                    d.image_path = self.images.for_video(first_line, seed)
            did = self.store.add_draft(d)
            if did:
                self.store.log(f"📝 Draft {d.kind_label()} #{did} creat ({d.source[:60]})")
            return did
        except Exception as e:
            self.store.log(f"Eroare la crearea draftului: {e}", "ERROR")
            return None

    def publish_due(self) -> int:
        """Publică ce e aprobat și scadent, cu caps. Returnează câte s-au publicat."""
        ok, reason = can_publish_now(self.store, self.cfg)
        published = 0
        for d in self.store.due_approved():
            if not ok:
                self.store.log(f"⏸️  Amânat #{d.id}: {reason}")
                break
            res = self.publisher.publish(d)
            published += int(res.ok)
            ok, reason = can_publish_now(self.store, self.cfg)
            if not ok and published:
                break
        return published

    # ------------------------------------------------------------ 1. feed propriu
    def scan_own_feed(self) -> int:
        new_count = 0
        try:
            videos = feedmod.fetch_feed(self.cfg.own_channel_id)
        except Exception as e:
            self.store.log(f"Feed propriu indisponibil: {e}", "WARN")
            return 0
        for v in videos:
            is_new = self.store.add_video(v)
            if v.views is not None:
                self.store.update_views(v.video_id, v.views)
            if is_new:
                new_count += 1
        # anunțăm cele neanunțate (și noul, și "primul video" la prima rulare)
        now = _local_now(self.cfg)
        self._boost_outliers()
        for row in self.store.unannounced_videos():
            if self.store.published_of_kind_today(KIND_VIDEO) >= 2:
                break
            pub = row.get("published")
            v = Video(video_id=row["id"], channel_id=row["channel_id"],
                      channel_title=row["channel_title"], title=row["title"],
                      url=row["url"], is_live=bool(row["is_live"]))
            evergreen = self.store.best_evergreen_video()
            d = self.brain.gen_video_post({**row, "is_live": row["is_live"], "url": v.url},
                                          evergreen=evergreen)
            d.scheduled_for = None  # ASAP
            did = self._save_draft(d, "video", seed=hash(row["id"]) % 9999)
            self.store.mark_announced(row["id"])
            if did and self.cfg.autopublish:
                self.store.update_draft(did, status=STATUS_APPROVED)
        return new_count

    def _boost_outliers(self) -> None:
        """Clip care performează peste medie => boost de postare (succesul se amplifică)."""
        rows = [dict(v) for v in self.store.conn.execute(
            "SELECT * FROM videos WHERE views IS NOT NULL AND channel_id=?",
            (self.cfg.own_channel_id,)).fetchall()]
        if len(rows) < 3:
            return
        views = sorted(r["views"] or 0 for r in rows)
        median = views[len(views) // 2] or 1
        recent = sorted(rows, key=lambda r: r.get("published") or "", reverse=True)[:3]
        import statistics
        for r in recent:
            if (r["views"] or 0) >= max(median * 2.5, 1000) and not self.store.get_kv("boosted:" + r["id"]):
                d = self.brain.gen_video_post(
                    {**r, "url": r["url"], "is_live": 0},
                    evergreen=None)
                d.text = ("🚀 Clipul ăsta URCĂ cel mai tare din ultima vreme!\n\n"
                          + d.text)
                d.source = f"outlier detectat: {r['views']} viz (medie canal ~{int(median)})"
                did = self._save_draft(d, "boost", seed=hash(r["id"]) % 9999)
                if did:
                    self.store.set_kv("boosted:" + r["id"], 1)
                    self.store.log(f"🚀 Outlier: «{r['title'][:50]}» are {r['views']} viz — îl impingem cu o postare")

    # ------------------------------------------------------------ 2. mirror trigger
    def scan_mirror_posts(self) -> int:
        """Urmărește /posts-ul template-ului (Jocuri Horror). Postare nouă la el => planificăm una."""
        mirror = self.cfg.mirror_channel
        if not mirror:
            return 0
        now = _local_now(self.cfg)
        fresh = 0
        try:
            posts = stylelab.scrape_community_posts(mirror)
        except Exception as e:
            self.store.log(f"Nu pot citi /posts de la {mirror}: {e}", "WARN")
            return 0
        for p in posts:
            is_new = self.store.add_exemplar(p)
            if not is_new:
                continue
            fresh += 1
        if fresh:
            self.store.log(f"🔎 {fresh} postări noi la {mirror} — planific replicile noastre")
            # planificăm o postare E/C la delay-ul configurat, dacă nu există deja ceva aprobat
            pending = self.store.drafts(status=STATUS_DRAFT) + self.store.drafts(status=STATUS_APPROVED)
            if len(pending) < self.cfg.max_posts_per_day:
                when = now + timedelta(minutes=self.cfg.mirror_delay_minutes) + timedelta(minutes=random.randint(-10, 10))
                kind = random.choice([KIND_QUESTION, KIND_POLL, KIND_MEME])
                gen = {KIND_QUESTION: self.brain.gen_question,
                       KIND_POLL: lambda link: self.brain.gen_poll(link),
                       KIND_MEME: lambda link: self.brain.gen_meme(link)}[kind]
                d = gen(self._own_link())
                d.scheduled_for = when.astimezone(timezone.utc)
                d.source = f"mirror trigger: postare nouă la {mirror}"
                did = self._save_draft(d, seed=random.randint(0, 9999))
                if did and self.cfg.autopublish:
                    self.store.update_draft(did, status=STATUS_APPROVED)
        return fresh

    def learn_schedule(self) -> list[int]:
        """Orele de aur învățate din postările template-ului."""
        hours = self.store.exemplar_hours(self.cfg.mirror_channel)
        learned = stylelab.learn_posting_hours(hours, self.cfg.daytime_slots)
        self.store.set_kv("learned_hours", learned)
        return learned

    # ------------------------------------------------------------ 3. trenduri
    def scan_trends(self) -> int:
        now = _local_now(self.cfg)
        total = 0
        # 3a. gaming trending
        if self.cfg.watch_gaming_trending:
            for t in trendmod.scrape_gaming_trending():
                self.store.add_trend(t)
                total += 1
        # 3b. clipurile fierbinți ale competitorilor (din feedurile lor)
        hot_inputs: dict[str, list] = {}
        for handle in self.cfg.competitors[:20]:
            try:
                cid = feedmod.resolve_handle(handle) or handle
                vids = feedmod.fetch_feed(cid)
                hot_inputs[handle] = vids[:5]
            except Exception:
                continue
        for t in trendmod.competitor_hot_videos(hot_inputs, now=now):
            self.store.add_trend(t)
        # generăm B din cel mai fierbinte trend neprocesat (max 1/zi)
        if self.store.published_of_kind_today(KIND_TREND) < 1:
            top = self.store.top_trends(limit=5)
            if top:
                t = top[0]
                if (t.get("score") or 0) > 0 and not self._already_morphed(t["title"]):
                    kws = trendmod.topic_keywords([x["title"] for x in top])
                    d = self.brain.gen_trend_post(
                        t["title"], t.get("channel") or "?", self._own_link(), keywords=kws)
                    d.scheduled_for = next_slot(self.cfg, [now.hour + 1]).astimezone(timezone.utc)
                    did = self._save_draft(d, "trend", seed=random.randint(0, 9999))
                    if did:
                        self.store.set_kv("morphed:" + t["title"][:40], 1)
                        if self.cfg.autopublish:
                            self.store.update_draft(did, status=STATUS_APPROVED)
        return total

    def _already_morphed(self, title: str) -> bool:
        return bool(self.store.get_kv("morphed:" + title[:40]))

    # ------------------------------------------------------------ 4-6. program zilnic
    def plan_daily(self) -> int:
        now = _local_now(self.cfg)
        planned = 0
        link = self._own_link()

        pending = self.store.drafts(status=STATUS_DRAFT) + self.store.drafts(status=STATUS_APPROVED)
        pending_poll = any(d.kind == KIND_POLL for d in pending)
        if not pending_poll and self.store.published_of_kind_today(KIND_POLL) < 1:
            d = self.brain.gen_poll(link)
            d.scheduled_for = next_slot(self.cfg, self.cfg.poll_hours).astimezone(timezone.utc)
            did = self._save_draft(d, "poll", seed=random.randint(0, 9999))
            planned += int(bool(did))
            if did and self.cfg.autopublish:
                self.store.update_draft(did, status=STATUS_APPROVED)

        pending_fun = any(d.kind in (KIND_MEME, KIND_QUESTION) for d in pending)
        if not pending_fun and self.store.published_of_kind_today(KIND_MEME) < 1 \
                and self.store.published_of_kind_today(KIND_QUESTION) < 1:
            kind = random.choice([KIND_MEME, KIND_QUESTION])
            d = (self.brain.gen_meme(link) if kind == KIND_MEME
                 else self.brain.gen_question(link))
            d.scheduled_for = next_slot(self.cfg, self.cfg.meme_hours).astimezone(timezone.utc)
            did = self._save_draft(d, "fun", seed=random.randint(0, 9999))
            planned += int(bool(did))
            if did and self.cfg.autopublish:
                self.store.update_draft(did, status=STATUS_APPROVED)

        today_ro = RO_DAYS[now.weekday()]

        # F — recap de duminică (formatul #1 al template-ului: "Va MULTUMESC MULT..." )
        if today_ro == "duminică":
            did = self._save_draft(self.brain.gen_recap(link), "recap", seed=random.randint(0, 9999))
            if did:
                planned += 1
                self.store.update_draft(did, scheduled_for=next_slot(self.cfg, [17]).astimezone(timezone.utc))
                if self.cfg.autopublish:
                    self.store.update_draft(did, status=STATUS_APPROVED)

        # G — anunț de program luni (antrenează audiența: exact mutarea lui JocHorror cu 6.9K likes)
        if today_ro == "luni":
            did = self._save_draft(self.brain.gen_schedule(link), "schedule", seed=random.randint(0, 9999))
            if did:
                planned += 1
                self.store.update_draft(did, scheduled_for=next_slot(self.cfg, [12]).astimezone(timezone.utc))
                if self.cfg.autopublish:
                    self.store.update_draft(did, status=STATUS_APPROVED)

        # vot eveniment cu o zi înainte de live (comunitatea DECIDE ce jucăm → feed warming + retenție live)
        tomorrow_ro = RO_DAYS[(now.weekday() + 1) % 7]
        if tomorrow_ro in (self.cfg.live_days or []) and self.store.published_of_kind_today(KIND_POLL) < 2:
            d = self.brain.gen_event_poll(link, day=tomorrow_ro)
            d.scheduled_for = next_slot(self.cfg, [self.cfg.live_hour - 1]).astimezone(timezone.utc)
            did = self._save_draft(d, "event-poll", seed=random.randint(0, 9999))
            if did:
                planned += 1
                if self.cfg.autopublish:
                    self.store.update_draft(did, status=STATUS_APPROVED)

        # teaser live în zilele de live (cu ~75 min înainte)
        if is_live_day(self.cfg, now):
            teaser_hour = max(0, self.cfg.live_hour - 1)
            d = self.brain.gen_video_post({
                "title": f"LIVE azi de la ora {self.cfg.live_hour}:00 — PokeCity cu {', '.join(self.cfg.collab_names)}🔴",
                "url": link, "id": "", "is_live": True})
            d.scheduled_for = now.replace(hour=teaser_hour, minute=45, second=0, microsecond=0)
            if d.scheduled_for <= now:
                d.scheduled_for = now + timedelta(minutes=30)
            d.scheduled_for = d.scheduled_for.astimezone(timezone.utc)
            did = self._save_draft(d, "live-teaser", seed=random.randint(0, 9999))
            planned += int(bool(did))
            if did and self.cfg.autopublish:
                self.store.update_draft(did, status=STATUS_APPROVED)
        return planned

    # ------------------------------------------------------------ tick complet
    def tick(self, quick: bool = False) -> dict:
        report = {"feeds": 0, "mirror": 0, "trends": 0, "planned": 0, "published": 0}
        self.store.log("── tick agent ──")
        report["feeds"] = self.scan_own_feed()
        if not quick:
            report["mirror"] = self.scan_mirror_posts()
            report["trends"] = self.scan_trends()
        report["planned"] = self.plan_daily()
        report["published"] = self.publish_due()
        return report

    def force_generate(self, kind: str) -> Optional[int]:
        """Generare la cerere (dashboard)."""
        seed = random.randint(0, 9999)
        link = self._own_link()
        try:
            if kind == KIND_VIDEO:
                v = self.store.latest_video()
                if not v:
                    return None
                d = self.brain.gen_video_post(v, self.store.best_evergreen_video())
                return self._save_draft(d, "video", seed)
            if kind == KIND_POLL:
                return self._save_draft(self.brain.gen_poll(link), "poll", seed)
            if kind == KIND_MEME:
                return self._save_draft(self.brain.gen_meme(link), "meme", seed)
            if kind == KIND_QUESTION:
                return self._save_draft(self.brain.gen_question(link), "question", seed)
            if kind == KIND_RECAP:
                return self._save_draft(self.brain.gen_recap(link), "recap", seed)
            if kind == KIND_SCHEDULE:
                return self._save_draft(self.brain.gen_schedule(link), "schedule", seed)
            if kind == KIND_TREND:
                top = self.store.top_trends(limit=5)
                if top:
                    kws = trendmod.topic_keywords([x["title"] for x in top])
                    return self._save_draft(
                        self.brain.gen_trend_post(top[0]["title"], top[0].get("channel", "?"),
                                                  link, keywords=kws), "trend", seed)
        except Exception as e:
            self.store.log(f"force_generate {kind} eșuat: {e}", "ERROR")
        return None
