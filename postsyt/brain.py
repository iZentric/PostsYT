"""Brain: generare postări (template-uri offline + LLM opțional OpenAI-compatibil).

Regulile de aur aplicate fiecărui draft:
  1. hook (întrebare/frază amuzantă)
  2. visual (imagine sau sondaj)
  3. link (ultimul video; opțional evergreen secundar)
Anti-plagiat: postările de tip B nu copiază titlul sursei (test Jaccard < 0.45).
"""
from __future__ import annotations

import json
import random
import re
import urllib.request
from typing import Optional

from . import content_banks as bank
from .models import (Draft, KIND_MEME, KIND_POLL, KIND_QUESTION, KIND_RECAP,
                     KIND_SCHEDULE, KIND_TREND, KIND_VIDEO, STATUS_APPROVED, STATUS_DRAFT)
from .util import count_emojis, jaccard, utcnow, word_set

MAX_CHARS = 1200
MAX_CHARS_SHORTS_FEED = 420      # în feed-ul de Shorts postările se trunchiază rapid
MAX_EMOJI = 14
MAX_HOOK_CHARS = 160             # primele 1-2 rânduri = tot ce vede lumea fără „expand"
MAX_POLL_OPTION_CHARS = 45       # vot dintr-o singură privire, ca pe un Short


def _hook_first(text: str, hook: str, max_chars: int = MAX_HOOK_CHARS) -> str:
    """Garantează că postarea ÎNCEPE cu hook-ul (vizualizare Shorts feed)."""
    first_block = text.split("\n", 1)[0]
    if len(first_block) <= max_chars and hook.split("\n")[0][:20] in text[:200]:
        return text
    rest = text[len(first_block):].lstrip("\n") if "\n" in text else ""
    return hook + "\n\n" + (rest or "")


def trim(text: str, limit: int = MAX_CHARS) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    return text[: limit - 1].rstrip() + "…" if len(text) > limit else text


def cap_emojis(text: str, cap: int = MAX_EMOJI) -> str:
    """Taie emoji-urile în exces păstrând textul inteligibil."""
    out, n = [], 0
    for ch in text:
        if ord(ch) > 0xFFFF or 0x2600 <= ord(ch) <= 0x27BF:
            n += 1
            if n > cap:
                continue
        out.append(ch)
    return "".join(out)


# ------------------------------------------------------------------ LLM provider
class LLM:
    """Client minimal OpenAI-compatibil (chat/completions) prin urllib."""

    def __init__(self, base_url: str, api_key: str, model: str, max_chars: int = 900):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_chars = max_chars

    def complete(self, system: str, user: str) -> Optional[str]:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.9,
            "max_tokens": 400,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None


SYSTEM_PROMPT = """Ești copywriter-ul canalului YouTube iSentric (Minecraft / PokeCity, gaming funny, public român 10-18 ani).
Stil: energie mare, propoziții SCURTE, emoji (3-8), întrebări directe, CTA spre comentarii.
NU copia nimic din alte canale. NU inventa linkuri. NU promite clickbait fals (fără minciuni).
Limba: ROMÂNĂ. Lungime: max 900 caractere."""


class Brain:
    """Motorul de generare. Folosește LLM dacă e configurat, altfel template-uri."""

    def __init__(self, cfg, llm: Optional[LLM] = None):
        self.cfg = cfg
        self.llm = llm if (cfg.llm_enabled and llm) else None
        self._used_hooks: list[str] = []

    # ............................................ helpers
    def _pick(self, seq: list, avoid: Optional[list] = None):
        avoid = avoid if avoid is not None else self._used_hooks
        fresh = [x for x in seq if x not in avoid]
        choice = random.choice(fresh or list(seq))
        avoid.append(choice)
        if len(avoid) > 20:
            del avoid[:10]
        return choice

    def _llm_or(self, prompt: str, fallback: str) -> str:
        if self.llm:
            out = self.llm.complete(SYSTEM_PROMPT, prompt)
            if out and len(out) > 20:
                return out
        return fallback

    def _finalize(self, d: Draft) -> Draft:
        d.text = cap_emojis(trim(d.text))
        d.text = re.sub(r"\n{3,}", "\n\n", d.text).strip()
        # linkul mereu la FINAL (în Shorts feed nu împinge conținutul sub fold)
        if d.link and d.link in d.text:
            d.text = d.text.replace(d.link, "").rstrip() + f"\n{d.link}"
        if d.poll_question:
            d.poll_question = trim(d.poll_question, 180)
            d.poll_options = [trim(o, MAX_POLL_OPTION_CHARS) for o in d.poll_options][:5]
        d.created_at = utcnow()
        if self.cfg.autopublish:
            d.status = STATUS_APPROVED
        return d

    # ............................................ Tip A — anunț video
    def gen_video_post(self, video: dict, evergreen: Optional[dict] = None) -> Draft:
        title = video["title"]
        url = video["url"]
        is_live = bool(video.get("is_live"))
        hook = self._pick(bank.LIVE_TEASERS if is_live else bank.HOOKS_VIDEO)
        hook = hook.replace("{hour}", str(self.cfg.live_hour))
        cta = self._pick(bank.CTAS)
        emoji = random.choice(bank.EMOJI_ENERGY)

        fallback = f"{hook}\n\n🎬 {title}\n\n{cta}\n{emoji} {url}"
        if evergreen and random.random() < 0.5:
            fallback += f"\n\n💎 Bonus — clipul nostru cu cele mai multe vizualizări:\n{evergreen['url']}"
        text = self._llm_or(
            f"Scrie o postare Community pentru noul video al canalului. "
            f"Titlu video: «{title}». Link: {url}. Tip: {'live' if is_live else 'video'}. "
            f"Include obligatoriu linkul la final. Fă-o să sune ca canalul iSentric.",
            fallback)
        if url not in text:
            text = text.rstrip() + f"\n🔗 {url}"
        text = _hook_first(text, hook)
        return self._finalize(Draft(
            kind=KIND_VIDEO, text=text, link=url, video_id=video.get("id", ""),
            source="trigger: video nou detectat în RSS"))

    # ............................................ Tip B — trend morph
    def gen_trend_post(self, trend_title: str, trend_channel: str,
                       own_link: str, keywords: Optional[list[str]] = None) -> Draft:
        words = (keywords or []) + [t for t in re.findall(r"[A-Za-zĂÂÎÎȘȚăâîșț0-9]{5,}", trend_title)][:3]
        topic = " / ".join(dict.fromkeys(w.lower() for w in words[:2])) or "ceva tare"
        opener = self._pick(bank.TREND_OPENERS).replace("{topic}", topic)
        bridge = self._pick(bank.TREND_BRIDGES)
        emoji = random.choice(bank.EMOJI_ENERGY)

        fallback = (f"{opener}\n\n{bridge}\n\n"
                    f"Până ne apucăm de treabă — cel mai nou clip de pe canal: {emoji}\n{own_link}")
        text = self._llm_or(
            f"Pe YouTube gaming e acum trend: «{trend_title}» (canal: {trend_channel}). "
            f"Scrie o postare scurtă în stilul iSentric care surfează pe trend FĂRĂ să copieze "
            f"titlul sau ideea textual — adapteaz-o la Minecraft/PokeCity. "
            f"Încheie cu linkul: {own_link}",
            fallback)
        # anti-plagiat: dacă seamnă prea mult cu sursa, trecem pe fallback
        if jaccard(word_set(text), word_set(trend_title)) > 0.45:
            text = fallback
        if own_link not in text:
            text = text.rstrip() + f"\n🔗 {own_link}"
        text = _hook_first(text, opener)
        return self._finalize(Draft(
            kind=KIND_TREND, text=text, link=own_link,
            source=f"trend de la {trend_channel}: {trend_title[:90]}"))

    # ............................................ Tip C — sondaj
    def gen_poll(self, own_link: str = "") -> Draft:
        q, opts = random.choice(bank.POLLS)
        prompt = (f"Creează un sondaj amuzant de max 120 caractere pentru fanii "
                  f"Minecraft/PokeCity cu 3-4 variante de răspuns (fiecare max 60 caractere). "
                  f"Returnează JSON: {{\"question\": \"...\", \"options\": [\"...\",\"...\"]}}")
        if self.llm:
            raw = self.llm.complete(SYSTEM_PROMPT, prompt)
            try:
                data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                if data.get("question") and len(data.get("options", [])) >= 2:
                    q, opts = data["question"], data["options"][:4]
            except Exception:
                pass
        text = q if not own_link else f"{q}\n\n🗳️ Votează sus — și până alegi, vezi cel mai nou clip de pe canal: {own_link}"
        return self._finalize(Draft(
            kind=KIND_POLL, text=text, link=own_link,
            poll_question=q, poll_options=list(opts),
            source="sondaj programat zilnic"))

    # ............................................ Tip D — meme card
    def gen_meme(self, own_link: str = "") -> Draft:
        top, bottom = random.choice(bank.MEMES)
        text = f"{top}\n{bottom}"
        if own_link and random.random() < 0.6:
            text += f"\n\n➡️ Iar dacă vrei râs la maxim, ultimul episod: {own_link}"
        d = Draft(kind=KIND_MEME, text=text, link=own_link if own_link in text else "",
                  source="meme random programat")
        d.image_prompt = (top, bottom)  # folosit de ImageMaker pt card
        return self._finalize(d)

    # ............................................ Tip E — întrebare comunitate
    def gen_question(self, own_link: str) -> Draft:
        q = self._pick(bank.QUESTIONS + bank.PREDICTION_QUESTIONS)
        text = self._llm_or(
            f"Scrie o postare-întrebare pentru comunitatea iSentric în stilul: «{q}». "
            f"Adaugă provocarea de a lăsa răspunsul în comentarii și termină cu linkul {own_link}.",
            f"{q}\n\nZi-mi în comentarii — citesc TOT și cea mai tare idee o pun în episodul următor 👇\n"
            f"➡️ Iar până decidem, cel mai nou clip: {own_link}")
        if own_link not in text:
            text = text.rstrip() + f"\n🔗 {own_link}"
        text = _hook_first(text, q)
        return self._finalize(Draft(
            kind=KIND_QUESTION, text=text, link=own_link,
            source="întrebare comunitate programată"))

    # ............................................ Tip F — recap & mulțumiri (duminică)
    def gen_recap(self, own_link: str = "") -> Draft:
        text = self._llm_or(
            "Scrie o postare de RECAP de duminică pentru canalul iSentric (Minecraft/PokeCity). "
            "Mulțumește comunității pentru săptămâna trecută, amintește un moment amuzant generic "
            "și întreabă care a fost momentul lor preferat. Max 400 caractere.",
            self._pick(bank.RECAPS))
        return self._finalize(Draft(
            kind=KIND_RECAP, text=text, link=own_link,
            source="recap de duminică (formatul cu engagement record la template)"))

    # ............................................ Tip G — program săptămânal (luni)
    def gen_schedule(self, own_link: str = "") -> Draft:
        days = " · ".join(d0.capitalize() for d0 in (self.cfg.live_days or []))
        tpl = self._pick(bank.SCHEDULE_POSTS)
        return self._finalize(Draft(
            kind=KIND_SCHEDULE, text=tpl, link=own_link,
            source=f"anunț program săptămânal (live: {days} {self.cfg.live_hour}:00)"))

    # ............................................. Vot eveniment live (postările leagă de live-uri)
    def gen_event_poll(self, own_link: str = "", day: str = "marți") -> Draft:
        tpl, opts = random.choice(bank.COMMUNITY_VOTES)
        q = tpl.replace("{day}", day)
        text = (f"{q}\n\n🗳️ Votează sus — varianta câștigătoare se joacă CHIAR LA LIVE! "
                f"🔴 Le vezi toate pe canal, live {'/'.join(self.cfg.live_days)} de la {self.cfg.live_hour}:00"
                + (f"\n➡️ {own_link}" if own_link else ""))
        return self._finalize(Draft(
            kind=KIND_POLL, text=text, link=own_link,
            poll_question=q, poll_options=list(opts),
            source=f"vot eveniment live ({day})"))
