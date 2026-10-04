"""Firul ARENA <-> server: eu (agentul din chat) scriu ordinele chirurgicale în
`orders/latest.json` în GitHub; daemon-ul de pe VPS îl descarcă periodic și execută
CU SESIUNEA CONTULUI (publică posturi, scanează statistici/comentarii, aduce pagini
de internet greu ajungibile). Serverul e doar „mâinile” logate; decizia e în chat.

Manifest (orders/latest.json):
{
  "rev": "2026-10-04-a",                 // obligatoriu - execuția e unică per rev
  "expires": "2026-10-20",               // opțional - zip cheap YYYY-MM-DD
  "jobs": [
    {"type": "publish", "kind": "A", "text": "...", "poll_options": ["a","b"]},
    {"type": "approve_all"},
    {"type": "generate", "kind": "C"},
    {"type": "analytics"},                                // salvează în KIT
    {"type": "deepstats", "limit": 6, "transcript": false},
    {"type": "comments_scan", "zile": 30, "max_videos": 10},
    {"type": "comments_reply", "plan": {...}, "limita": 15, "uscat": false},
    {"type": "fetch", "url": "https://...", "session": true}
  ]
}
Rev neexecutat => rulează; rev văzut deja => sare (idempotent). Fiecare ordin e
izolat: dacă unul crapă, restul continuă, iar rezultatul se vede în Jurnal+KIT.
"""

import json
import os
import time
from datetime import datetime, timezone

BRANCH = "arena/01a103b1-postsyt"
ORDERS_URL = ("https://raw.githubusercontent.com/iZentric/PostsYT/"
              f"{BRANCH}/orders/latest.json")
MAX_JOBS = 10
FETCH_TRIM = 16000      # caractere salvate din pagina cerută


def _download_manifest(fetch_text=None) -> dict:
    if fetch_text is not None:
        return json.loads(fetch_text)
    from .util import http_get
    sep = "&" if "?" in ORDERS_URL else "?"
    raw = http_get(f"{ORDERS_URL}{sep}ts={int(time.time())}", timeout=20)
    return json.loads(raw)


def _state_path(cfg) -> str:
    return os.path.join(cfg.data_dir, "orders_state.json")


def _load_state(cfg) -> dict:
    try:
        with open(_state_path(cfg), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(cfg, rev: str, note: str) -> None:
    try:
        os.makedirs(cfg.data_dir, exist_ok=True)
        with open(_state_path(cfg), "w", encoding="utf-8") as f:
            json.dump({"rev": rev, "at": datetime.now(timezone.utc).isoformat(),
                       "note": note}, f, ensure_ascii=False)
    except Exception:
        pass


def pull_and_execute(cfg, store, agent, fetch_text=None, now=None) -> dict:
    """Descarcă manifestul; execută joburile o singură dată per `rev`.
    Niciodată nu aruncă — erorile se raportează în `report` și Jurnal."""
    report = {"rev": None, "executed": [], "skipped": True, "eroare": ""}
    try:
        manifest = _download_manifest(fetch_text)
    except Exception as e:
        report["eroare"] = f"download manifest: {e}"
        return report
    rev = str(manifest.get("rev") or "").strip()
    report["rev"] = rev
    if not rev:
        return report
    if _load_state(cfg).get("rev") == rev:
        return report                       # deja executat — idempotent
    expires = str(manifest.get("expires") or "2999-12-31")
    today = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    if expires < today:
        _save_state(cfg, rev, "expirat — sărit fără execuție")
        store.log(f"🛰️ Manifest {rev} expirat ({expires}) — sărit", "WARN")
        return report
    jobs = list(manifest.get("jobs") or [])[:MAX_JOBS]
    report["skipped"] = False
    for i, job in enumerate(jobs, 1):
        kind = str(job.get("type") or "?")
        try:
            detail = _run_job(cfg, store, agent, job)
            report["executed"].append(f"{i}.{kind}: {detail}")
            store.log(f"🛰️ Ordin {i}/{len(jobs)} ({kind}): {detail}")
        except Exception as e:
            report["executed"].append(f"{i}.{kind}: EROARE {e}")
            store.log(f"🛰️ Ordin {i}/{len(jobs)} ({kind}) EȘUAT: {e}", "ERROR")
    _save_state(cfg, rev, f"{len(report['executed'])} joburi executate")
    return report


# ---------------------------------------------------------------- joburile

def _run_job(cfg, store, agent, job: dict) -> str:
    kind = str(job.get("type") or "")
    if kind == "publish":
        return _job_publish(store, agent, job)
    if kind == "approve_all":
        pend = store.drafts(status="draft", limit=50)
        from .models import STATUS_APPROVED
        for d in pend:
            store.update_draft(d.id, status=STATUS_APPROVED)
        return f"{len(pend)} drafturi aprobate"
    if kind == "generate":
        did = agent.force_generate(str(job.get("kind") or "A"))
        return f"draft #{did} generat"
    if kind == "tick":
        rep = agent.tick(quick=True)
        return "tick complet"
    if kind == "analytics":
        from . import ytanalytics
        res = ytanalytics.get_channel_analytics(cfg)
        return (f"salvat ({len(res.get('video_recente', []))} clipuri); "
                f"vizibil în KIT")
    if kind == "deepstats":
        from . import deepstats
        from .cli import _videoclipuri_pentru_scan
        vids = _videoclipuri_pentru_scan(cfg, int(job.get("limit") or 6))
        if not vids:
            return "0 clipuri găsite de scanat"
        rez = deepstats.depth_scan(cfg, vids,
                                   want_transcripts=bool(job.get("transcript", False)),
                                   top_comentarii=int(job.get("top_comments", 5)))
        return f"{rez['total']} clipuri → {os.path.basename(str(rez.get('salvat_in', '?')))} (în KIT)"
    if kind == "comments_scan":
        from .comments import Commenter
        from .cli import _videoclipuri_pentru_scan
        vids = _videoclipuri_pentru_scan(cfg, int(job.get("max_videos") or 10))
        if not vids:
            return "0 clipuri găsite de scanat"
        rez = Commenter(cfg, store=store).scan(
            vids, zile=int(job.get("zile") or 30),
            max_pages=int(job.get("pagini") or 3),
            doar_fara_raspuns=not bool(job.get("cu_raspuns", False)))
        erori_txt = " | ".join(str(e)[:90] for e in rez.get("erori", [])[:2])
        return (f"{rez['total']} de răspuns, erori {len(rez['erori'])}"
                + (f" [{erori_txt}]" if erori_txt else "")
                + f" → {os.path.basename(str(rez.get('salvat_in', '?')))} (în KIT)")
    if kind == "comments_reply":
        from .comments import Commenter
        plan = job.get("plan") or {}
        rez = Commenter(cfg, store=store).apply_plan(
            plan, limita_zilnica=int(job.get("limita") or 15),
            uscat=bool(job.get("uscat", False)))
        return f"postate {rez['postate']}, sărite {rez['sarite']}, erori {len(rez['erori'])}"
    if kind == "fetch":
        return _job_fetch(cfg, store, job)
    raise ValueError(f"tip necunoscut: {kind!r}")


def _download_image(cfg, url: str) -> str:
    """Descarcă o imagine reală de pe net (pentru posturile cu poză ale agentului)."""
    import urllib.request
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("image_url invalid")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PostsYT-orders)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read(9 * 1024 * 1024)
    if len(body) < 500:
        raise ValueError("fișierul descărcat e prea mic — nu pare imagine")
    if body[:8].startswith(b"\x89PNG"):
        ext = ".png"
    elif body[:2] == b"\xff\xd8":
        ext = ".jpg"
    elif body[8:12] == b"WEBP":
        ext = ".webp"
    else:
        ext = ".jpg"
    os.makedirs(cfg.images_dir, exist_ok=True)
    path = os.path.join(cfg.images_dir, f"agent_{int(time.time())}{ext}")
    with open(path, "wb") as f:
        f.write(body)
    return path


def _job_publish(store, agent, job: dict) -> str:
    text = str(job.get("text") or "").strip()[:2000]
    if not text:
        raise ValueError("publish fără text")
    opts = [str(o)[:80] for o in (job.get("poll_options") or []) if str(o).strip()][:8]
    img = str(job.get("image_url") or "").strip()
    image_path = _download_image(agent.cfg, img) if img else ""
    from .models import Draft, STATUS_APPROVED
    draft = Draft(kind="C" if opts else str(job.get("kind") or "A")[:1].upper(),
                  text=text,
                  poll_question=(text.split("\n")[0][:140] if opts else ""),
                  poll_options=opts,
                  image_path=image_path,
                  source="orders-agent-arena",
                  status=STATUS_APPROVED)
    did = store.add_draft(draft)
    d = store.get_draft(did) if did else None
    if d is None:          # fallback: publicăm obiectul construit, nu blocăm zborul
        store.log(f"⚠️ publish: get_draft({did}) gol — public direct din obiect", "WARN")
        d = draft
    agent.publisher.publish(d)
    if did:
        try:               # marcajul local e separat de zbor — nu-l lăsăm să reraport eșec
            from .models import STATUS_PUBLISHED
            store.update_draft(did, status=STATUS_PUBLISHED)
        except Exception as e:  # noqa: BLE001
            store.log(f"⚠️ publish: marcaj DB pentru #{did}: {e}", "WARN")
    return (f"post #{did} zburat spre YouTube ({'sondaj' if opts else 'text'}"
            f"{'+imagine REALĂ' if image_path else ''})")


def _job_fetch(cfg, store, job: dict) -> str:
    url = str(job.get("url") or "").strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("fetch fără URL https valid")
    use_session = bool(job.get("session", True))
    if use_session:
        from .innertube import InnertubeClient, load_cookies
        cookies = load_cookies(cfg.cookies_file, cfg.cookies_json)
        client = InnertubeClient(cookies, channel_id=cfg.own_channel_id)
        _status, _hdrs, body = client._req("GET", url, headers=client._headers())
    else:
        from .util import http_get
        body = http_get(url, timeout=30)
    if not isinstance(body, str):
        body = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    os.makedirs(cfg.data_dir, exist_ok=True)
    path = os.path.join(cfg.data_dir, "fetch_latest.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\nDATA: {datetime.now(timezone.utc).isoformat()}\n"
                f"SESIUNE: {'da' if use_session else 'nu'}\n{'=' * 60}\n")
        f.write(body[:FETCH_TRIM])
    return f"adus {len(body)} caractere → fetch_latest.txt (în KIT)"
