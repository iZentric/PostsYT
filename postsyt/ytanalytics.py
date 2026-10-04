"""YouTube Analytics pentru canalul propriu — date reale, zero API key/OAuth.

Două surse combinate:
  1. Paginile canalului (/videos, /shorts, /about) -> ytInitialData:
     abonați, vizualizări totale, ultimele videoclipuri cu views/durată/dată.
  2. Studio Innertube (get_creator_analytics) -> metricile PRIVATE din
     ultimele 28 zile (vizualizări, ore vizionate, abonați noi). Dacă YouTube
     schimbă endpointul, restul datelor rămâne valid — studio vine ca bonus.

Totul e injectabil (getter/poster) => testabil 100% offline.
CLI:  python -m postsyt analytics
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Optional

from .innertube import InnertubeClient, STUDIO_ORIGIN, load_cookies, sapisidhash
from .util import (extract_yt_initial_data, extract_ytcfg, http_get, http_post,
                   parse_yt_count, runs_to_text, walk_find, deep_get)

ORIGIN = "https://www.youtube.com"

# metrici Studio pe care le recunoaștem din carduri
_KNOWN_METRICS = ("VIEWS", "ESTIMATED_WATCH_TIME", "WATCH_TIME",
                  "SUBSCRIBERS_NET_CHANGE", "SUBSCRIBERS_GAINED",
                  "SUBSCRIBERS_LOST", "TOTAL_SUBSCRIBERS")


class AnalyticsError(Exception):
    pass


# ------------------------------------------------------------------ parsare sume
def parse_count_text(text: str) -> Optional[int]:
    """Parsare robustă RO/EN: '1.2K', '1,2 K', '4.142', '1,234', '6,4 mii de
    vizualizări', '2 milioane de abonați' -> int."""
    if not text:
        return None
    t = text.lower().replace("\xa0", " ").replace(" ", " ").replace(" ", " ")
    m = re.search(r"([\d][\d\s.,]*)[\s]*(mii|milioane|miliarde|mld\.?|mil\.?|k|m)?\b", t)
    if not m:
        return None
    num_raw = m.group(1).strip(" .,")
    suf = (m.group(2) or "").rstrip(".")
    mult = {"mii": 1_000, "k": 1_000, "m": 1_000_000, "mil": 1_000_000,
            "milioane": 1_000_000, "mld": 1_000_000_000,
            "miliarde": 1_000_000_000}.get(suf, 1)
    num = num_raw.replace(" ", "")
    if mult > 1:
        if num.count(",") + num.count(".") == 1:
            num = num.replace(",", ".")
        else:  # mai multe separatoare = grupe de mii, nu zecimale
            num = num.replace(",", "").replace(".", "")
        try:
            # round() evită erorile float: 4.02 * 1000 = 4019.9999... în binar
            return int(round(float(num) * mult))
        except ValueError:
            return None
    try:
        return int(re.sub(r"[\s.,]", "", num))
    except ValueError:
        return None


def _first_numeric(text: str) -> Optional[int]:
    return parse_count_text(text)


# ------------------------------------------------------------------ ytInitialData
def parse_videos(initial: dict, tip: str = "video") -> list[dict]:
    """Extrage videoclipurile renderizate server-side dintr-un tab al canalului."""
    out: list[dict] = []
    seen: set = set()
    for vr in walk_find(initial, "videoRenderer"):
        if not isinstance(vr, dict):
            continue
        vid = str(vr.get("videoId") or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        views_txt = runs_to_text(vr.get("viewCountText")) or \
            runs_to_text(vr.get("shortViewCountText"))
        out.append({
            "id": vid,
            "titlu": runs_to_text(vr.get("title")),
            "vizionari": parse_count_text(views_txt) if "viz" in views_txt.lower()
                         or re.search(r"\d", views_txt or "") else None,
            "vizionari_txt": views_txt,
            "publicat": runs_to_text(vr.get("publishedTimeText")),
            "durata": runs_to_text(vr.get("lengthText")),
            "tip": tip,
        })
    return out


def parse_shorts(initial: dict) -> list[dict]:
    """Shorts-urile (layout nou shortsLockupViewModel)."""
    out: list[dict] = []
    seen: set = set()
    for sl in walk_find(initial, "shortsLockupViewModel"):
        if not isinstance(sl, dict):
            continue
        entity = str(sl.get("entityId") or "")
        m = re.search(r"shorts-shelf-item-([\w-]{11})", entity) or \
            re.search(r"\b([\w-]{11})\b", entity)
        vid = m.group(1) if m else ""
        if not vid or vid in seen:
            continue
        seen.add(vid)
        meta = sl.get("overlayMetadata") or {}
        titlu = str(deep_get(meta, "primaryText", "content", default="") or "")
        views_txt = str(deep_get(meta, "secondaryText", "content", default="") or "")
        if not titlu:
            acc = str(sl.get("accessibilityText") or "")
            titlu = acc.split(",")[0] if acc else ""
        out.append({
            "id": vid,
            "titlu": titlu,
            "vizionari": parse_count_text(views_txt),
            "vizionari_txt": views_txt,
            "publicat": "",
            "durata": "",
            "tip": "short",
        })
    return out


def parse_channel_header(initial: dict) -> dict:
    """Abonați / număr videoclipuri din headerul canalului.
    Două strategii: layout vechi (subscriberCountText) + layout nou
    (contentMetadataViewModel / orice text RO-EN cu 'abonați')."""
    info: dict = {"abonati": None, "abonati_txt": "", "videoclipuri_txt": ""}
    subs = walk_find(initial, "subscriberCountText")
    for s in subs:
        txt = runs_to_text(s) if not isinstance(s, str) else s
        if txt and re.search(r"\d", txt) and not info["abonati_txt"]:
            info["abonati_txt"] = txt
            info["abonati"] = parse_count_text(txt)
            break
    vids = walk_find(initial, "videosCountText")
    for v in vids:
        txt = runs_to_text(v.get("runs", v) if isinstance(v, dict) else v) \
            if not isinstance(v, str) else v
        if txt and re.search(r"\d", txt):
            info["videoclipuri_txt"] = txt
            break
    # fallback layout nou: orice bucată de text cu «abonați»/«videoclipuri»
    if not info["abonati_txt"] or not info["videoclipuri_txt"]:
        blob = json.dumps(initial, ensure_ascii=False)
        if not info["abonati_txt"]:
            m = re.search(r'"content"\s*:\s*"([\d][^"]*?(?:de abonați|subscribers?))"',
                          blob, re.IGNORECASE) or \
                re.search(r'"simpleText"\s*:\s*"([\d][^"]*?(?:de abonați|subscribers?))"',
                          blob, re.IGNORECASE)
            if m:
                info["abonati_txt"] = m.group(1)
                info["abonati"] = parse_count_text(m.group(1))
        if not info["videoclipuri_txt"]:
            m = re.search(r'"content"\s*:\s*"([\d][^"]*?(?:videoclipuri|videos?))"',
                          blob, re.IGNORECASE) or \
                re.search(r'"simpleText"\s*:\s*"([\d][^"]*?(?:videoclipuri|videos?))"',
                          blob, re.IGNORECASE)
            if m:
                info["videoclipuri_txt"] = m.group(1)
    return info


def parse_about(initial: dict) -> dict:
    """Vizualizări totale canal + dată înregistrare din tabul Despre.
    Fallback: cel mai mare număr urmat de «de vizualizări» din orice layout."""
    info: dict = {"vizualizari_totale": None, "vizualizari_totale_txt": "",
                  "inregistrat": "", "descriere": ""}
    for ab in walk_find(initial, "channelAboutFullMetadataRenderer"):
        if not isinstance(ab, dict):
            continue
        vt = runs_to_text(ab.get("viewCountText"))
        if vt and not info["vizualizari_totale_txt"]:
            info["vizualizari_totale_txt"] = vt
            info["vizualizari_totale"] = parse_count_text(vt)
        jd = runs_to_text(ab.get("joinedDateText"))
        if jd and not info["inregistrat"]:
            info["inregistrat"] = jd
        desc = runs_to_text(ab.get("description"))
        if desc and not info["descriere"]:
            info["descriere"] = desc
    if not info["vizualizari_totale_txt"]:
        blob = json.dumps(initial, ensure_ascii=False)
        best_txt, best_val = "", 0
        for m in re.finditer(r'"([\d][\d.,\s\xa0]*?)\s*(?:de vizualizări|valorizări|views?)"',
                             blob, re.IGNORECASE):
            val = parse_count_text(m.group(1)) or 0
            if val > best_val:
                best_txt, best_val = m.group(1).strip(), val
        if best_val:
            info["vizualizari_totale_txt"] = f"{best_txt} de vizualizări"
            info["vizualizari_totale"] = best_val
    return info


# ------------------------------------------------------------------ Studio metrics
def _parse_studio_cards(resp_text: str) -> dict:
    """Extrage metrici cunoscute din orice pereche (columns+rows) găsită."""
    out: dict = {}
    try:
        data = json.loads(resp_text)
    except (ValueError, TypeError):
        return out

    def numeric(v: Any) -> Optional[float]:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            for k in ("doubleValue", "bigNumberValue", "value", "simpleValue",
                      "content", "amount"):
                if k in v:
                    n = numeric(v[k])
                    if n is not None:
                        return n
            for vv in v.values():
                n = numeric(vv)
                if n is not None:
                    return n
        if isinstance(v, str):
            p = parse_count_text(v)
            return float(p) if p is not None else None
        return None

    def scan(node: Any):
        if isinstance(node, dict):
            cols = node.get("columns")
            rows = node.get("rows")
            if isinstance(cols, list) and isinstance(rows, list) and rows:
                names = []
                for c in cols:
                    if isinstance(c, str):
                        names.append(c)
                    elif isinstance(c, dict):
                        names.append(str(c.get("columnId") or c.get("metric")
                                         or c.get("name") or c.get("id") or ""))
                    else:
                        names.append("")
                row = rows[0]
                vals = row.get("values") if isinstance(row, dict) else row
                if isinstance(vals, list):
                    for i, val in enumerate(vals):
                        name = names[i].upper() if i < len(names) else ""
                        if name in _KNOWN_METRICS and name not in out:
                            n = numeric(val)
                            if n is not None:
                                out[name] = n
            for v in node.values():
                scan(v)
        elif isinstance(node, list):
            for it in node:
                scan(it)

    scan(data)
    return out


_STUDIO_PAYLOAD_VARIANTS = (
    lambda client_ver: {
        "context": {"client": {"clientName": "WEB_CREATOR", "clientVersion": client_ver}},
        "useDefaultMetricCardConfigs": True,
        "cards": [{"dimensions": [],
                   "metrics": [{"metric": m, "type": "BASIC"} for m in
                               ("VIEWS", "ESTIMATED_WATCH_TIME",
                                "SUBSCRIBERS_NET_CHANGE")]}],
        "timePeriod": {"timePeriodId": "LAST_28_DAYS"},
    },
    lambda client_ver: {
        "context": {"client": {"clientName": "WEB_CREATOR", "clientVersion": client_ver}},
        "useDefaultMetricCardConfigs": True,
        "cards": [{"dimensions": [],
                   "metrics": ["VIEWS", "ESTIMATED_WATCH_TIME",
                               "SUBSCRIBERS_NET_CHANGE"]}],
        "timePeriod": {"timePeriodId": "LAST_28_DAYS"},
    },
    lambda client_ver: {
        "context": {"client": {"clientName": "WEB_CREATOR", "clientVersion": client_ver}},
        "useDefaultMetricCardConfigs": True,
    },
)


def fetch_studio_metrics(cookies: dict, *, getter=http_get, poster=http_post) -> dict:
    """Metricile private din Studio (28 zile). Aruncă AnalyticsError la eșec total."""
    studio_page = getter(STUDIO_ORIGIN, headers={
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    })
    cfg = extract_ytcfg(studio_page) or {}
    client_ver = cfg.get("INNERTUBE_CLIENT_VERSION", "1.20251001.01.00")
    api_key = cfg.get("INNERTUBE_API_KEY", "")
    url = (f"{STUDIO_ORIGIN}/youtubei/v1/creator/get_creator_analytics"
           f"?prettyPrint=false" + (f"&key={api_key}" if api_key else ""))
    base_headers = {
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "Authorization": sapisidhash(cookies, STUDIO_ORIGIN),
        "Origin": STUDIO_ORIGIN,
        "Referer": STUDIO_ORIGIN + "/",
        "X-Origin": STUDIO_ORIGIN,
        "X-Youtube-Client-Name": "62",
        "X-Youtube-Client-Version": str(client_ver),
        "X-Goog-AuthUser": "0",
        "Content-Type": "application/json",
    }
    last_err = ""
    for variant in _STUDIO_PAYLOAD_VARIANTS:
        body = json.dumps(variant(client_ver))
        try:
            text, _ = poster(url, body=body, headers=base_headers)
        except Exception as e:  # noqa: BLE001 - încercăm următoarea variantă
            last_err = str(e)[:200]
            continue
        metrics = _parse_studio_cards(text)
        if metrics:
            return metrics
        last_err = "răspuns fără metrici recunoscute"
    raise AnalyticsError(f"Studio analytics indisponibil: {last_err or 'toate variantele au eșuat'}")


# ------------------------------------------------------------------ principal
def get_channel_analytics(cfg, *, getter: Callable = http_get,
                          poster: Callable = http_post,
                          save: bool = True) -> dict:
    """Pachetul complet de analytics. Nu aruncă excepții pentru surse individuale
    — fiecare eroare ajunge în res['erori'], datele rămase rămân valide."""
    cookies = load_cookies(cfg.cookies_file, cfg.cookies_json)
    headers = {
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    }
    handle = cfg.own_handle if str(cfg.own_handle).startswith("@") \
        else f"@{cfg.own_handle}"
    res: dict = {
        "canal": {"handle": handle, "id": cfg.own_channel_id,
                  "abonati": None, "abonati_txt": "", "videoclipuri_txt": "",
                  "vizualizari_totale": None, "vizualizari_totale_txt": "",
                  "inregistrat": ""},
        "video_recente": [],
        "studio_28zile": None,
        "surse": [],
        "erori": [],
    }

    def _page(tab: str) -> Optional[dict]:
        try:
            html = getter(f"{ORIGIN}/{handle}/{tab}", headers=headers)
            return extract_yt_initial_data(html) or {}
        except Exception as e:  # noqa: BLE001
            res["erori"].append(f"pagina /{tab}: {str(e)[:160]}")
            return None

    # 1) videoclipuri + header canal (abonați)
    vids_page = _page("videos")
    if vids_page is not None:
        res["video_recente"].extend(parse_videos(vids_page, tip="video"))
        if vids_page:
            hdr = parse_channel_header(vids_page)
            res["canal"].update({k: v for k, v in hdr.items() if v not in (None, "")})
            res["surse"].append("pagina_canal")

    # 2) shorts
    shorts_page = _page("shorts")
    if shorts_page:
        res["video_recente"].extend(parse_shorts(shorts_page))

    # 3) about (vizualizări totale)
    about_page = _page("about")
    if about_page:
        about = parse_about(about_page)
        res["canal"].update({k: v for k, v in about.items() if v not in (None, "")})

    # 4) metrici private Studio (bonus; nu blochează restul)
    try:
        metrics = fetch_studio_metrics(cookies, getter=getter, poster=poster)
        res["studio_28zile"] = {
            "vizualizari": metrics.get("VIEWS"),
            "ore_vizionate": (metrics.get("ESTIMATED_WATCH_TIME")
                              or metrics.get("WATCH_TIME")),
            "abonati_noi": metrics.get("SUBSCRIBERS_NET_CHANGE"),
            "abonati_total": metrics.get("TOTAL_SUBSCRIBERS"),
        }
        res["surse"].append("studio")
    except Exception as e:  # noqa: BLE001
        res["erori"].append(f"studio_28zile: {str(e)[:160]}")

    if save:
        os.makedirs(cfg.data_dir, exist_ok=True)
        path = os.path.join(cfg.data_dir, "analytics_latest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        res["salvat_in"] = path
    return res


def _fmt_int(n: Any) -> str:
    if n is None:
        return "?"
    return f"{int(n):,}".replace(",", ".")


def format_summary(res: dict) -> str:
    c = res["canal"]
    lines = [f"📊 ANALYTICS {c['handle']} — date reale",
             f"   Abonați: {c.get('abonati_txt') or _fmt_int(c.get('abonati'))}   "
             f"Clipuri: {c.get('videoclipuri_txt') or '?'}   "
             f"Vizualizări totale: {c.get('vizualizari_totale_txt') or _fmt_int(c.get('vizualizari_totale'))}"]
    s = res.get("studio_28zile")
    if s and any(v is not None for v in s.values()):
        lines.append(f"   Ultimele 28 zile (Studio): vizualizări {_fmt_int(s.get('vizualizari'))} · "
                     f"ore vizionate {_fmt_int(s.get('ore_vizionate'))} · "
                     f"abonați noi {_fmt_int(s.get('abonati_noi'))}")
    else:
        lines.append("   Ultimele 28 zile (Studio): indisponibil acum — restul datelor e valid")
    vids = res.get("video_recente", [])
    if vids:
        lines.append("   Ultimele clipuri:")
        for i, v in enumerate(vids[:12], 1):
            tip = "short" if v["tip"] == "short" else "video"
            lines.append(f"    {i:>2}. [{tip}] {v['titlu'][:52]} — "
                         f"{v.get('vizionari_txt') or _fmt_int(v.get('vizionari'))}"
                         + (f" · {v['publicat']}" if v.get("publicat") else ""))
    if res.get("erori"):
        lines.append("   ⚠️ " + " | ".join(res["erori"]))
    return "\n".join(lines)
