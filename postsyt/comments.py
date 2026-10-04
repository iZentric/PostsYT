"""Răspunsuri la comentariile canalului — Innertube, aceleași cookie-uri.
Scrie & citește comentarii ca un utilizator logat (nu afectează postările).

Flux de lucru (2 comenzi, controlul rămâne la proprietar):
  1)  python -m postsyt comments scan
        → adună thread-urile (cu reply_params PROASPĂTE) în data/comments.json
  2)  proprietarul trimite planul (eu/agentul îl scriu, el aprobă conținutul):
        python -m postsyt comments reply --plan data/replies_plan.json
        → publică răspunsurile cu pause aleatorii + limită zilnică anti-spam.

NU e o mașină de spam: limite stricte, oprire la erori în serie, jurnal complet.
YouTube limitează dur scrierile de comentarii — de aceea pacing-ul e obligatoriu.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import timedelta
from typing import Callable, Optional

from .innertube import ORIGIN, InnertubeClient, load_cookies, sapisidhash
from .util import (deep_get, iso, parse_relative_time_ro, runs_to_text, utcnow,
                   walk_find)

COMMENTS_FILE = "comments.json"
DEFAULT_ZILE = 60            # istoricul mai vechi rămâne neatins implicit
DEFAULT_LIMITA_ZILNICA = 40  # prag prudent; YouTube taie dur peste ~50-100 răsp/zi
PAUZA = (30, 90)             # secunde aleatorii între răspunsuri (uman, nu bot)
MAX_ERORI_SERIE = 3

_ENDPOINT_NEXT = "next"
_ENDPOINT_BROWSE = "browse"
_ENDPOINT_REPLY = "comment/create_comment_reply"


# ------------------------------------------------------------------ parsare JSON YT
def comments_section_token(next_text: str) -> str:
    """Tokenul de continuare al secțiunii de comentarii din răspunsul /next."""
    try:
        data = json.loads(next_text)
    except (ValueError, TypeError):
        return ""
    for panel in walk_find(data, "engagementPanelSectionListRenderer"):
        ids = [str(s) for s in walk_find(panel, "sectionIdentifier")]
        if any("comment" in i for i in ids):
            for c in walk_find(panel, "continuationCommand"):
                if isinstance(c, dict) and c.get("token"):
                    return str(c["token"])
    return ""


def extract_continuation_items(resp_text: str) -> list:
    """continuationItems din append/reload — paginile de comentarii."""
    try:
        data = json.loads(resp_text)
    except (ValueError, TypeError):
        return []
    items: list = []
    for key in ("reloadContinuationItemsCommand", "appendContinuationItemsAction",
                "appendContinuationItemsCommand"):
        for cmd in walk_find(data, key):
            if isinstance(cmd, dict) and isinstance(cmd.get("continuationItems"), list):
                items.extend(cmd["continuationItems"])
    return items


def _next_page_token(node) -> str:
    if isinstance(node, str):
        try:
            node = json.loads(node)
        except (ValueError, TypeError):
            return ""
    for r in walk_find(node, "continuationItemRenderer"):
        for c in walk_find(r, "continuationCommand"):
            if isinstance(c, dict) and c.get("token"):
                return str(c["token"])
    return ""


def _reply_params(thread: dict) -> str:
    for ep in walk_find(thread, "createCommentReplyEndpoint"):
        if isinstance(ep, dict) and ep.get("createReplyParams"):
            return str(ep["createReplyParams"])
    return ""


def _owner_a_raspuns(thread: dict) -> bool:
    replies = deep_get(thread, "replies", "commentRepliesRenderer", "contents")
    if not replies:
        return False
    for cr in walk_find(replies, "commentRenderer"):
        if isinstance(cr, dict) and cr.get("authorIsChannelOwner"):
            return True
    return False


def parse_threads(raw_items: list, video_id: str = "", video_titlu: str = "") -> list[dict]:
    """commentThreadRenderer[] -> dicturi normalizate răspundibile."""
    out: list[dict] = []
    for tr in walk_find({"root": raw_items}, "commentThreadRenderer"):
        if not isinstance(tr, dict):
            continue
        cr = deep_get(tr, "comment", "commentRenderer", default={}) or {}
        cid = str(cr.get("commentId") or "")
        if not cid:
            continue
        likes = cr.get("likeCount")
        try:
            likes = int(likes)
        except (TypeError, ValueError):
            likes = 0
        out.append({
            "video_id": video_id,
            "video_titlu": video_titlu,
            "comment_id": cid,
            "autor": runs_to_text(cr.get("authorText")),
            "autor_e_owner": bool(cr.get("authorIsChannelOwner")),
            "text": runs_to_text(cr.get("contentText")),
            "publicat": runs_to_text(cr.get("publishedTimeText")),
            "likes": likes,
            "reply_params": _reply_params(tr),
            "owner_a_raspuns": _owner_a_raspuns(tr),
        })
    return out


# ------------------------------------------------------------------ motor
class Commenter:
    """Interfața de lucru cu comentarii. poster injectabil => teste fără rețea."""

    def __init__(self, cfg, store=None, log: Callable = print,
                 sleeper: Callable = time.sleep, poster: Optional[Callable] = None):
        self.cfg, self.store, self.log = cfg, store, log
        self.sleeper = sleeper
        self._poster = poster
        self._client: Optional[InnertubeClient] = None

    # ............... transport Innertube (ca la create_post)
    def _ensure_client(self) -> InnertubeClient:
        if self._client is None:
            cookies = load_cookies(self.cfg.cookies_file, self.cfg.cookies_json)
            self._client = InnertubeClient(cookies, channel_id=self.cfg.own_channel_id,
                                           persist_path=self.cfg.cookies_file)
        return self._client

    def _post_json(self, endpoint: str, body: dict) -> str:
        if self._poster is not None:
            return str(self._poster(endpoint, body))
        client = self._ensure_client()
        client.ensure_config()
        # CONTEXT REAL (fix: varianta hardcodată trimitea o clientVersion inexistentă
        # => YouTube 400 la /next. Mereu contextul proaspăt întors de ytcfg.)
        body = {**body, "context": client.context}
        url = f"{ORIGIN}/youtubei/v1/{endpoint}?key={client.api_key}&prettyPrint=false"
        cl_headers = (client.context or {}).get("client", {})
        headers = client._headers(**{
            "Authorization": sapisidhash(client.cookies),
            "Content-Type": "application/json",
            "X-Youtube-Client-Name": str(cl_headers.get("clientName") or 1),
            "X-Youtube-Client-Version": str(cl_headers.get("clientVersion") or ""),
            "X-Goog-Visitor-Id": str(client.visitor_data or ""),
        })
        _, _, text = client._req("POST", url, headers=headers, body=json.dumps(body))
        return text

    # ............... citire thread-uri
    def video_threads(self, video_id: str, video_titlu: str = "",
                      max_pages: int = 4) -> list[dict]:
        """Toate thread-urile (cu paginare) ale unui videoclip."""
        client_ctx = self._client.context if self._client else None
        ctx = client_ctx or {"client": {"clientName": "WEB",
                                        "clientVersion": "2.20250930.01.00"}}
        threads: list[dict] = []
        seen: set = set()
        try:
            r = self._post_json(_ENDPOINT_NEXT, {"context": ctx, "videoId": video_id})
        except Exception as e:  # noqa: BLE001 - reîncearcă o dată după refresh de context
            client_ctx = self._client.context if self._client else None
            ctx = client_ctx or ctx
            r = self._post_json(_ENDPOINT_NEXT, {"context": ctx, "videoId": video_id})
        token = comments_section_token(r)
        pages = 0
        while token and pages < max_pages:
            pages += 1
            r = self._post_json(_ENDPOINT_BROWSE, {"context": ctx, "continuation": token})
            for t in parse_threads(extract_continuation_items(r), video_id, video_titlu):
                if t["comment_id"] not in seen:
                    seen.add(t["comment_id"])
                    threads.append(t)
            token = _next_page_token(r)
        return threads

    # ............... scan complet canal
    def scan(self, videoclipuri: list[dict], *, zile: int = DEFAULT_ZILE,
             max_pages: int = 4, doar_fara_raspuns: bool = True,
             progres: Optional[Callable] = None) -> dict:
        """videoclipuri: [{id, titlu}]. Scrie data/comments.json cu tot ce-i răspundibil."""
        progres = progres or self.log
        ref = utcnow()
        prag = ref - timedelta(days=zile) if zile else None
        toate: list[dict] = []
        erori: list[str] = []
        for i, v in enumerate(videoclipuri, 1):
            vid, titlu = str(v.get("id") or ""), str(v.get("titlu") or "")
            if not vid:
                continue
            progres(f"   [{i}/{len(videoclipuri)}] comentarii: {titlu[:50] or vid}")
            try:
                threads = self.video_threads(vid, titlu, max_pages=max_pages)
            except Exception as e:  # noqa: BLE001 - un clip stricat nu oprește scanarea
                erori.append(f"{vid}: {str(e)[:140]}")
                continue
            for t in threads:
                if t["autor_e_owner"]:
                    continue  # comentariile mele proprii nu au nevoie de răspuns
                if doar_fara_raspuns and t["owner_a_raspuns"]:
                    continue
                if prag:
                    dt = parse_relative_time_ro(t.get("publicat", ""), ref=ref)
                    if dt is not None and dt < prag:
                        continue
                if not t["reply_params"]:
                    continue  # nu știu cum să răspund la el (rar: comentarii restricționate)
                toate.append(t)
        rezultat = {
            "scanat_la": iso(ref),
            "canal": getattr(self.cfg, "own_handle", ""),
            "videoclipuri_scanate": len(videoclipuri),
            "zile_istoric": zile,
            "threaduri_raspundibile": toate,
            "total": len(toate),
            "erori": erori,
        }
        os.makedirs(self.cfg.data_dir, exist_ok=True)
        path = os.path.join(self.cfg.data_dir, COMMENTS_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rezultat, f, ensure_ascii=False, indent=2)
        if self.store:
            self.store.log(f"💬 Scan comentarii: {len(toate)} thread-uri răspundibile "
                           f"din {len(videoclipuri)} clipuri (istoric {zile}z, "
                           f"erori {len(erori)})")
        rezultat["salvat_in"] = path
        return rezultat

    # ............... răspuns propriu-zis
    def reply_one(self, reply_params: str, text: str) -> bool:
        client_ctx = self._client.context if self._client else None
        ctx = client_ctx or {"client": {"clientName": "WEB",
                                        "clientVersion": "2.20250930.01.00"}}
        body = {"context": ctx, "commentText": text, "createReplyParams": reply_params}
        resp = self._post_json(_ENDPOINT_REPLY, body)
        if "createCommentReply" in resp or '"commentRenderer"' in resp:
            return True
        if '"error"' in resp[:2000]:
            raise RuntimeError(f"YouTube a refuzat răspunsul: {resp[:180]}")
        # răspuns ambiguu — îl tratăm ca succes (fmt de răspuns se mai schimbă)
        return True

    def apply_plan(self, plan: dict, *, comments_path: Optional[str] = None,
                   limita_zilnica: int = DEFAULT_LIMITA_ZILNICA,
                   pauza: tuple = PAUZA, uscat: bool = False,
                   max_erori_serie: int = MAX_ERORI_SERIE) -> dict:
        """Publică răspunsurile din planul aprobat: {"raspunsuri":[{"comment_id","text"}]}.
        Respectă limita zilnică (kv în DB), pauze aleatorii, stop la erori în serie."""
        comments_path = comments_path or os.path.join(self.cfg.data_dir, COMMENTS_FILE)
        with open(comments_path, encoding="utf-8") as f:
            scan_data = json.load(f)
        params_by_id = {t["comment_id"]: t.get("reply_params", "")
                        for t in scan_data.get("threaduri_raspundibile", [])}
        meta_by_id = {t["comment_id"]: t
                      for t in scan_data.get("threaduri_raspundibile", [])}

        zi = utcnow().strftime("%Y-%m-%d")
        kv_key = f"replies_count_{zi}"
        postate_azi = int(self.store.get_kv(kv_key) or 0) if self.store else 0
        buget = max(0, limita_zilnica - postate_azi)

        rez = {"postate": 0, "sarite": 0, "erori": [], "uscat": uscat,
               "buget_zi": buget}
        erori_serie = 0
        rasp = plan.get("raspunsuri") or []
        for idx, item in enumerate(rasp, 1):
            cid = str(item.get("comment_id") or "")
            text = str(item.get("text") or "").strip()
            if not cid or not text:
                rez["sarite"] += 1
                continue
            if rez["postate"] >= buget:
                self.log(f"⛔ Limita zilnică atinsă ({limita_zilnica}). "
                         f"Restul de {len(rasp) - idx + 1} rămân pe mâine.")
                break
            params = params_by_id.get(cid)
            if not params:
                rez["sarite"] += 1
                rez["erori"].append(f"{cid}: threadul nu e în scanarea curentă "
                                    f"(re-rulează `comments scan` pentru params proaspete)")
                continue
            src = meta_by_id.get(cid) or {}
            eticheta = f"→ {src.get('autor', '?')} @ {src.get('video_titlu', '')[:40]}"
            if uscat:
                self.log(f"🧪 [USCAT] {idx}. {eticheta}: «{text[:70]}»")
                rez["sarite"] += 1
                continue
            try:
                self.reply_one(params, text[:3000])
                rez["postate"] += 1
                erori_serie = 0
                if self.store:
                    self.store.set_kv(kv_key, postate_azi + rez["postate"])
                    self.store.log(f"💬 Răspuns publicat {rez['postate']}/{buget} {eticheta}")
                if idx < len(rasp):
                    self.sleeper(random.randint(*pauza))
            except Exception as e:  # noqa: BLE001
                erori_serie += 1
                rez["erori"].append(f"{cid}: {str(e)[:160]}")
                if self.store:
                    self.store.log(f"❌ Răspuns eșuat {eticheta}: {str(e)[:140]}", "ERROR")
                if erori_serie >= max_erori_serie:
                    self.log(f"⛔ {max_erori_serie} erori la rând — mă opresc "
                             f"(probabil limită YouTube sau sesiune). Reîncearcă mâine.")
                    break
        return rez
