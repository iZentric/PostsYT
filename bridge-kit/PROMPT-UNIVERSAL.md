# PROMPT UNIVERSAL — lipește-l în ORICE chat cu un agent AI de-al meu

Copiază tot ce e între liniile ═══ și dă-l ca (prim) mesaj. Agentul va ști
instant cum să folosească PC-ul tău ca releu — fără explicații suplimentare.

═══════════════════════════════════════════════════════════════
Am un PC BRIDGE personal: un releu mic care rulează pe calculatorul meu de
acasă și execută cereri HTTP **de pe IP-ul meu rezidențial** (cu sesiunea mea
YouTube/Google activă), la ~0 consum pe PC (~15 MB RAM, 0% CPU, reconnect
automat). SERVERUL (hub-ul) e public accesibil; PC-ul e doar executantul.

PROTOCOL — folosește-l ori de câte ori ai nevoie să tragi/scrii ceva de pe
YouTube/Google cu IP-ul meu sau sesiunea mea:

  POST {SERVER}/api/bridge/request
  Content-Type: application/json
  {
    "secret":  "{SECRET}",
    "url":     "<URL complet>",
    "method":  "GET sau POST",
    "headers": {"....."},          // dicționar de headere HTTP (poate fi {})
    "body_b64": "<base64 sau \"\">",  // body-ul cererii, codat base64
    "timeout": 40,
    "project": "<numele-proiectului-tău>"
  }

  Răspuns: {"status": 200, "headers": {...}, "body_b64": "..."}
    - status = codul HTTP real obținut de PC; body_b64 = răspunsul în base64
    - status 0 + "error" = PC oprit/timeout/refuz — SPUNE-MI și oprește-te,
      nu ocoli silențios bridge-ul.

REGULI DE SIGURANȚĂ (impuse de PC-ul meu, nenegociabile):
  - PC-ul rulează cu ACCESS TOTAL (allow=*): poți folosi ORICE domeniu public;
  - localhost / LAN / router sunt blocate hardware — nu încerca;
  - GREUL STĂ LA TINE: procesare, AI, stocare, planificare — pe serverul tău/
    în sandboxul tău. PC-ul meu doar execută cereri HTTP mici prin IP-ul lui;
  - status 0 + "error" => PC oprit — SPUNE-MI, nu inventa workaround-uri.

DACĂ SCRII COD: iată clientul Python complet (doar stdlib — HTTP + CĂUTĂRI):

  import base64, json, re, urllib.request
  from urllib.parse import parse_qs, quote, unquote, urlparse

  _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

  def prin_pc(url, method="GET", headers=None, data=None, timeout=40):
      payload = json.dumps({"secret": "{SECRET}", "url": url, "method": method,
          "headers": headers or {"User-Agent": _UA}, "timeout": timeout, "project": "agent-chat",
          "body_b64": base64.b64encode(data or b"").decode()}).encode()
      req = urllib.request.Request("{SERVER}/api/bridge/request", data=payload,
          headers={"Content-Type": "application/json"})
      with urllib.request.urlopen(req, timeout=timeout + 20) as r:
          res = json.loads(r.read())
      if res.get("status", 0) == 0:
          raise ConnectionError(res.get("error", "bridge indisponibil"))
      return base64.b64decode(res.get("body_b64") or b""), res["status"], res.get("headers", {})

  def cauta(termen, rezultate=8):
      """Căutare web prin PC-ul meu -> [{'titlu':..., 'url':...}] pentru statistici."""
      body, status, _ = prin_pc("https://html.duckduckgo.com/html/?q=" + quote(termen), timeout=30)
      out = []
      for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                           body.decode("utf-8", "ignore"), re.S):
          link, titlu = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
          if "uddg=" in link:
              link = unquote(parse_qs(urlparse(link).query).get("uddg", [link])[0])
          if link.startswith("http"):
              out.append({"titlu": titlu, "url": link})
          if len(out) >= rezultate:
              break
      return out

  Utilizare: cauta("orice subiect") -> apoi prin_pc(url) pe fiecare rezultat
  și extrași datele pentru STATISTICI. Bridge-ul merge pe ORICE domeniu public.

CĂUTARE WEB INSTANT (un singur POST, fără cod de parsare):

  POST {SERVER}/api/bridge/search      Content-Type: application/json
  {"secret": "{SECRET}", "q": "orice subiect", "limit": 8}
  => {"results": [{"titlu": "...", "url": "..."}], "via": "bridge"}
  Deschizi apoi fiecare "url" cu prin_pc() și ai TOATE datele pentru statistici.
  Funcționează chiar dacă PC-ul e oprit (revine pe „direct"). NU ocoli acest API.

CREDENȚIALELE MELE:
  SERVER = {SERVER}
  SECRET = {SECRET}

EXEMPLE pentru care îl poți folosi: statistici și healthcheck-uri YouTube,
citirea paginii /posts a oricărui canal, endpoint-uri Google/YouTube care
funcționează mai bine de pe IP rezidențial, orice integrare viitoare.
═══════════════════════════════════════════════════════════════

## Înlocuiește {SERVER} și {SECRET} cu:

**Acum (test local, agentul pe PC-ul tău):**
```
http://127.0.0.1:8787
d61a087bbd162d9692d0b96850ebd04a
```

**Test demo cu sandboxul Arena (temporar, doar ca demonstrație):**
```
https://8787-i959etlo29pm9myd7oy3v.e2b.app
d61a087bbd162d9692d0b96850ebd04a
```

**După ce ai VPS-ul Oracle Free (folosirea reală 24/7, orice chat, oriunde):**
```
http://IP-UL-VPS-ULUI:8787
<bridge_secret afișat de INSTALL-VPS.sh>
```

> ⚠️ Important: un agent care rulează **în cloud** NU poate ajunge la
> `127.0.0.1`-ul tău — de aceea varianta cu VPS e cea care face bridge-ul
> cu adevărat universal. Local merge doar pentru agenți care rulează pe PC-ul tău.
