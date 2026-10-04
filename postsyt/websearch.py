"""Căutare web universală pentru TOȚI agenții — „API-ul tău privat de search".

Lanț de reziliență:
  1. Dacă PC bridge-ul e online → căutarea iese prin PC (IP rezidențial, site-uri
     care blochează datacenterele = accesibile).
  2. Altfel → direct de pe server/hub (nu depindem DOAR de PC).

Orice agent ți-o poate folosi cu UN singur POST /api/bridge/search — vezi
docs/BRIDGE.md și bridge-kit/PROMPT-UNIVERSAL.md.
"""
from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from .util import http_get

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def parse_ddg_results(html: str, limit: int = 8) -> list[dict]:
    """Parser DuckDuckGo HTML — stdlib pur, testabil fără rețea."""
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         html, re.S):
        link, titlu = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "uddg=" in link:  # DDG redirect -> destinația reală
            link = unquote(parse_qs(urlparse(link).query).get("uddg", [link])[0])
        if link.startswith("http"):
            out.append({"titlu": titlu, "url": link})
        if len(out) >= limit:
            break
    return out


def search(q: str, limit: int = 8, hub=None) -> dict:
    """Caută pe web și întoarce rezultate curate.
    {'results': [{'titlu','url'}...], 'via': 'bridge'|'direct'|'niciuna', 'error'?}"""
    q = (q or "").strip()
    if not q:
        return {"results": [], "via": "niciuna", "error": "q gol"}
    limit = max(1, min(int(limit or 8), 20))
    url = "https://html.duckduckgo.com/html/?q=" + quote(q)

    # 1. prin PC bridge, dacă e conectat (nu depindem exclusiv de el)
    try:
        if hub and hub.enabled and any(b["online"] for b in hub.status()):
            res = hub.submit(url, method="GET", headers={"User-Agent": _UA},
                             timeout=40, project="websearch")
            if res.get("status") == 200:
                html = base64.b64decode(res.get("body_b64") or b"").decode("utf-8", "ignore")
                return {"results": parse_ddg_results(html, limit), "via": "bridge"}
    except Exception:
        pass  # cadem pe direct

    # 2. fallback direct de pe server — sistemul merge și fără PC
    try:
        html = http_get(url, headers={"User-Agent": _UA}, timeout=25)
        return {"results": parse_ddg_results(html, limit), "via": "direct"}
    except Exception as e:
        return {"results": [], "via": "niciuna", "error": str(e)[:200]}
