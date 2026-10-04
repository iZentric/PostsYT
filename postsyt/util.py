"""Utilitare: HTTP (stdlib), timp, text, JSON brace-balanced extractor."""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------- HTTP layer
class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        self.status = status
        self.url = url
        self.body = body[:500]
        super().__init__(f"HTTP {status} la {url}: {self.body[:200]}")


def http_get(url: str, headers: Optional[dict] = None, timeout: int = 30,
             want_headers: bool = False):
    """want_headers=True -> returneaza (text, headers) cu TOATE liniile Set-Cookie
    păstrate (una pe rând în cheia 'Set-Cookie'), pentru rotația de sesiune."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            text = raw.decode(enc, errors="replace")
            if want_headers:
                hdrs = dict(resp.headers)
                try:
                    sc = resp.headers.get_all("Set-Cookie")
                except Exception:  # noqa: BLE001
                    sc = None
                if sc:
                    hdrs["Set-Cookie"] = "\n".join(sc)
                return text, hdrs
            return text
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, url, e.read().decode("utf-8", errors="replace")) from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"Nu mă pot conecta la {url}: {e.reason}") from e


def http_post(url: str, body: bytes | str | None = None, headers: Optional[dict] = None,
              timeout: int = 30) -> tuple[str, dict]:
    """Returnează (text, headers)."""
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or "utf-8"
            hdrs = dict(resp.headers)
            try:
                sc = resp.headers.get_all("Set-Cookie")
            except Exception:  # noqa: BLE001
                sc = None
            if sc:
                hdrs["Set-Cookie"] = "\n".join(sc)
            return raw.decode(enc, errors="replace"), hdrs
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        raise HttpError(e.code, url, txt) from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"Nu mă pot conecta la {url}: {e.reason}") from e


# ---------------------------------------------------------------- JSON helpers
def extract_balanced_json(text: str, start_idx: int) -> tuple[Optional[dict], int]:
    """Extrage un obiect JSON echilibrat începând cu '{' la/ după start_idx.
    Returnează (obj, end_index)."""
    i = text.find("{", start_idx)
    if i < 0:
        return None, start_idx
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                chunk = text[i:j + 1]
                try:
                    return json.loads(chunk), j + 1
                except json.JSONDecodeError:
                    return None, j + 1
    return None, len(text)


def extract_ytcfg(page: str) -> dict:
    """Merghează toate apelurile ytcfg.set({...}) dintr-o pagină YouTube."""
    merged: dict = {}
    pos = 0
    while True:
        idx = page.find("ytcfg.set(", pos)
        if idx < 0:
            break
        obj, end = extract_balanced_json(page, idx)
        if obj:
            merged.update(obj)
        pos = max(end, idx + 10)
    # uneori configul e în ytcfg.data_ = {...}
    idx = page.find("ytcfg.data_ = ")
    if idx >= 0:
        obj, _ = extract_balanced_json(page, idx)
        if obj:
            merged = {**obj, **merged}
    return merged


def extract_yt_initial_data(page: str) -> Optional[dict]:
    for marker in ("var ytInitialData = ", "ytInitialData = ", "window[\"ytInitialData\"] = "):
        idx = page.find(marker)
        if idx >= 0:
            obj, _ = extract_balanced_json(page, idx + len(marker))
            if obj:
                return obj
    return None


def deep_get(obj: Any, *path: Any, default: Any = None) -> Any:
    cur = obj
    for p in path:
        try:
            if isinstance(cur, dict):
                cur = cur[p]
            elif isinstance(cur, list) and isinstance(p, int):
                cur = cur[p]
            else:
                return default
        except (KeyError, IndexError, TypeError):
            return default
    return cur


def walk_find(obj: Any, key: str) -> list:
    """Găsește recursiv toate valorile unui chei dintr-un JSON."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(walk_find(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(walk_find(item, key))
    return found


def runs_to_text(runs_obj: Any) -> str:
    if isinstance(runs_obj, dict):
        if "simpleText" in runs_obj:
            return str(runs_obj["simpleText"])
        runs = runs_obj.get("runs") or []
        return "".join(str(r.get("text", "")) for r in runs if isinstance(r, dict))
    return ""


# ---------------------------------------------------------------- text utils
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\s#ăâîșțĂÂÎȘȚ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def word_set(text: str) -> set:
    return {w for w in normalize(text).split() if len(w) > 2}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()


def count_emojis(text: str) -> int:
    return sum(1 for ch in text if ord(ch) > 0xFFFF or 0x2600 <= ord(ch) <= 0x27BF)


def human_int(n: Optional[int]) -> str:
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1_000:.1f}K".replace(".0K", "K")
    return str(n)


def parse_yt_count(text: str) -> Optional[int]:
    """Parsare '1.2K', '4,142', '3.5 mil.' -> int (RO/EN mixt)."""
    if not text:
        return None
    t = text.strip().lower().replace("\xa0", " ")
    m = re.match(r"([\d.,]+)\s*(k|m|mil\.?|mld\.?)?", t)
    if not m:
        return None
    num = float(m.group(1).replace(",", ".").replace(" ", ""))
    suf = m.group(2) or ""
    mult = 1
    if suf == "k":
        mult = 1_000
    elif suf in ("m", "mil.", "mil"):
        mult = 1_000_000
    elif suf in ("mld.", "mld"):
        mult = 1_000_000_000
    return int(num * mult)


# ---------------------------------------------------------------- timp
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


RO_MONTHS = {
    "ian": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "iun": 6,
    "iul": 7, "aug": 8, "sept": 9, "oct": 10, "noi": 11, "dec": 12,
}


def parse_relative_time_ro(text: str, ref: Optional[datetime] = None) -> Optional[datetime]:
    """'acum 3 ore', 'acum 2 zile', 'acum 1 săptămână', 'acum 5 minute' (RO/EN)."""
    if not text:
        return None
    ref = ref or utcnow()
    t = normalize(text)
    m = re.search(r"(?:acum|about)\s*(\d+)\s*(minute?|min|ore?|or[ae]|hours?|zi(?:le)?|days?|saptaman\w*|weeks?|lun\w*|months?|ani?|years?)", t)
    if not m:
        if "acum" in t or "hour" in t:
            return ref
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit.startswith(("min",)):
        delta = timedelta(minutes=n)
    elif unit.startswith(("or", "hour")):
        delta = timedelta(hours=n)
    elif unit.startswith(("zi", "day")):
        delta = timedelta(days=n)
    elif unit.startswith(("s", "w")):
        delta = timedelta(weeks=n)
    elif unit.startswith(("l", "month")):
        delta = timedelta(days=30 * n)
    else:
        delta = timedelta(days=365 * n)
    return ref - delta


def jitter(minutes: int) -> timedelta:
    import random
    return timedelta(minutes=random.randint(-minutes, minutes))
