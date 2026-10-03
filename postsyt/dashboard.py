"""Dashboard local (stdlib http.server) — previzualizare, aprobare, publicare.

Rute:
  GET  /                  -> pagina principală
  GET  /img/<file>        -> imaginile generate (SVG/PNG)
  GET  /api/state         -> JSON cu starea curentă (pt refresh JS)
  POST /action/generate   -> ?kind=A|B|C|D|E
  POST /action/approve    -> ?id=
  POST /action/publish    -> ?id=
  POST /action/skip       -> ?id=
  POST /action/delete     -> ?id=
  POST /action/edit       -> ?id= (body: text+poll)
  POST /action/refresh    -> tick rapid (fără internet în dev)
  POST /action/tick       -> tick complet
"""
from __future__ import annotations

import json
import os
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .models import (KIND_LABELS, KIND_POLL, STATUS_APPROVED, STATUS_DRAFT,
                     STATUS_PUBLISHED)

PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>⚡ PostsYT — agentul lui iSentric</title>
<style>
:root{
 --bg:#0b0f1a; --card:#131a2c; --card2:#182136; --line:#243050;
 --txt:#e8edf7; --dim:#8ea0c2; --acc:#ffd166; --acc2:#0ea5e9; --ok:#34d399; --bad:#f87171;
}
*{box-sizing:border-box; margin:0}
body{background:radial-gradient(1200px 600px at 80% -10%,#1b2545 0%,var(--bg) 55%);
 color:var(--txt); font:15px/1.5 'Segoe UI',system-ui,sans-serif; padding:22px; min-height:100vh}
h1{font-size:26px; letter-spacing:.3px}
h1 b{color:var(--acc)}
.sub{color:var(--dim); font-size:13px; margin-top:3px}
.grid{display:grid; gap:14px}
.cols{grid-template-columns:2fr 1fr; margin-top:18px}
@media(max-width:980px){.cols{grid-template-columns:1fr}}
.kpis{grid-template-columns:repeat(4,1fr); margin-top:16px}
@media(max-width:980px){.kpis{grid-template-columns:repeat(2,1fr)}}
.card{background:linear-gradient(180deg,var(--card),var(--card2)); border:1px solid var(--line);
 border-radius:16px; padding:16px; box-shadow:0 10px 30px rgba(0,0,0,.25)}
.kpi b{font-size:26px; display:block}
.kpi span{color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.8px}
.kpi.good b{color:var(--ok)} .kpi.warn b{color:var(--acc)}
h2{font-size:17px; margin-bottom:12px; display:flex; align-items:center; gap:8px}
.tag{font-size:11px; padding:3px 10px; border-radius:20px; background:#263557; color:#bcd0f5; border:1px solid #33477c}
.tag.A{background:#123c2b;color:#7ef0b8;border-color:#1d5b41}
.tag.B{background:#46260f;color:#ffbf80;border-color:#6b3d18}
.tag.C{background:#0f3550;color:#7ccbf5;border-color:#175073}
.tag.D{background:#3b1650;color:#e49ef5;border-color:#572378}
.tag.E{background:#4a3a10;color:#ffe08a;border-color:#6d5717}
.st{font-size:11px; padding:2px 8px; border-radius:12px}
.st.draft{background:#2a3350;color:#9fb4e6}.st.approved{background:#123c2b;color:#7ef0b8}
.st.published{background:#0f3e50;color:#6fd7f5}.st.failed{background:#4a1620;color:#ff9aa5}
.btn{cursor:pointer; border:1px solid #37508a; background:#22315a; color:#dbe6ff;
 padding:8px 14px; border-radius:11px; font:600 13px 'Segoe UI'; transition:.15s}
.btn:hover{background:#2c4071; transform:translateY(-1px)}
.btn.ok{background:#0f5132;border-color:#1a7a4c;color:#c9f6dd}
.btn.danger{background:#571c22;border-color:#8a2932;color:#ffd2d6}
.btn.gold{background:#574410;border-color:#8a7017;color:#ffe9a8}
.btn.sm{padding:5px 10px; font-size:12px}
.row{display:flex; gap:8px; flex-wrap:wrap; align-items:center}
.draft{display:grid; grid-template-columns:130px 1fr; gap:14px; border-top:1px solid var(--line); padding:14px 0}
.draft img{width:130px; height:130px; object-fit:contain; border-radius:12px; background:#0a0f1e; border:1px solid var(--line)}
.dtext{white-space:pre-wrap; background:#0d1425; border:1px solid var(--line); border-radius:10px;
 padding:10px 12px; font-size:13px; max-height:180px; overflow:auto}
textarea{width:100%; background:#0d1425; color:var(--txt); border:1px solid var(--line);
 border-radius:10px; padding:10px; font:13px 'Segoe UI'; min-height:100px}
.opts{font-size:12px; color:var(--dim); margin-top:5px}
.meta{font-size:11.5px; color:var(--dim); margin-top:6px}
a{color:var(--acc2)}
table{width:100%; border-collapse:collapse; font-size:12.5px}
td,th{text-align:left; padding:7px 8px; border-bottom:1px solid var(--line)}
th{color:var(--dim); font-weight:600; text-transform:uppercase; font-size:10.5px; letter-spacing:.6px}
.log{font:12px/1.7 ui-monospace,Consolas,monospace; color:#9fb2d8; max-height:260px; overflow:auto;
 background:#0a0f1e; border-radius:10px; padding:10px 12px; border:1px solid var(--line)}
.log .WARN{color:var(--acc)} .log .ERROR{color:var(--bad)}
.hourbar{display:flex; align-items:flex-end; gap:3px; height:70px; margin-top:8px}
.hourbar div{flex:1; background:linear-gradient(180deg,var(--acc2),#1d4ed8); border-radius:4px 4px 0 0; min-height:3px; position:relative}
.hourbar div span{position:absolute; top:-15px; left:50%; transform:translateX(-50%); font-size:9px; color:var(--dim)}
.exemplar{border-top:1px solid var(--line); padding:10px 0; font-size:13px}
.exemplar .stts{font-size:11px; color:var(--dim)}
.empty{color:var(--dim); font-size:13px; padding:16px; text-align:center; border:1px dashed var(--line); border-radius:12px}
.pill{font-size:11px; background:#22315a; border-radius:20px; padding:2px 9px; color:#bcd0f5}
.pulse{display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--ok);
 box-shadow:0 0 0 0 rgba(52,211,153,.7); animation:p 2s infinite}
@keyframes p{70%{box-shadow:0 0 0 9px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.footer{margin-top:26px; color:var(--dim); font-size:11.5px; text-align:center}
details{margin-top:6px} summary{cursor:pointer; color:var(--acc2); font-size:12px}
video,img.emoji{vertical-align:middle}
</style>
</head>
<body>
<h1>⚡ <b>PostsYT</b> — agentul de postări al lui <b>iSentric</b> <span class="pill">Minecraft · PokeCity</span></h1>
<div class="sub">Regula de aur: hook + visual + link la cel mai nou clip · ritm copiat după @JocuriHorrorSky · <span class="pulse"></span> daemon: {{daemon}}</div>

<div class="grid kpis">
 <div class="card kpi"><b>{{kpi_videos}}</b><span>videoclipuri urmărite</span></div>
 <div class="card kpi warn"><b>{{kpi_drafts}}</b><span>drafturi în așteptare</span></div>
 <div class="card kpi good"><b>{{kpi_today}}</b><span>publicate azi</span></div>
 <div class="card kpi"><b>{{kpi_next}}</b><span>următorul slot</span></div>
</div>

<div class="grid cols">
 <div>
  <div class="card">
   <h2>🧠 Generează manual
    <span style="margin-left:auto" class="row">
     <button class="btn sm gold" onclick="act('generate','kind=A')">🎬 Anunț video</button>
     <button class="btn sm gold" onclick="act('generate','kind=C')">📊 Sondaj</button>
     <button class="btn sm gold" onclick="act('generate','kind=D')">😂 Meme</button>
     <button class="btn sm gold" onclick="act('generate','kind=E')">❓ Întrebare</button>
     <button class="btn sm gold" onclick="act('generate','kind=B')">🔥 Trend</button>
     <button class="btn sm" onclick="act('tick')">⟳ Tick agent</button>
    </span></h2>
   {{drafts_html}}
  </div>
 </div>
 <div class="grid">
  <div class="card"><h2>🎬 Ultimul video</h2>{{latest_video_html}}</div>
  <div class="card"><h2>🎓 Style Lab — ce merge la @JocuriHorrorSky</h2>
   <div class="sub">Orele lui de publicare observate</div>
   {{hours_bar}}
   {{exemplars_html}}
  </div>
  <div class="card"><h2>🔥 Trenduri gaming acum</h2>{{trends_html}}</div>
  <div class="card"><h2>📜 Jurnal</h2><div class="log">{{log_html}}</div></div>
 </div>
</div>
<div class="footer">PostsYT v{{version}} · rulează local · driver publicare: <b>{{driver}}</b> · autopublish: <b>{{autopub}}</b> · <a href="https://studio.youtube.com/channel/UCBoZcTLayAUgYTPsyrStiLg" target="_blank">YouTube Studio ↗</a></div>
<script>
async function act(a, qs){
 qs = qs ? '&'+qs : '';
 await fetch('/action/'+a+'?id=0'+qs, {method:'POST'});
 location.reload();
}
async function actId(a, id){
 await fetch('/action/'+a+'?id='+id, {method:'POST'});
 location.reload();
}
async function saveEdit(id){
 const t = document.getElementById('t'+id).value;
 await fetch('/action/edit?id='+id, {method:'POST', body: JSON.stringify({text:t})});
 location.reload();
}
setTimeout(()=>{ if(!document.querySelector('details[open]')) location.reload(); }, 45000);
</script>
</body>
</html>"""


class Dashboard:
    def __init__(self, cfg, store, agent):
        self.cfg, self.store, self.agent = cfg, store, agent

    # ------------------------------------------------------ view helpers
    def _drafts_html(self) -> str:
        drafts = self.store.drafts(limit=30)
        show = [d for d in drafts if d.status in (STATUS_DRAFT, STATUS_APPROVED)] or drafts[:6]
        if not show:
            return '<div class="empty">Niciun draft încă. Apasă pe un buton de generare sau pornește daemonul.</div>'
        out = []
        for d in show:
            img = ""
            if d.image_path and os.path.exists(d.image_path):
                img = f'<img src="/img/{os.path.basename(d.image_path)}" alt="visual">'
            else:
                img = '<div style="width:130px;height:130px;border-radius:12px;background:#0a0f1e;border:1px solid var(--line);display:flex;align-items:center;justify-content:center;color:var(--dim);font-size:11px">fără<br>imagine</div>'
            opts = ""
            if d.kind == KIND_POLL and d.poll_options:
                letters = "ABCDE"
                opts = '<div class="opts">' + " · ".join(
                    f"<b>{letters[i]}</b> {o}" for i, o in enumerate(d.poll_options)) + "</div>"
            sched = d.scheduled_for.strftime("%d %b %H:%M") if d.scheduled_for else "cât mai repede"
            link = f' · 🔗 <a href="{d.link}" target="_blank">link</a>' if d.link else ""
            actions = ""
            if d.status == STATUS_DRAFT:
                actions = (f'<button class="btn sm ok" onclick="actId(\'approve\',{d.id})">✔ Aprobă</button>'
                           f'<button class="btn sm danger" onclick="actId(\'skip\',{d.id})">✖ Sari</button>')
            elif d.status == STATUS_APPROVED:
                actions = (f'<button class="btn sm ok" onclick="actId(\'publish\',{d.id})">🚀 Publică acum</button>'
                           f'<button class="btn sm danger" onclick="actId(\'skip\',{d.id})">✖ Sari</button>')
            else:
                actions = f'<button class="btn sm danger" onclick="actId(\'delete\',{d.id})">🗑</button>'
            out.append(f'''
<div class="draft">
 <div>{img}</div>
 <div>
  <div class="row"><span class="tag {d.kind}">{d.kind_label()}</span>
   <span class="st {d.status}">{d.status}</span>
   <span class="pill">🕒 {sched}</span>{link}</div>
  <details><summary>editează…</summary>
   <textarea id="t{d.id}">{d.text}</textarea>
   <button class="btn sm" onclick="saveEdit({d.id})">💾 Salvează</button></details>
  <div class="dtext">{d.text}</div>{opts}
  <div class="meta">{d.source}{(' — ⚠ ' + d.error) if d.error else ''}</div>
  <div class="row" style="margin-top:8px">{actions}</div>
 </div>
</div>''')
        return "".join(out)

    def _latest_video_html(self) -> str:
        v = self.store.latest_video()
        if not v:
            return '<div class="empty">Încă nu am citit feedul. Pornește un tick cu internet.</div>'
        return (f'<a href="{v["url"]}" target="_blank"><img src="https://i.ytimg.com/vi/{v["id"]}/mqdefault.jpg" '
                f'style="width:100%;border-radius:12px"></a>'
                f'<div style="margin-top:8px;font-weight:600">{v["title"]}</div>'
                f'<div class="meta">{(v["published"] or "")[:10]} · 👁 {v["views"] if v["views"] else "?"} · '
                f'{"🔴 live" if v["is_live"] else ("#shorts" if v["is_short"] else "video")}</div>')

    def _hours_bar(self) -> str:
        hours = self.store.exemplar_hours(self.cfg.mirror_channel)
        learned = self.store.get_kv("learned_hours", self.cfg.daytime_slots)
        counts = [0] * 24
        for h in hours:
            counts[h % 24] += 1
        mx = max(counts) or 1
        bars = []
        for h in range(24):
            ht = int(60 * counts[h] / mx) + 3
            star = "*" if h in (learned or []) else str(h)
            bars.append(f'<div style="height:{ht}px" title="{h}:00 — {counts[h]} postări"><span>{star}</span></div>')
        return f'<div class="hourbar">{"".join(bars)}</div><div class="meta">* = sloturi recomandate învățate: <b>{learned}</b></div>'

    def _exemplars_html(self) -> str:
        ex = self.store.top_exemplars(limit=5)
        if not ex:
            return '<div class="empty">Fă un tick cu internet ca să învățăm stilul lui.</div>'
        out = []
        for e in ex:
            stats = f'👍 {e["likes"] if e["likes"] else "?"} · 💬 {e["comments"] if e["comments"] else "?"}'
            out.append(f'<div class="exemplar">{e["text"][:160]}<div class="stts">{stats}</div></div>')
        return "".join(out)

    def _trends_html(self) -> str:
        ts = self.store.top_trends(limit=8)
        if not ts:
            return '<div class="empty">Nicio tendință încă — rulează un tick cu internet.</div>'
        rows = "".join(
            f'<tr><td><a href="{t["url"]}" target="_blank">{t["title"][:60]}</a></td>'
            f'<td>{t["channel"][:20]}</td><td>{int(t.get("vph") or 0):,}/h</td></tr>' for t in ts)
        return f'<table><tr><th>Trend</th><th>Canal</th><th>Viteză</th></tr>{rows}</table>'

    def _log_html(self) -> str:
        evs = self.store.recent_events(40)
        return "".join(
            f'<div class="{e["level"]}">[{(e["ts"] or "")[5:16].replace("T"," ")}] {e["msg"]}</div>'
            for e in evs)

    def render(self) -> str:
        from . import __version__
        d_list = self.store.drafts(status=STATUS_DRAFT)
        daemon = "ON" if os.environ.get("POSTSYT_DAEMON") == "1" else "OFF"
        # următorul slot: cel mai apropiat draft programat
        upcoming = [d for d in self.store.drafts(status=STATUS_APPROVED) if d.scheduled_for] + \
                   [d for d in d_list if d.scheduled_for]
        nxt = min((d.scheduled_for for d in upcoming), default=None)
        html = PAGE
        repl = {
            "{{daemon}}": daemon,
            "{{kpi_videos}}": str(self.store.count_videos()),
            "{{kpi_drafts}}": str(len(d_list)),
            "{{kpi_today}}": str(self.store.published_today()),
            "{{kpi_next}}": nxt.strftime("%H:%M") if nxt else "—",
            "{{drafts_html}}": self._drafts_html(),
            "{{latest_video_html}}": self._latest_video_html(),
            "{{hours_bar}}": self._hours_bar(),
            "{{exemplars_html}}": self._exemplars_html(),
            "{{trends_html}}": self._trends_html(),
            "{{log_html}}": self._log_html(),
            "{{driver}}": self.cfg.publish_driver,
            "{{autopub}}": "DA" if self.cfg.autopublish else "NU (aprobare manuală)",
            "{{version}}": __version__,
        }
        for k, v in repl.items():
            html = html.replace(k, v)
        return html


def make_handler(dash: Dashboard):
    cfg, store, agent = dash.cfg, dash.store, dash.agent

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, text: str, ctype="text/html; charset=utf-8", code=200):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/" or u.path == "/index.html":
                self._send(dash.render())
            elif u.path.startswith("/img/"):
                name = os.path.basename(u.path)
                path = os.path.join(cfg.images_dir, name)
                if not os.path.exists(path):
                    self._send("404", "text/plain", 404)
                    return
                ctype = ("image/svg+xml" if name.endswith(".svg")
                         else "image/png" if name.endswith(".png") else "image/jpeg")
                with open(path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/state":
                state = {
                    "drafts": len(store.drafts(status=STATUS_DRAFT)),
                    "published_today": store.published_today(),
                }
                self._send(json.dumps(state), "application/json")
            else:
                self._send("Not found", "text/plain", 404)

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if not u.path.startswith("/action/"):
                self._send("Not found", "text/plain", 404)
                return
            action = u.path.split("/action/")[1]
            q = urllib.parse.parse_qs(u.query)
            did = int(q.get("id", ["0"])[0])
            try:
                def work():
                    if action == "generate":
                        agent.force_generate(q.get("kind", ["C"])[0])
                    elif action == "approve":
                        store.update_draft(did, status=STATUS_APPROVED)
                        store.log(f"👍 Draft #{did} aprobat")
                    elif action == "publish":
                        d = store.get_draft(did)
                        if d:
                            store.update_draft(did, status=STATUS_APPROVED)
                            agent.publisher.publish(d)
                    elif action == "skip":
                        store.update_draft(did, status="skipped")
                        store.log(f"⏭️ Draft #{did} sărit")
                    elif action == "delete":
                        store.update_draft(did, status="skipped")
                    elif action == "edit":
                        length = int(self.headers.get("Content-Length", 0))
                        payload = json.loads(self.rfile.read(length) or b"{}")
                        if payload.get("text"):
                            store.update_draft(did, text=payload["text"])
                            store.log(f"✏️ Draft #{did} editat")
                    elif action == "tick":
                        agent.tick(quick=True)
                    elif action == "refresh":
                        pass
                if action == "tick":
                    threading.Thread(target=work, daemon=True).start()
                else:
                    work()
            except Exception as e:
                store.log(f"Eroare acțiune {action}: {e}", "ERROR")
            self._send("ok", "text/plain")

    return Handler


def run_dashboard(cfg, store, agent, port: Optional[int] = None):
    port = port or cfg.dashboard_port
    dash = Dashboard(cfg, store, agent)
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(dash))
    print(f"🌐 Dashboard pornit pe http://0.0.0.0:{port} — deschide în browser")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
