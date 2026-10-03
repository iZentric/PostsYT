"""Client universal pentru PC Bridge — doar stdlib, ~40 de linii, copiabil oriunde.

Orice agent/proiect poate:
  - prin_pc(url, ...): execută cereri HTTP prin PC-ul utilizatorului (IP rezidențial)
  - cauta(termen): căutare DuckDuckGo prin PC -> rezultate structurate pentru statistici

Config: pune SERVER + SECRET (din postsyt-bridge.ini / config.json) mai jos
sau prin variabilele de mediu PCBRIDGE_SERVER / PCBRIDGE_SECRET.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from urllib.parse import parse_qs, quote, unquote, urlparse

SERVER = os.environ.get("PCBRIDGE_SERVER", "http://127.0.0.1:8787")
SECRET = os.environ.get("PCBRIDGE_SECRET", "")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def prin_pc(url: str, method: str = "GET", headers: dict | None = None,
            data: bytes | None = None, timeout: int = 40, project: str = "agent"):
    """Execută cererea pe PC-ul de acasă. Întoarce (body_bytes, status, headers)."""
    payload = json.dumps({
        "secret": SECRET, "url": url, "method": method,
        "headers": headers or {"User-Agent": _UA}, "timeout": timeout,
        "project": project,
        "body_b64": base64.b64encode(data or b"").decode(),
    }).encode()
    req = urllib.request.Request(SERVER + "/api/bridge/request", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 20) as r:
        res = json.loads(r.read())
    if res.get("status", 0) == 0:
        raise ConnectionError(f"PC bridge: {res.get('error', 'indisponibil')}")
    return base64.b64decode(res.get("body_b64") or b""), res["status"], res.get("headers", {})


def extrage_rezultate_ddg(html: bytes, limita: int = 8) -> list[dict]:
    """Parser pentru html.duckduckgo.com — separat ca să fie testabil fără rețea."""
    out = []
    text = html.decode("utf-8", "ignore")
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         text, re.S):
        link, titlu = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "uddg=" in link:  # link-urile DDG sunt redirecte — scoatem destinația reală
            link = unquote(parse_qs(urlparse(link).query).get("uddg", [link])[0])
        if link.startswith("http"):
            out.append({"titlu": titlu, "url": link})
        if len(out) >= limita:
            break
    return out


def cauta(termen: str, rezultate: int = 8) -> list[dict]:
    """Căutare web prin PC-ul de acasă (evită rate-limit-urile de datacenter).
    Întoarce [{'titlu':..., 'url':...}] — de acolo agentul deschide paginile
    tot cu prin_pc() și calculează orice statistici vrea."""
    body, status, _ = prin_pc("https://html.duckduckgo.com/html/?q=" + quote(termen),
                              timeout=30, project="cautari")
    if status != 200:
        raise RuntimeError(f"DuckDuckGo a răspuns {status}")
    return extrage_rezultate_ddg(body, rezultate)


if __name__ == "__main__":
    print("Test bridge:", prin_pc("https://example.com", timeout=20)[1])
    for r in cauta("youtube trending gaming romania", 3):
        print("  •", r["titlu"][:70], "—", r["url"][:70])
