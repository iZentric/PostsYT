"""Publisher: alege driverul potrivit pentru fiecare draft.

- innertube: postări text/imagine complet automate (recomandat).
- sondaje: Playwright UI (studio_bot) dacă e instalat; altfel fallback inteligent:
  sondajul devine postare cu imagine de sondaj + variantele în text (A/B/C/D),
  votarea se face în comentarii — același mecanism de engagement.
- queue: nu publică nimic, doar lasă în dashboard pentru copy/paste manual.
"""
from __future__ import annotations

from typing import Optional

from .models import Draft, KIND_POLL, STATUS_FAILED, STATUS_PUBLISHED
from .util import utcnow, iso


class PublishResult:
    def __init__(self, ok: bool, post_id: str = "", error: str = "", mode: str = ""):
        self.ok, self.post_id, self.error, self.mode = ok, post_id, error, mode
    def __repr__(self):
        return f"PublishResult(ok={self.ok}, mode={self.mode}, id={self.post_id}, err={self.error[:80]})"


class Publisher:
    def __init__(self, cfg, store, log=print):
        self.cfg, self.store, self.log = cfg, store, log
        self._client = None

    # ------------------------------------------------- innertube
    def _innertube(self):
        if self._client is None:
            from .innertube import InnertubeClient, load_cookies
            cookies = load_cookies(self.cfg.cookies_file, self.cfg.cookies_json)
            self._client = InnertubeClient(cookies, channel_id=self.cfg.own_channel_id)
        return self._client

    # ------------------------------------------------- sondaje
    def _publish_poll(self, d: Draft) -> PublishResult:
        letters = "ABCDE"
        if self.cfg.experimental_innertube_polls:
            try:
                poll = {"choices": [{"text": o} for o in d.poll_options]}
                pid = self._innertube().create_post(d.text, poll=poll)
                return PublishResult(True, post_id=pid, mode="innertube-poll")
            except Exception as e:
                self.log(f"[poll innertube experimental] eșuat: {e} — merg pe fallback")
        try:
            from .studio_bot import publish_poll_via_browser
            pid = publish_poll_via_browser(self.cfg, d)
            if pid:
                return PublishResult(True, post_id=pid, mode="playwright-poll")
        except Exception as e:
            self.log(f"[poll playwright] indisponibil: {e} — fallback imagine+comentarii")
        # Fallback: imagine de sondaj + opțiuni în text, vot prin comentarii
        opts = "\n".join(f"{letters[i]}) {o}" for i, o in enumerate(d.poll_options))
        text = (f"{d.poll_question}\n\n{opts}\n\n"
                f"🗳️ Votează răspunsul tău în comentarii (A/B/C/D) — număr fiecare vot! 🔥"
                + (f"\n➡️ {d.link}" if d.link else ""))
        pid = self._innertube().create_text_or_image_post(text, d.image_path or None)
        return PublishResult(True, post_id=pid, mode="poll-ca-imagine")

    # ------------------------------------------------- main
    def publish(self, draft: Draft) -> PublishResult:
        if self.cfg.publish_driver == "queue":
            return PublishResult(False, error="Modul queue: publicare manuală din dashboard copy/paste.",
                                 mode="queue")
        try:
            if draft.kind == KIND_POLL and draft.poll_question and draft.poll_options:
                res = self._publish_poll(draft)
            else:
                pid = self._innertube().create_text_or_image_post(
                    draft.text, draft.image_path or None)
                res = PublishResult(True, post_id=pid, mode="innertube")
        except Exception as e:
            res = PublishResult(False, error=str(e)[:300], mode="error")
        if res.ok:
            self.store.update_draft(draft.id, status=STATUS_PUBLISHED,
                                    published_at=utcnow(), yt_post_id=res.post_id, error="")
            self.store.log(f"✅ Publicat ({res.mode}): {draft.kind_label()} #{draft.id} — yt post {res.post_id}")
        else:
            self.store.update_draft(draft.id, status=STATUS_FAILED, error=res.error)
            self.store.log(f"❌ Publicare eșuată #{draft.id}: {res.error}", "ERROR")
        return res
