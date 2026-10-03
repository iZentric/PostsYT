"""Bridge Hub — releul dintre agenți (cloud) și PC-ul utilizatorului.

Arhitectură:
  AGENT (server/VPS) --enqueue task--> HUB <--long-poll-- PC BRIDGE (pc_bridge.py)
  PC-ul execută cererea HTTP local (IP-ul lui rezidențial) și întoarce răspunsul.

- Protocol JSON minimal, generabil de ORICE proiect (vezi docs/BRIDGE.md).
- Securitate: secret partajat; fără secret nu poți nici lua, nici livra taskuri.
- PC-ul filtrează domeniile (implicit doar YouTube/Google) → nu poate fi abuzat.
"""
from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from typing import Optional


class BridgeHub:
    def __init__(self, secret: str):
        self.secret = secret or ""
        self.enabled = bool(self.secret)
        self._cond = threading.Condition()
        self._queue: list[dict] = []          # taskuri în așteptare
        self._results: dict[str, dict] = {}   # id -> rezultat primit de la PC
        self.bridges: dict[str, dict] = {}    # nume -> {agent, last_seen}

    # ----------------------------- latura PC (bridge-ul)
    def check_secret(self, secret: str) -> bool:
        return self.enabled and secret == self.secret

    def poll(self, name: str, agent: str, wait: int = 45) -> Optional[dict]:
        """PC-ul așteaptă long-poll un task. Returnează task sau None la timeout."""
        deadline = time.time() + min(wait, 55)
        with self._cond:
            self.bridges[name] = {"agent": agent, "last_seen": time.time()}
            self._cond.notify_all()
            task_id_taken = None
            while time.time() < deadline:
                if self._queue:
                    task = self._queue.pop(0)
                    return task
                self._cond.wait(timeout=min(2.0, max(0.2, deadline - time.time())))
        return None

    def deliver(self, task_id: str, result: dict) -> bool:
        with self._cond:
            # (taskul a fost deja luat/s-a expirat — acceptăm oricum rezultatul)
            self._results[task_id] = result
            self._cond.notify_all()
        return True

    # ----------------------------- latura AGENT (server)
    def submit(self, url: str, method: str = "GET", headers: Optional[dict] = None,
               body: bytes | None = None, timeout: int = 45, project: str = "*") -> dict:
        """Trimite o cerere spre PC și așteaptă răspuns. Returnează:
        {status, headers, body_b64, error?}"""
        if not self.enabled:
            return {"status": 0, "error": "bridge hub dezactivat (lipsește bridge_secret)"}
        with self._cond:
            alive = [n for n, b in self.bridges.items() if time.time() - b["last_seen"] < 70]
        if not alive:
            return {"status": 0, "error": "niciun PC bridge conectat"}
        task = {
            "id": uuid.uuid4().hex,
            "url": url,
            "method": method.upper(),
            "headers": headers or {},
            "body_b64": base64.b64encode(body or b"").decode(),
            "timeout": 35,
            "project": project,
            "queued_at": time.time(),
        }
        deadline = time.time() + timeout
        with self._cond:
            self._queue.append(task)
            self._cond.notify_all()
            while time.time() < deadline:
                if task["id"] in self._results:
                    return self._results.pop(task["id"])
                self._cond.wait(timeout=0.5)
        return {"status": 0, "error": "timeout — PC-ul nu a răspuns la timp"}

    def status(self) -> list[dict]:
        now = time.time()
        return [
            {"name": n, "agent": b["agent"], "online": (now - b["last_seen"] < 70),
             "last_seen_ago_s": int(now - b["last_seen"])}
            for n, b in self.bridges.items()
        ]

    # ----------------------------- transport pentru InnertubeClient
    def make_transport(self):
        """Funcție transport compatibilă InnertubeClient(transport=...)."""
        from .util import HttpError

        def transport(method: str, url: str, headers: dict, body: bytes | None):
            res = self.submit(url, method=method, headers=headers,
                              body=body if isinstance(body, (bytes, str)) else None,
                              timeout=50, project="postsyt")
            status = res.get("status") or 0
            body_b = base64.b64decode(res.get("body_b64") or b"")
            text = body_b.decode("utf-8", errors="replace")
            if status >= 400:
                raise HttpError(status, url, text)
            if status == 0:
                raise ConnectionError(f"Bridge PC: {res.get('error','eroare necunoscută')}")
            return status, res.get("headers") or {}, text
        return transport
