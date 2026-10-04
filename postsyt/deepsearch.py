"""Deep search — nu doar GĂSEȘTE, ci și CITEȘTE paginile găsite.

  1. websearch.search (via bridge când PC-ul e pornit — IP rezidențial, deci site-urile
     care-și bat joc de datacentere se deschid tot)
  2. pentru primele k rezultate: descarcă pagina și extrage textul esențial

API:  POST /api/agent/deepsearch  {"secret": ..., "q": "...", "k": 3}
"""
from __future__ import annotations

import base64
import re
from typing import Callable, Optional

from . import websearch
from .util import http_get

MAX_SNIPPET = 1200


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", html)
    txt = re.sub(r"&nbsp;?", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    txt = re.sub(r"&#39;|&quot;", "'", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _fetch(url: str, hub=None, getter: Callable = http_get) -> str:
    """Pagina prin PC bridge dacă e online (IP rezidențial), altfel direct."""
    if hub is not None:
        try:
            if any(b.get("online") for b in hub.status()):
                res = hub.submit(url, method="GET", headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
                    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
                }, body=b"", timeout=40, project="deepsearch")
                if res.get("status") and 200 <= int(res.get("status", 0)) < 400 \
                        and res.get("body_b64"):
                    return base64.b64decode(res["body_b64"]).decode("utf-8", "replace")
        except Exception:
            pass
    return getter(url, headers={"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}, timeout=40)


def deep_search(q: str, *, k: int = 3, hub=None, getter: Callable = http_get,
                search_limit: int = 8, max_chars: int = MAX_SNIPPET) -> dict:
    q = str(q or "")[:300]
    k = max(1, min(int(k or 3), 6))
    found = websearch.search(q, limit=search_limit, hub=hub)
    results = []
    for item in found.get("results", [])[:k]:
        url = item.get("url", "")
        entry = {"titlu": item.get("titlu", ""), "url": url, "ok": False}
        if url.startswith("http"):
            try:
                text = _strip_html(_fetch(url, hub=hub, getter=getter))
                entry.update(ok=True, continut=text[:max_chars],
                             trunchiat=len(text) > max_chars)
            except Exception as e:  # noqa: BLE001 - o pagină căzută nu oprește restul
                entry["eroare"] = str(e)[:140]
        results.append(entry)
    return {"q": q, "via": found.get("via", "niciuna"), "k": k,
            "rezultate_gasite": len(found.get("results", [])),
            "pagini_citite": results}
