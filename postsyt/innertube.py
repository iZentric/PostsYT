"""InnerTube publisher — postări YouTube Community fără API oficial.

Metodă verificată în proiecte reale (FS Poster plugin, extensia ReClip):
  1. GET youtube.com -> ytcfg (INNERTUBE_API_KEY, INNERTUBE_CONTEXT, DELEGATED_SESSION_ID)
  2. GET youtube.com/channel/<UC>/community -> "createBackstagePostParams"
  3. (imagini) POST channel_image_upload/posts -> upload URL -> bytes -> encryptedBlobId
  4. POST /youtubei/v1/backstage/create_post cu header Authorization: SAPISIDHASH ts_sha1

Cookie-uri: export Netscape (cookies.txt) sau JSON [{name,value,domain}].
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import time
from typing import Optional

from .util import HttpError, extract_ytcfg, http_get, http_post

ORIGIN = "https://www.youtube.com"
STUDIO_ORIGIN = "https://studio.youtube.com"


class AuthError(Exception):
    pass


class InnertubeError(Exception):
    pass


def _sapisid_from_cookies(cookies: dict) -> tuple[str, str]:
    """Returnează (prefix, valoare): SAPISID > __Secure-3PAPISID > __Secure-1PAPISID."""
    if cookies.get("SAPISID"):
        return "SAPISIDHASH", cookies["SAPISID"]
    if cookies.get("__Secure-3PAPISID"):
        return "SAPISID3PHASH", cookies["__Secure-3PAPISID"]
    if cookies.get("__Secure-1PAPISID"):
        return "SAPISID1PHASH", cookies["__Secure-1PAPISID"]
    raise AuthError("Nu am găsit cookie SAPISID/__Secure-*PAPISID — ai exportat cookies după login?")


def sapisidhash(cookies: dict, origin: str = ORIGIN) -> str:
    prefix, sid = _sapisid_from_cookies(cookies)
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sid} {origin}".encode()).hexdigest()
    return f"{prefix} {ts}_{digest}"


# ------------------------------------------------------------------ cookie loaders
def load_netscape_cookies(path: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") and not line.startswith("#HttpOnly_"):
                continue
            line = line[len("#HttpOnly_"):] if line.startswith("#HttpOnly_") else line
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    return cookies


def load_json_cookies(path: str) -> dict[str, str]:
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        return data
    return {c["name"]: c["value"] for c in data if "name" in c}


def load_cookies(txt_path: str, json_path: str) -> dict[str, str]:
    if os.path.exists(txt_path):
        c = load_netscape_cookies(txt_path)
        if c:
            return c
    if os.path.exists(json_path):
        return load_json_cookies(json_path)
    raise AuthError(
        f"Nu există fișier de cookies. Rulează `python -m postsyt login` sau exportă "
        f"cookies.txt în {txt_path}")


class InnertubeClient:
    def __init__(self, cookies: dict[str, str], channel_id: Optional[str] = None):
        self.cookies = cookies
        self.channel_id = channel_id
        self.api_key: Optional[str] = None
        self.context: Optional[dict] = None
        self.page_id: Optional[str] = None       # DELEGATED_SESSION_ID (brand accounts)
        self.visitor_data: Optional[str] = None
        self._backstage_params: Optional[str] = None
        self._backstage_params_at: float = 0.0

    # ....................................................... infra
    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def _headers(self, **extra) -> dict:
        h = {
            "Cookie": self._cookie_header(),
            "X-Origin": ORIGIN,
            "X-Youtube-Bootstrap-Logged-In": "true",
            "X-Goog-AuthUser": "0",
            "Accept": "*/*",
            "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
        }
        if self.page_id:
            h["X-Goog-PageId"] = self.page_id
        h.update(extra)
        return h

    def refresh_config(self) -> None:
        page = http_get(ORIGIN, headers=self._headers())
        cfg = extract_ytcfg(page)
        if not cfg.get("INNERTUBE_API_KEY"):
            raise AuthError("Nu am putut citi configul YouTube. Cookies expirate? Refă login.")
        if not cfg.get("LOGGED_IN", False):
            raise AuthError("Sesiunea nu e logată (LOGGED_IN=false). Re-exportă cookies.")
        self.api_key = cfg["INNERTUBE_API_KEY"]
        self.context = cfg.get("INNERTUBE_CONTEXT") or {
            "client": {
                "clientName": cfg.get("INNERTUBE_CLIENT_NAME", "WEB"),
                "clientVersion": cfg.get("INNERTUBE_CLIENT_VERSION", ""),
                "visitorData": cfg.get("VISITOR_DATA"),
            }
        }
        self.visitor_data = cfg.get("VISITOR_DATA") or \
            (self.context.get("client", {}).get("visitorData"))
        self.page_id = cfg.get("DELEGATED_SESSION_ID")
        if not self.channel_id:
            m = re.search(r'"(?:channelId|browseId)"\s*:\s*"(UC[\w-]{22})"', page)
            if m:
                self.channel_id = m.group(1)

    def ensure_config(self) -> None:
        if not self.api_key or not self.context:
            self.refresh_config()

    # ....................................................... backstage params
    def backstage_params(self, force: bool = False) -> str:
        if (not force and self._backstage_params
                and time.time() - self._backstage_params_at < 15 * 60):
            return self._backstage_params
        self.ensure_config()
        if not self.channel_id:
            raise InnertubeError("ChannelId necunoscut — setează own_channel_id în config.")
        page = http_get(f"{ORIGIN}/channel/{self.channel_id}/community",
                        headers=self._headers())
        m = re.search(r'"createBackstagePostParams"\s*:\s*"((?:[^"\\]|\\.)*)"', page)
        if not m:
            if "Community" not in page and "community" not in page:
                raise InnertubeError(
                    "Canalul nu are tab-ul Community activ (îl primești la 500+ subs).")
            raise InnertubeError("Nu am găsit createBackstagePostParams — pagina s-a schimbat sau nu ești logat.")
        params = json.loads(f'"{m.group(1)}"')  # decode escape-uri \u...
        self._backstage_params = params
        self._backstage_params_at = time.time()
        return params

    # ....................................................... upload imagine
    def upload_image(self, image_bytes: bytes) -> dict:
        """Returnează imagesData element: {encryptedBlobId, previewCoordinates}."""
        self.ensure_config()
        _, resp_headers = http_post(
            f"{ORIGIN}/channel_image_upload/posts", body=b"",
            headers=self._headers(**{
                "X-YouTube-ChannelId": self.channel_id or "",
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Header-Content-Length": str(len(image_bytes)),
                "X-Goog-Upload-Command": "start",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Authorization": sapisidhash(self.cookies),
            }))
        upload_url = resp_headers.get("X-Goog-Upload-URL") or resp_headers.get("X-Goog-Upload-Url")
        if not upload_url:
            raise InnertubeError("Nu am primit upload URL pentru imagine (X-Goog-Upload-URL).")
        body, _ = http_post(upload_url, body=image_bytes, headers=self._headers(**{
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "X-YouTube-ChannelId": self.channel_id or "",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        }))
        data = json.loads(body)
        blob = data.get("encryptedBlobId")
        if not blob:
            raise InnertubeError(f"Uploadul de imagine a eșuat: {body[:200]}")
        # dimensiuni din PNG header pentru crop corect (fallback pătrat)
        width = height = 0
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" and len(image_bytes) > 24:
            width, height = struct.unpack(">II", image_bytes[16:24])
        if width > height > 0:
            top, left = 0.0, (width - height) / (2 * width)
        elif height > width > 0:
            left, top = 0.0, (height - width) / (2 * height)
        else:
            top = left = 0.0
        return {
            "encryptedBlobId": blob,
            "previewCoordinates": {
                "top": top, "right": 1 - left, "bottom": 1 - top, "left": left,
            },
        }

    # ....................................................... creare postare
    def create_post(self, text: str, images: Optional[list[dict]] = None,
                    poll: Optional[dict] = None) -> str:
        """Publică postarea. Returnează postId. Aruncă InnertubeError la eșec."""
        self.ensure_config()
        body: dict = {
            "context": self.context,
            "createBackstagePostParams": self.backstage_params(),
            "commentText": text,
        }
        if images:
            body["imagesAttachment"] = {"imagesData": images}
        if poll:  # experimental — forma exactă nu e documentată
            body["pollAttachment"] = poll
        url = f"{ORIGIN}/youtubei/v1/backstage/create_post?key={self.api_key}&prettyPrint=false"
        client = self.context.get("client", {}) if self.context else {}
        try:
            resp, _ = http_post(url, body=json.dumps(body), headers=self._headers(**{
                "Authorization": sapisidhash(self.cookies),
                "Content-Type": "application/json",
                "X-Youtube-Client-Name": str(client.get("clientName") or 1),
                "X-Youtube-Client-Version": str(client.get("clientVersion") or ""),
                "X-Goog-Visitor-Id": str(self.visitor_data or ""),
            }))
        except HttpError as e:
            if e.status in (400, 401, 403) and not self._backstage_params:
                raise
            if e.status in (400, 401, 403):
                # reîncearcă o dată cu params proaspete
                body["createBackstagePostParams"] = self.backstage_params(force=True)
                resp, _ = http_post(url, body=json.dumps(body), headers=self._headers(**{
                    "Authorization": sapisidhash(self.cookies),
                    "Content-Type": "application/json",
                    "X-Youtube-Client-Name": str(client.get("clientName") or 1),
                    "X-Youtube-Client-Version": str(client.get("clientVersion") or ""),
                    "X-Goog-Visitor-Id": str(self.visitor_data or ""),
                }))
            else:
                raise
        m = re.search(r'"postId"\s*:\s*"([^"]+)"', resp)
        if not m:
            if "error" in resp[:2000]:
                raise InnertubeError(f"YouTube a respins postarea: {resp[:250]}")
            raise InnertubeError(f"Răspuns neașteptat la create_post: {resp[:250]}")
        # invalidează params după folosire (one-shot, per observații din proiecte)
        self._backstage_params = None
        return m.group(1)

    def create_text_or_image_post(self, text: str,
                                  image_path: Optional[str] = None) -> str:
        images = None
        if image_path and os.path.exists(image_path) and image_path.endswith((".png", ".jpg", ".jpeg")):
            with open(image_path, "rb") as f:
                images = [self.upload_image(f.read())]
        return self.create_post(text, images=images)


def check_auth(cookies: dict) -> tuple[bool, str]:
    """Verifică dacă sesiunea e validă. (ok, mesaj)"""
    try:
        client = InnertubeClient(cookies)
        client.refresh_config()
        return True, f"Autentificat. Channel: {client.channel_id or '?'}"
    except Exception as e:
        return False, str(e)
