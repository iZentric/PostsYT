# 🌉 PC Bridge — pachetul tău personal (citește-mă întâi)

## Ce ai în pachet

| Fișier | La ce folosește |
|---|---|
| `pc_bridge.py` | Releul care rulează pe PC-ul tău (doar Python stdlib, ~15-20 MB RAM, 0% CPU) |
| `INSTALEAZA-BRIDGE.bat` | Dublu-click = instalează + pornire automată Windows + pornește ACUM |
| `PROMPT-UNIVERSAL.md` | **Comoara**: text gata de lipit în ORICE chat cu un agent AI → agentul îți folosește PC-ul imediat |
| `BRIDGE-PROTOCOL.md` | Documentația completă a protocolului (pentru curioși / proiecte proprii) |

## Instalare în 60 de secunde

1. Dublu-click `INSTALEAZA-BRIDGE.bat` (pc_bridge.py trebuie să fie lângă el ✅)
2. Completezi cele 2 valori de mai jos (le ai deja, sunt ale tale)
3. La „nume" apeși doar Enter

## Valorile tale (copiază-le exact)

### Pentru agentul PostsYT care rulează PE PC-UL TĂU (test local)
```
SERVER = http://127.0.0.1:8787
SECRET = d61a087bbd162d9692d0b96850ebd04a
```

### Pentru testul WOW chiar acum: conectează PC-ul la sandboxul meu cloud
*(vezi cu ochii tăi cum PC-ul tău apare „ONLINE" în dashboardul live din browserul tău — hub-ul e în cloudul Arena, execuția e pe PC-ul tău)*
```
SERVER = https://8787-i959etlo29pm9myd7oy3v.e2b.app
SECRET = d61a087bbd162d9692d0b96850ebd04a
```
⚠️ Sandboxul e temporar (moare la finalul sesiunii) — e DOAR demo.

### Pentru folosirea REALĂ 24/7 (după ce instalăm serverul Oracle Free)
```
SERVER = http://IP-UL-VPS-ULUI:8787
SECRET = <cel afișat de installer la final>
```
Le înlocuiești ulterior în `%USERPROFILE%\PostsYT-Bridge\postsyt-bridge.ini` (2 rânduri, atât).

## Siguranță (rezumat)

- Fără `SECRET`, nimeni nu-ți poate trimite taskuri.
- PC-ul execută **doar** domenii YouTube/Google — restul le refuză singur.
- Oprire oricând: Task Scheduler → „PostsYT PC Bridge" → Dezactivează.

## Când vrei ca un ALT agent (alt chat) să-ți folosească PC-ul

Deschizi `PROMPT-UNIVERSAL.md`, copiezi blocul și-l lipești ca prim mesaj.
Gata — agentul știe protocolul, regulile și are codul de client.
