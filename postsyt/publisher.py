"""Publisher: alege driverul potrivit pentru fiecare draft.

- innertube: postări text/imagine complet automate (recomandat).
  Dacă e configurat PC Bridge-ul (bridge_secret) și PC-ul e online, publicarea
  iese prin PC-ul utilizatorului (IP rezidențial, aceleași cookie-uri) — vezi
  docs/BRIDGE.md. Altfel publică direct de pe mașina agentului.
- sondaje: Playwright UI (studio_bot) dacă e instalat; altfel fallback inteligent:
  sondajul devine postare cu imagine de sondaj + variantele în text (A/B/C/D),
  votarea se face în comentarii — același mecanism de engagement.
- queue: nu publică nimic, doar lasă în dashboard pentru copy/paste manual.
"""
from __future__ import annotations

from .models import Draft, KIND_POLL, STATUS_FAILED, STATUS_PUBLISHED
from .util import utcnow


class PublishResult:
    def __init__(self, ok: bool, post_id: str = "", error: str = "", mode: str = ""):
        self.ok, self.post_id, self.error, self.mode = ok, post_id, error, mode
    def __repr__(self):
        return f"PublishResult(ok={self.ok}, mode={self.mode}, id={self.post_id}, err={self.error[:80]})"


class _T:  # draft minimal pentru fallback-ul de sondaj
    def __init__(self, text, image_path):
        self.text, self.image_path = text, image_path


class Publisher:
    def __init__(self, cfg, store, log=print):
        self.cfg, self.store, self.log = cfg, store, log
        self.hub = None                     # BridgeHub, setat de Agent
        self._client = None                 # client direct (server/PC local)
        self._client_bridge = None          # client prin PC bridge

    def set_hub(self, hub) -> None:
        self.hub = hub

    # ------------------------------------------------- innertube
    def _bridge_online(self) -> bool:
        return bool(self.hub and self.hub.enabled
                    and getattr(self.cfg, "publish_via_bridge", True)
                    and any(b["online"] for b in self.hub.status()))

    def _innertube(self, allow_bridge: bool = True):
        """Returnează (client, tag). Tag "+bridge" când iese prin PC-ul de acasă."""
        from .innertube import InnertubeClient, load_cookies
        if (allow_bridge and getattr(self.cfg, "bridge_only", False)
                and self.hub and self.hub.enabled and not self._bridge_online()):
            raise RuntimeError(
                "bridge_only activ: PC-ul e oprit, deci NU public de pe IP de datacenter. "
                "Publicarea se reia singură când revine bridge-ul (sau setezi bridge_only "
                "pe false în config.json).")
        if allow_bridge and self._bridge_online():
            if self._client_bridge is None:
                cookies = load_cookies(self.cfg.cookies_file, self.cfg.cookies_json)
                self._client_bridge = InnertubeClient(
                    cookies, channel_id=self.cfg.own_channel_id,
                    transport=self.hub.make_transport())
                self.log("🌉 Publicarea iese prin PC bridge (IP-ul tău de acasă)")
            return self._client_bridge, "+bridge"
        if self._client is None:
            cookies = load_cookies(self.cfg.cookies_file, self.cfg.cookies_json)
            self._client = InnertubeClient(cookies, channel_id=self.cfg.own_channel_id)
        return self._client, ""

    def _post_text(self, text: str, image_path: str | None, base_mode: str):
        """Un singur drum pt text/imagine: bridge dacă e online, fallback direct."""
        try:
            client, tag = self._innertube()
            pid = client.create_text_or_image_post(text, image_path)
            return PublishResult(True, post_id=pid, mode=f"{base_mode}{tag}")
        except ConnectionError as e:
            # bridge-ul a picat fix la publicare -> încercăm direct, nu pierdem postarea
            self.log(f"🌉 PC bridge picat ({e}) — reîncerc direct de pe server")
            self._client_bridge = None
            client, _ = self._innertube(allow_bridge=False)
            pid = client.create_text_or_image_post(text, image_path)
            return PublishResult(True, post_id=pid, mode=f"{base_mode} (fallback direct)")

    # ------------------------------------------------- sondaje
    def _publish_poll(self, d: Draft) -> PublishResult:
        letters = "ABCDE"
        if self.cfg.experimental_innertube_polls:
            try:
                client, tag = self._innertube()
                poll = {"choices": [{"text": o} for o in d.poll_options]}
                pid = client.create_post(d.text, poll=poll)
                return PublishResult(True, post_id=pid, mode=f"innertube-poll{tag}")
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
        res = self._post_text(text, d.image_path or None, "poll-ca-imagine")
        return res

    # ------------------------------------------------- main
    def publish(self, draft: Draft) -> PublishResult:
        if self.cfg.publish_driver == "queue":
            return PublishResult(False, error="Modul queue: publicare manuală din dashboard copy/paste.",
                                 mode="queue")
        try:
            if draft.kind == KIND_POLL and draft.poll_question and draft.poll_options:
                res = self._publish_poll(draft)
            else:
                res = self._post_text(draft.text, draft.image_path or None, "innertube")
        except Exception as e:
            res = PublishResult(False, error=str(e)[:300], mode="error")
        if res.ok:
            self.store.update_draft(draft.id, status=STATUS_PUBLISHED,
                                    published_at=utcnow(), yt_post_id=res.post_id, error="")
            self.store.log(f"✅ Publicat ({res.mode}): {draft.kind_label()} #{draft.id} — yt post {res.post_id}")
        elif self.cfg.publish_driver != "queue":
            self.store.update_draft(draft.id, status=STATUS_FAILED, error=res.error)
            self.store.log(f"❌ Publicare eșuată #{draft.id}: {res.error}", "ERROR")
        return res
