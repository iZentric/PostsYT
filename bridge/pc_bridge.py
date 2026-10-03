#!/usr/bin/env python3
"""
PostsYT PC Bridge — releu universal care rulează pe PC-ul TĂU.

Ce face: stă așezat (aprox. 15-20 MB RAM, ~0% CPU, ~2 cereri mici/minut),
întreabă serverul dacă are vreun task HTTP, îl execută de pe IP-ul tău de
acasă (cu sesiunea ta YouTube, dacă serverul îi trimite header-ele) și
întoarce răspunsul. ORICE proiect de pe server poate folosi bridge-ul
(vezi docs/BRIDGE.md), nu doar PostsYT.

Siguranță:
  - fără secretul partajat, taskurile sunt refuzate de server;
  - proxy-lock configurabil («allow» din ini): implicit doar YouTube/Google;
    cu «allow = *» agenții tăi pot folosi ORICE domeniu public.
  - localhost/LAN/router BLOCATE MEREU, indiferent de setare.

Rulare manuală:
  python pc_bridge.py --server http://IP-SERVER:8787 --secret SECRETUL

Sau cu fișier postsyt-bridge.ini (lângă script sau în %USERPROFILE%):
  [bridge]
  server = http://IP-SERVER:8787
  secret = cheia-din-config.json-de-pe-server
  name   = PC-ACASA
  agent  = postsyt
"""
from __future__ import annotations

import base64
import configparser
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

# --- unicul loc unde se decide ce are voie să treacă prin PC-ul tău ----------
ALLOWED_HOSTS = ("youtube.com", "googleapis.com", "ggpht.com", "ytimg.com")


def _is_private(host: str) -> bool:
    """localhost / LAN / router — BLOCAT MEREU, chiar și cu allow=*.
    (protejează routerul și device-urile din rețeaua ta, indiferent de setare)"""
    import ipaddress
    h = host.lower()
    if h in ("localhost",) or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
    except ValueError:
        return False  # nume de domeniu public — OK


def make_checker(allow_spec: str | None):
    """Fabrică de filtru. allow_spec:
       None/'' -> doar YouTube/Google (implicit, maxim de sigur)
       'a.com,b.com' -> doar acele domenii (+ subdomenii)
       '*' -> ORICE domeniu public (localhost/LAN rămân mereu blocate)"""
    if allow_spec is None or not str(allow_spec).strip():
        allow_spec = ",".join(ALLOWED_HOSTS)
    raw = [p.strip().lower() for p in str(allow_spec).split(",") if p.strip()]
    allow_all = "*" in raw
    parts = {p[1:].lstrip(".") if p.startswith("*") else p for p in raw if p != "*"}

    def ok(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host or _is_private(host):
            return False
        if allow_all:
            return True
        return any(host == h or host.endswith("." + h) for h in parts)

    ok.allow_all = allow_all
    return ok


def host_allowed(url: str) -> bool:
    """Compat: verificare cu lista implicită YouTube/Google."""
    return make_checker(None)(url)


HOP_BY_HOP = {"host", "content-length", "connection", "keep-alive",
              "transfer-encoding", "upgrade", "proxy-authorization"}
MAX_RESP = 24 * 1024 * 1024  # nu citim răspunsuri mai mari de 24 MB


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S]") + " " + msg, flush=True)


class PcBridge:
    def __init__(self, server: str, secret: str, name: str = "PC",
                 agent: str = "postsyt", wait: int = 50, allow: str | None = None):
        self.server = server.rstrip("/")
        self.secret, self.name, self.agent, self.wait = secret, name, agent, wait
        self._ok = make_checker(allow)
        self.done_tasks = 0

    # ---------------- HTTP către server (dashboardul agentului)
    def _post_json(self, path: str, payload: dict, timeout: int = 30) -> dict:
        req = urllib.request.Request(
            self.server + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def _poll(self) -> dict | None:
        """Long-poll: stă blocat până la `wait` secunde așteptând un task."""
        url = (f"{self.server}/bridge/poll?name={urllib.parse.quote(self.name)}"
               f"&agent={urllib.parse.quote(self.agent)}&wait={self.wait}")
        req = urllib.request.Request(url, headers={"X-Bridge-Key": self.secret})
        with urllib.request.urlopen(req, timeout=self.wait + 20) as r:
            return json.loads(r.read() or b"{}").get("task")

    # ---------------- execuția taskului pe PC (ieșire prin IP-ul tău)
    def _execute(self, task: dict) -> dict:
        url = task.get("url", "")
        if not self._ok(url):
            return {"status": 0, "error": f"refuzat de PC: domeniu nepermis ({url[:80]})"}
        body = base64.b64decode(task.get("body_b64") or b"")
        headers = {k: v for k, v in (task.get("headers") or {}).items()
                   if k.lower() not in HOP_BY_HOP}
        headers.setdefault("User-Agent", "pc-bridge/1.0")
        req = urllib.request.Request(url, data=body if task.get("method", "GET") != "GET" else None,
                                     headers=headers, method=task.get("method", "GET"))
        try:
            with urllib.request.urlopen(req, timeout=int(task.get("timeout") or 30)) as r:
                data = r.read(MAX_RESP)
                return {"status": r.status, "headers": dict(r.headers.items()),
                        "body_b64": base64.b64encode(data).decode()}
        except urllib.error.HTTPError as e:      # 4xx/5xx — tot răspuns util
            try:
                data = e.read(MAX_RESP)
            except Exception:
                data = b""
            return {"status": e.code, "headers": dict(e.headers.items() if e.headers else {}),
                    "body_b64": base64.b64encode(data).decode()}
        except Exception as e:
            return {"status": 0, "error": f"{type(e).__name__}: {e}"}

    # ---------------- bucla principală
    def run(self) -> None:
        log(f"🌉 PC Bridge «{self.name}» plecat → {self.server} (agent: {self.agent})")
        if self._ok.allow_all:
            log("   ⚠️  Mod ACCES TOTAL (allow=*) activ: agenții pot folosi ORICE domeniu public.")
            log("       Routerul/localhost rămân blocate oricum. Restricție: editează 'allow' din ini.")
        log("   Fără ecran. Îl poți lăsa să ruleze — nu consumă nimic. Ctrl+C ca să oprești.")
        fails = 0
        while True:
            try:
                task = self._poll()
                fails = 0
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    log("⛔ Secret greșit — verifică bridge_secret din config.json de pe server.")
                    time.sleep(60)
                else:
                    wait = min(60, 2 ** min(fails, 5))
                    log(f"Server răspuns {e.code} — reîncerc în {wait}s")
                    fails += 1
                    time.sleep(wait)
                continue
            except Exception as e:
                wait = min(60, 2 ** min(fails, 5))
                log(f"Server inaccesibil ({type(e).__name__}) — reîncerc în {wait}s")
                fails += 1
                time.sleep(wait)
                continue
            if not task:
                continue  # timeout normal de long-poll
            result = self._execute(task)
            result.update({"secret": self.secret, "id": task.get("id", "")})
            try:
                self._post_json("/bridge/result", result)
                self.done_tasks += 1
                via = result.get("status") or result.get("error", "?")
                log(f"✓ task #{self.done_tasks} gata: {task.get('method')} "
                    f"{task.get('url', '')[:68]} → {via}")
            except Exception as e:
                log(f"Nu am putut livra rezultatul: {type(e).__name__}: {e}")


def load_and_run() -> None:
    import argparse
    p = argparse.ArgumentParser(description="PostsYT PC Bridge — releu universal")
    p.add_argument("--server"); p.add_argument("--secret")
    p.add_argument("--name", default=None); p.add_argument("--agent", default=None)
    p.add_argument("--wait", type=int, default=None)
    p.add_argument("--allow", help="domenii permise separate prin virgulă, sau * = orice")
    p.add_argument("--config", help="cale către postsyt-bridge.ini")
    args = p.parse_args()

    cfg = configparser.ConfigParser()
    candidates = [args.config] if args.config else [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "postsyt-bridge.ini"),
        os.path.join(os.path.expanduser("~"), "postsyt-bridge.ini"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            cfg.read(c, encoding="utf-8")
            break
    ini = cfg["bridge"] if cfg.has_section("bridge") else {}

    server = args.server or ini.get("server", "")
    secret = args.secret or ini.get("secret", "")
    name = args.name or ini.get("name", socket.gethostname() or "PC")
    agent = args.agent or ini.get("agent", "postsyt")
    wait = args.wait or int(ini.get("wait", 50))
    allow = args.allow if args.allow is not None else ini.get("allow", None)

    if not server or not secret:
        print("Completează datele de conectare (le găsești după instalarea serverului):")
        server = server or input("  Adresa serverului (ex: http://80.240.24.15:8787): ").strip()
        secret = secret or input("  Secret (bridge_secret din config.json): ").strip()
        if not server or not secret:
            sys.exit("Lipsește serverul sau secretul.")

    PcBridge(server, secret, name=name, agent=agent, wait=min(wait, 55), allow=allow).run()


if __name__ == "__main__":
    try:
        load_and_run()
    except KeyboardInterrupt:
        print("\nOprit.")
