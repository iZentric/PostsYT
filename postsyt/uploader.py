"""Upload video YouTube prin fluxul Studio (Scotty) — fără API key/OAuth,
doar cu cookie-urile existente. Același mecanism folosit de studio.youtube.com.

Pași:
  1. POST start  -> upload.youtube.com/upload/studio  (metadate + sesiune)
  2. PUT bucăți  -> X-Goog-Upload-URL (resumable, 308 = confirmare intermediară)
  3. finalize    -> extragem videoId din răspuns (sau anunțăm procesarea)

CLI:  python -m postsyt upload clip.mp4 --title "POKE CITY #5" --privacy unlisted
Implicit PRIVACY=private (sigur); --privacy public doar la cerere explicită.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Callable, Optional

from .innertube import STUDIO_ORIGIN, load_cookies, sapisidhash
from .util import USER_AGENT, HttpError, extract_ytcfg, http_get

UPLOAD_ORIGIN = "https://upload.youtube.com"
START_URL = f"{UPLOAD_ORIGIN}/upload/studio"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB — granularitatea cerută de Google
PRIVACIES = ("PRIVATE", "UNLISTED", "PUBLIC")


class UploadError(Exception):
    def __init__(self, msg: str, etapa: str = ""):
        self.etapa = etapa
        super().__init__(msg)


# ------------------------------------------------------------------ transport
def _default_transport(method: str, url: str, headers: dict, body: bytes,
                       timeout: int = 120) -> tuple[int, dict, str]:
    """(status, headers, text). 308 e status normal în upload resumable."""
    req = urllib.request.Request(url, data=body if method != "GET" else None,
                                 method=method,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), \
                resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (308,):
            return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
        raise HttpError(e.code, url, e.read().decode("utf-8", "replace")) from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"Nu mă pot conecta la {url}: {e.reason}") from e


def _h(headers: dict, name: str) -> str:
    """Header lookup case-insensitive."""
    for k, v in (headers or {}).items():
        if k.lower() == name.lower():
            return v
    return ""


# ------------------------------------------------------------------ payloaduri
def build_start_body(title: str, description: str, privacy: str,
                     tags: list[str]) -> dict:
    """Corpul sesiunii de upload Studio (schema folosită de clientul web)."""
    return {
        "frontendUploadId": f"innertube_studio_{uuid.uuid4().hex[:12]}",
        "deviceProject": "youtube_creator",
        "initialMetadata": {
            "title": title,
            "description": description,
            "privacy": privacy,
            "tags": tags,
            "draftState": {"isDraft": False},
        },
    }


def extract_video_id(resp_text: str) -> Optional[str]:
    for pat in (r'"(?:videoId|encryptedVideoId|documentVideoId)"\s*:\s*"([\w-]{11})"',
                r'"scottyResourceId"\s*:\s*\{[^}]*"([\w-]{11})"'):
        m = re.search(pat, resp_text or "")
        if m:
            return m.group(1)
    return None


def extract_scotty_id(resp_text: str) -> str:
    m = re.search(r'"scottyResourceId"\s*:\s*\{\s*"id"\s*:\s*"([^"]+)"', resp_text or "")
    return m.group(1) if m else ""


# ------------------------------------------------------------------ motor
def upload_video(cfg, file_path: str, *, title: Optional[str] = None,
                 description: str = "", tags: Optional[list] = None,
                 privacy: str = "PRIVATE",
                 transport: Callable = _default_transport,
                 getter: Callable = http_get,
                 log: Callable = print,
                 on_progress: Optional[Callable] = None) -> dict:
    """Urcă fișierul pe canal. Returnează dict {ok, video_id, url, etapa, eroare, debug}."""
    debug: list[str] = []
    res = {"ok": False, "video_id": "", "url": "", "etapa": "validare",
           "eroare": "", "debug_path": ""}
    try:
        # ---- validări
        if not os.path.isfile(file_path):
            raise UploadError(f"Fișierul nu există: {file_path}", "validare")
        size = os.path.getsize(file_path)
        if size == 0:
            raise UploadError("Fișier gol (0 octeți)", "validare")
        privacy = (privacy or "PRIVATE").upper()
        if privacy not in PRIVACIES:
            raise UploadError(f'privacy trebuie să fie unul din {PRIVACIES}, nu "{privacy}"',
                              "validare")
        title = (title or os.path.splitext(os.path.basename(file_path))[0]).strip()[:100]
        tags = [str(t).strip()[:30] for t in (tags or []) if str(t).strip()][:15]
        desc = description[:5000]
        base = os.path.basename(file_path)
        mime = mimetypes.guess_type(base)[0] or "video/mp4"

        # ---- auth
        res["etapa"] = "autentificare"
        cookies = load_cookies(cfg.cookies_file, cfg.cookies_json)
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        client_ver = "1.20251001.01.00"
        try:
            page = getter(STUDIO_ORIGIN, headers={"Cookie": cookie_header})
            cfg_page = extract_ytcfg(page) or {}
            client_ver = cfg_page.get("INNERTUBE_CLIENT_VERSION", client_ver)
            debug.append(f"studio cfg ok, client {client_ver}")
        except Exception as e:  # noqa: BLE001 - nu blocăm uploadul pentru cfg
            debug.append(f"studio cfg eșuat (continui cu default): {str(e)[:120]}")

        auth_headers = {
            "Cookie": cookie_header,
            "Authorization": sapisidhash(cookies, STUDIO_ORIGIN),
            "Origin": STUDIO_ORIGIN,
            "Referer": STUDIO_ORIGIN + "/",
            "X-Origin": STUDIO_ORIGIN,
            "X-Youtube-Client-Name": "62",
            "X-Youtube-Client-Version": client_ver,
            "X-Goog-AuthUser": "0",
        }

        # ---- 1) START
        res["etapa"] = "start"
        start_body = json.dumps(build_start_body(title, desc, privacy, tags)).encode()
        status, rheaders, text = transport(
            "POST", START_URL,
            {**auth_headers,
             "X-Goog-Upload-Command": "start",
             "X-Goog-Upload-File-Name": base,
             "X-Goog-Upload-Header-Content-Length": str(size),
             "X-Goog-Upload-Header-Content-Type": mime,
             "X-Goog-Upload-Protocol": "resumable",
             "Content-Type": "application/json"},
            start_body)
        debug.append(f"start -> {status}; resp: {text[:300]}")
        upload_url = _h(rheaders, "X-Goog-Upload-URL")
        if status not in (200, 201) or not upload_url:
            raise UploadError(
                f"YouTube a respins START-ul uploadului (HTTP {status}): {text[:200]}",
                "start")
        log(f"☁️  Sesiune upload creată — trimit {size / 1024 / 1024:.1f} MB în bucăți de "
            f"{CHUNK_SIZE // 1024 // 1024} MB")

        # ---- 2) CHUNK loop
        res["etapa"] = "bucăți"
        sent = 0
        final_text = ""
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                last = sent + len(chunk) >= size
                cmd = "upload, finalize" if last else "upload"
                status, rheaders, text = transport(
                    "PUT", upload_url,
                    {**auth_headers,
                     "X-Goog-Upload-Command": cmd,
                     "X-Goog-Upload-Offset": str(sent),
                     "Content-Type": "application/octet-stream"},
                    chunk)
                debug.append(f"chunk @{sent} ({len(chunk)}b, {cmd}) -> {status}")
                if status not in (200, 201, 308):
                    raise UploadError(f"Eșec la bucata @{sent} (HTTP {status}): {text[:200]}",
                                      "bucăți")
                sent += len(chunk)
                if on_progress:
                    on_progress(sent, size)
                if last:
                    final_text = text
                    break

        # ---- 3) finalize / video id
        res["etapa"] = "finalize"
        vid = extract_video_id(final_text)
        scotty = extract_scotty_id(final_text)
        debug.append(f"finalize: videoId={vid or '?'} scotty={scotty or '?'} "
                     f"resp: {final_text[:300]}")
        if vid:
            res.update(ok=True, video_id=vid,
                       url=f"https://youtu.be/{vid}", eroare="", etapa="gata")
            log(f"✅ Upload COMPLET: https://youtu.be/{vid}  (privacy: {privacy})")
        else:
            # YouTube uneori nu întoarce id-ul imediat — clipul e la procesare în Studio
            res.update(ok=True, video_id="", url="", etapa="gata-fara-id",
                       eroare="YouTube procesează clipul — apare în câteva minute la "
                              "Studio → Conținut (id-ul nu a venit în răspuns).")
            log("✅ Fișierul a ajuns la YouTube și se procesează. "
                "Îl găsești în Studio → Conținut în câteva minute.")
        return res

    except Exception as e:  # noqa: BLE001
        res["eroare"] = str(e)[:400]
        res["ok"] = False
        debug.append(f"EROARE la etapa {res['etapa']}: {str(e)[:300]}")
        log(f"❌ Upload eșuat ({res['etapa']}): {e}")
        return res
    finally:
        try:
            dbg_path = os.path.join(cfg.data_dir, "upload_debug.log")
            os.makedirs(cfg.data_dir, exist_ok=True)
            with open(dbg_path, "a", encoding="utf-8") as f:
                f.write(f"\n===== upload {os.path.basename(file_path)} =====\n")
                f.write("\n".join(debug) + "\n")
            res["debug_path"] = dbg_path
        except Exception:  # noqa: BLE001
            pass
