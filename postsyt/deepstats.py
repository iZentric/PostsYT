"""Deep stats — analiza completă a fiecărui clip al canalului, "până la ultima chestie":

  • metadate: titlu, descriere completă, taguri, durată, dată publicare, likes
  • TRANSCRIPTUL video (caption track / auto-ASR, preferă română)
  • TOP comentarii (sortate după likes) — ce întreabă / zice comunitatea

Totul prin Innertube + paginile publice (watch), cu aceleași cookie-uri.
CLI:   python -m postsyt deepstats [--limita 8] [--fara-transcript]
API:   POST /api/agent/deepstats  {"secret": ..., "limit": 8}
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Callable, Optional

from .innertube import ORIGIN, load_cookies
from .util import (deep_get, extract_balanced_json, http_get, iso, utcnow,
                   walk_find)

MAX_TRANSCRIPT_CHARS = 6000   # destul pentru strategie, fără să sufoce agentul
UAGET = {"Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}


# ------------------------------------------------------------------ player response
def extract_player_response(page: str) -> dict:
    for marker in ("var ytInitialPlayerResponse = ", "ytInitialPlayerResponse = "):
        idx = page.find(marker)
        if idx >= 0:
            obj, _ = extract_balanced_json(page, idx + len(marker))
            if obj:
                return obj
    return {}


def parse_player_details(player: dict) -> dict:
    vd = player.get("videoDetails") or {}
    mf = deep_get(player, "microformat", "playerMicroformatRenderer", default={}) or {}
    likes = None
    for lv in walk_find(player, "likeCount"):
        s = str(lv).replace(",", "").replace(".", "")
        if s.isdigit():
            likes = int(s)
            break
    return {
        "titlu": vd.get("title", ""),
        "descriere": vd.get("shortDescription", ""),
        "taguri": vd.get("keywords") or [],
        "durata_secunde": int(vd["lengthSeconds"]) if str(vd.get("lengthSeconds", "")).isdigit() else None,
        "publicat": mf.get("publishDate") or mf.get("uploadDate") or "",
        "likes": likes,
        "categorie": mf.get("category", ""),
        "este_live": bool(vd.get("isLiveContent")),
    }


# ------------------------------------------------------------------ transcript
def _caption_tracks(player: dict) -> list:
    tracks = deep_get(player, "captions", "playerCaptionsTracklistRenderer",
                      "captionTracks", default=[]) or []
    return [t for t in tracks if isinstance(t, dict) and t.get("baseUrl")]


def get_transcript(player: dict, *, getter: Callable = http_get,
                   max_chars: int = MAX_TRANSCRIPT_CHARS) -> Optional[dict]:
    """textul vorbit în clip. Preferă RO, apoi EN, apoi orice; auto-ASR e marcat."""
    tracks = _caption_tracks(player)
    if not tracks:
        return None

    def rank(t):
        lang = str(t.get("languageCode") or "").lower()
        manual = not (t.get("kind") == "asr")
        if lang.startswith("ro"):
            return (0 if manual else 1)
        if lang.startswith("en"):
            return (2 if manual else 3)
        return 4 if manual else 5

    track = sorted(tracks, key=rank)[0]
    url = re.sub(r"\\u0026", "&", str(track["baseUrl"]))
    try:
        xml_text = getter(url, headers=UAGET, timeout=30)
    except Exception:
        # unele trackuri cer fmt=json3
        try:
            xml_text = getter(url + ("&" if "?" in url else "?") + "fmt=srv3",
                              headers=UAGET, timeout=30)
        except Exception:
            return None
    bucati: list[str] = []
    try:
        root = ET.fromstring(xml_text)
        for node in root.iter("text"):
            if node.text:
                bucati.append(node.text.strip())
    except ET.ParseError:
        # fallback: poate e json3
        try:
            data = json.loads(xml_text)
            for ev in data.get("events", []):
                for seg in ev.get("segs", []) or []:
                    if seg.get("utf8"):
                        bucati.append(seg["utf8"].strip())
        except (ValueError, AttributeError):
            return None
    text = " ".join(b for b in bucati if b)
    if not text:
        return None
    return {
        "limba": track.get("languageCode", "?"),
        "automat": bool(track.get("kind") == "asr"),
        "text": text[:max_chars],
        "trunchiat": len(text) > max_chars,
        "caractere_totale": len(text),
    }


# ------------------------------------------------------------------ scan adânc
def depth_scan(cfg, videoclipuri: list, *, want_transcripts: bool = True,
               top_comentarii: int = 5, progres: Optional[Callable] = print,
               getter: Callable = http_get, commenter=None) -> dict:
    """videoclipuri: [{id, titlu}]. Scrie data/deepstats_latest.json."""
    progres = progres or (lambda *a, **k: None)
    cookies = load_cookies(cfg.cookies_file, cfg.cookies_json)
    headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()), **UAGET}
    out: list[dict] = []
    erori: list[str] = []
    if commenter is None:
        from .comments import Commenter
        commenter = Commenter(cfg, log=lambda *a, **k: None)
    for i, v in enumerate(videoclipuri, 1):
        vid = str(v.get("id") or "")
        if not vid:
            continue
        progres(f"   🔬 [{i}/{len(videoclipuri)}] {str(v.get('titlu') or vid)[:50]}")
        entry: dict = {"id": vid, "titlu_scan": v.get("titlu", "")}
        try:
            page = getter(f"{ORIGIN}/watch?v={vid}", headers=headers, timeout=40)
            player = extract_player_response(page)
            entry.update(parse_player_details(player))
            entry["url"] = f"https://youtu.be/{vid}"
            if want_transcripts:
                entry["transcript"] = get_transcript(player, getter=getter)
            else:
                entry["transcript"] = None
            try:
                threads = commenter.video_threads(vid, entry.get("titlu", ""), max_pages=1)
                cele_mai = sorted(threads, key=lambda t: -t.get("likes", 0))[:top_comentarii]
                entry["comentarii_total_prima_pagina"] = len(threads)
                entry["top_comentarii"] = [
                    {"autor": t["autor"], "text": t["text"][:300], "likes": t["likes"],
                     "intrebare": "?" in t["text"]} for t in cele_mai]
            except Exception as e:  # noqa: BLE001 - clipul fără comentarii nu blochează
                entry["top_comentarii"] = []
                entry["comentarii_nota"] = str(e)[:120]
        except Exception as e:  # noqa: BLE001
            erori.append(f"{vid}: {str(e)[:140]}")
            entry["eroare"] = str(e)[:200]
        out.append(entry)
    intrebari = sum(1 for v in out for c in (v.get("top_comentarii") or []) if c.get("intrebare"))
    rez = {
        "scanat_la": iso(utcnow()),
        "canal": getattr(cfg, "own_handle", ""),
        "videoclipuri": out,
        "total": len(out),
        "cu_transcript": sum(1 for v in out if v.get("transcript")),
        "intebari_in_top_comentarii": intrebari,
        "erori": erori,
    }
    os.makedirs(cfg.data_dir, exist_ok=True)
    path = os.path.join(cfg.data_dir, "deepstats_latest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rez, f, ensure_ascii=False, indent=2)
    rez["salvat_in"] = path
    return rez


def format_summary(rez: dict) -> str:
    lines = [f"🔬 DEEP STATS {rez.get('canal', '')} — {rez['total']} clipuri disecate"]
    for v in rez.get("videoclipuri", []):
        dur = v.get("durata_secunde")
        dur_s = f"{dur // 60}:{dur % 60:02d}" if dur else "?"
        tr = v.get("transcript")
        lines.append(f"\n🎬 {v.get('titlu', '?')[:80]}")
        lines.append(f"   {v.get('publicat', '?')} · {dur_s} · "
                     f"likes {v.get('likes') if v.get('likes') is not None else '?'} · "
                     f"transcript {'✅ ' + tr['limba'] if tr else '❌'}")
        if v.get("taguri"):
            lines.append(f"   taguri: {', '.join(v['taguri'][:8])}")
        for c in (v.get("top_comentarii") or [])[:3]:
            q = " ❓" if c.get("intrebare") else ""
            lines.append(f"   💬 [{c['likes']}👍]{q} {c['autor'][:18]}: {c['text'][:70]}")
    if rez.get("erori"):
        lines.append("\n⚠️ " + " | ".join(rez["erori"]))
    lines.append(f"\n   📊 {rez.get('cu_transcript', 0)}/{rez['total']} cu transcript · "
                 f"❓ {rez.get('intebari_in_top_comentarii', 0)} întrebări din comunitate "
                 f"(idei de episoade viitoare!)")
    return "\n".join(lines)
