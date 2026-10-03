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
  - PC-ul execută doar cereri către YouTube/Google (lista de mai jos) —
    nimeni nu te poate folosi ca proxy spre internet.

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


def host_allowed(url: str) -> bool:
    """True doar dacă URL-ul aparține YouTube/Google (proxy-lock)."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


HOP_BY_HOP = {"host", "content-length", "connection", "keep-alive",
              "transfer-encoding", "upgrade", "proxy-authorization"}
MAX_RESP = 24 * 1024 * 1024  # nu citim răspunsuri mai mari de 24 MB


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S]") + " " + msg, flush=True)


class PcBridge:
    def __init__(self, server: str, secret: str, name: str = "PC",
                 agent: str = "postsyt", wait: int = 50):
        self.server = server.rstrip("/")
        self.secret, self.name, self.agent, self.wait = secret, name, agent, wait
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
        if not host_allowed(url):
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

    if not server or not secret:
        print("Completează datele de conectare (le găsești după instalarea serverului):")
        server = server or input("  Adresa serverului (ex: http://80.240.24.15:8787): ").strip()
        secret = secret or input("  Secret (bridge_secret din config.json): ").strip()
        if not server or not secret:
            sys.exit("Lipsește serverul sau secretul.")

    PcBridge(server, secret, name=name, agent=agent, wait=min(wait, 55)).run()


if __name__ == "__main__":
    try:
        load_and_run()
    except KeyboardInterrupt:
        print("\nOprit.")
