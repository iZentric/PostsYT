# 🌉 PC Bridge — releu universal prin PC-ul de acasă

## Ce e și de ce există

Agentul PostsYT rulează 24/7 pe un server (VPS), dar YouTube vede *mai bine*
postările care vin **de pe IP-ul tău rezidențial** (același cu contul/cookie-urile).
Bridge-ul rezolvă asta fără ca PC-ul să facă vreo treabă grea:

```
AGENT (server/VPS) ── pune task în coadă ──> DASHBOARD (hub)
                                                ▲ long-poll (un task la ~50s)
PC-ul TĂU (pc_bridge.py) ── execută HTTP local ──┘  → răspuns înapoi la agent
```

- PC-ul stă în long-poll: **0% CPU, ~15-20 MB RAM, ~2 cereri mínuscule pe minut**.
- Postările noastre ies prin PC → YouTube vede conexiunea ta de acasă.
- **Universal**: orice proiect (azi sau peste un an) poate trimite cereri prin
  același bridge folosind protocolul de mai jos — PC-ul rămâne același „dumb relay".

## Siguranță (2 straturi)

1. **Secret partajat** (`bridge_secret` în `config.json` de pe server): fără el nu
   poți nici lua taskuri, nici livra rezultate, nici cere execuții.
2. **Proxy-lock pe PC**: `pc_bridge.py` execută **doar** cereri spre
   `*.youtube.com`, `*.googleapis.com`, `*.ggpht.com`, `*.ytimg.com`.
   Orice altceva e refuzat *de PC* — chiar dacă cineva ar compromite serverul,
   PC-ul tău nu poate deveni proxy general spre internet.

## Pornire rapidă

1. **Pe server** (o dată): `deploy/INSTALL-VPS.sh` generează automat
   `bridge_secret` în `config.json`. Sau manual: `"bridge_secret": "<hex-16>"`.
2. **Pe PC** (o dată): rulează `deploy\INSTALEAZA-BRIDGE.bat` — îți cere
   serverul și secretul, instalează în pornire automată și pornește acum.
3. În dashboard, sus, apare **„🌉 PC Bridge ONLINE (NUME-PC)"**. Din acel moment
   publicarea trece automat prin PC (`publish_via_bridge: true`). Bridge oprit?
   Postarea iese direct de pe server — **nimic nu se pierde**.

## Protocol HTTP (pentru ORICE proiect)

Toate rutele sunt servite de dashboard (`http://SERVER:8787`), fără cookie de
login — cheia e `bridge_secret`.

### 1. `GET /bridge/poll?name=PC-1&agent=NUME-PROIECT&wait=50`
Header: `X-Bridge-Key: SECRET`. Long-poll (max ~55s). Răspuns:
```json
{"task": null}
// sau
{"task": {"id": "abc...", "url": "https://...", "method": "POST",
          "headers": {...}, "body_b64": "...", "timeout": 35, "project": "postsyt"}}
```

### 2. `POST /bridge/result`
```json
{"secret": "SECRET", "id": "abc...", "status": 200,
 "headers": {"Content-Type": "application/json"},
 "body_b64": "e30="}
```
`status: 0` + `"error": "text"` semnalează eșec local (proxy-lock, timeout DNS etc.).

### 3. `POST /api/bridge/request` — modul SINCRON (cel mai ușor pt. alte proiecte)
Nu trebuie să implementezi polling: trimiți cererea, primești răspunsul.
```json
=> {"secret": "SECRET", "url": "https://www.youtube.com/feed/trending",
    "method": "GET", "headers": {"Accept": "text/html"},
    "body_b64": "", "timeout": 40, "project": "proiectul-meu"}
<= {"status": 200, "headers": {...}, "body_b64": "..."}
```
Erori: HTTP 403 cu `{"status":0,"error":"secret invalid"}`.

### 4. `GET /api/bridge/status?secret=SECRET` (sau header `X-Bridge-Key`)
```json
{"bridges": [{"name": "PC-ACASA", "agent": "postsyt",
              "online": true, "last_seen_ago_s": 12}],
 "publish_via_bridge": true, "queue_len": 0}
```

## Client generic în 15 linii (refolosibil în orice agent/proiect)

```python
import base64, json, urllib.request

SERVER, SECRET = "http://IP-SERVER:8787", "bridge_secret-din-config"

def prin_pc(url, method="GET", headers=None, data=None, timeout=40):
    """Execută această cerere pe PC-ul de acasă și întoarce body-ul (bytes)."""
    payload = json.dumps({"secret": SECRET, "url": url, "method": method,
        "headers": headers or {}, "timeout": timeout, "project": "numele-proiectului",
        "body_b64": base64.b64encode(data or b"").decode()}).encode()
    req = urllib.request.Request(SERVER + "/api/bridge/request", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 20) as r:
        res = json.loads(r.read())
    if res.get("status", 0) == 0:
        raise ConnectionError(res.get("error", "bridge indisponibil"))
    if res["status"] >= 400:
        raise RuntimeError(f"HTTP {res['status']} prin bridge")
    return base64.b64decode(res.get("body_b64") or b"")
```

## Implementarea de referință (PC)

`bridge/pc_bridge.py` — stdlib only (niciun `pip install`), ~160 de linii:
long-poll → proxy-lock → execuție `urllib` → `POST /bridge/result` → reconnect
cu backoff exponențial (2s → 60s). Se configurează cu `postsyt-bridge.ini`
(scris automat de `INSTALEAZA-BRIDGE.bat`).

## Întrebări frecvente

- **Cât consumă pe PC?** ~15-20 MB RAM, 0% CPU când e idle, un ping mic pe ~25s
  în medie (un poll lung la 50s + taskurile propriu-zise). Neglijabil.
- **Ce se întâmplă când PC-ul e închis/resetat?** Bridge-ul apare „offline",
  agentul publică direct de pe server; la repornire se reconectează singur
  (e în Task Scheduler + retry intern în buclă).
- **Pot opri trecerea prin bridge fără să-l opresc pe PC?**
  Da: `publish_via_bridge: false` în `config.json` (se păstrează pentru alte proiecte).
- **Pot avea 2 PC-uri bridge?** Da — nume diferite; primul care ia taskul îl execută.
- **Vreau ca alt proiect să NU folosească bridge-ul.** Nu-i dai secretul. Atât.
