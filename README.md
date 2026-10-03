# ⚡ PostsYT — agentul de postări YouTube Community al lui iSentric

Agent autonom care îți ține canalul viu între uploaduri: **generează, programează și publică**
postări pe tab-ul Community (text + imagine + sondaje + link), urmărind:

1. **Regula de aur** a fiecărei postări: **hook** (întrebare/frază amuzantă) + **visual**
   (imagine/sondaj/meme) + **link** (ultimul video; opțional un evergreen cu potențial).
2. **Ritmul lui @JocuriHorrorSky** — îi citim /posts-ul din 20 în 20 de minute; când postează
   el, programăm și noi una la `mirror_delay_minutes` (implicit 45 min). Plus orele lui de aur
   învățate automat în *Style Lab*.
3. **Trendurile** — YouTube Gaming Trending + clipurile cu cea mai mare viteză (vizualizări/oră)
   la 16 creatori RO din lista ta. Le *adaptăm* în stilul tău (nu copiem — gard anti-plagiat).
4. **Research-ul strategiilor** → vezi **[STRATEGIE.md](STRATEGIE.md)** (de ce sondaje zilnice,
   de ce 24h pre-upload, ce formate câștigă, la ce ore).

---

## 🚀 Quickstart pe PC (Windows, 5 minute)

1. **Instalează Python 3.10+** de pe [python.org/downloads](https://www.python.org/downloads/)
   → la instalare **bifează ✅ „Add Python to PATH”** (foarte important!).
2. **Descarcă proiectul:** butonul verde „Code → Download ZIP” din
   [GitHub — repo-ul tău PostsYT](https://github.com/iZentric/PostsYT) (sau `git clone …`) → extragi undeva, ex. `C:\PostsYT`.
3. **Dublu-click pe `PORNESTE-POSTSYT.bat`** — atât:
   - prima dată îți deschide browser să te loghezi pe YouTube (1 singură dată),
   - apoi pornește **agentul + dashboardul** la adresa **http://localhost:8787**.

Lasă fereastra neagră deschisă cât vrei să posteze automat. O închizi → se oprește.
Vrei să posteze și noaptea? Lasă PC-ul pornit peste noapte, sau pune-l pe un mini-PC/VPS.

## 🌐 Rulează 24/7 FĂRĂ PC-ul tău (recomandat dacă îl resetezi/stingi des)

Agentul pe un mini-server = postează non-stop, indiferent de PC-ul tău.
**Ghid complet pas-cu-pas: [docs/VPS.md](docs/VPS.md)** (Oracle Cloud Free Tier = GRATIS,
sau Hetzner/Contabo ~€4/lună). Pe server, o singură comandă instalează tot:

```bash
curl -sSL https://raw.githubusercontent.com/iZentric/PostsYT/arena/01a103b1-postsyt/deploy/INSTALL-VPS.sh | sudo bash
```

→ repo + Python + servicii systemd (repornire automată la crash) + dashboard protejat cu token secret.
Varianta gratuită pe PC: `deploy/INSTALEAZA-PORNIRE-AUTOMATA.bat` (pornește singur la fiecare boot Windows).

### Opțional (recomandat pentru calitate maximă)
Deschide `PORNESTE-POSTSYT.bat` cu Notepad și șterge `REM ` din fața rândului cu
`pip install pillow cairosvg playwright` → imagini PNG reale la upload + sondaje native.

### Linux / macOS
```bash
chmod +x PORNESTE-POSTSYT.sh && ./PORNESTE-POSTSYT.sh
```

### 2. Autentificare (o singură dată)

YouTube **nu are API oficial** pentru postări Community — de aceea agentul folosește aceeași
sesiune ca browserul tău (metodă folosită de toate uneltele serioase de autoposting, ex. FS Poster).

Varianta ușoară:
```bash
python -m postsyt login        # se deschide un browser, te loghezi pe Google, gata
```

Varianta manuală: instalează extensia **Cookie-Editor** / **EditThisCookie**, intră logat pe
youtube.com, exportă cookie-urile ca *Netscape* și salvează în `data/cookies.txt`.

Verifică tot:
```bash
python -m postsyt doctor
```
Trebuie să vezi `✅ sesiune YouTube: Autentificat`.

### 3. Pornește

```bash
python -m postsyt dashboard    # centru de comandă web (aprobare / editare / publicare)
python -m postsyt daemon       # agentul care lucrează singur 24/7 (alt terminal)
```

Sau totul-într-unul pe un PC/laptop care stă deschis. Pe VPS (recomandat pentru non-stop):
`nohup python -m postsyt daemon &`

### 4. Mod manual 100% sigur (fără login)

Setează în `config.json` `"publish_driver": "queue"` → agentul generează totul, tu dai doar
*Copy* din dashboard și lipești în YouTube Studio. Zero automatizare pe cont, zero risc.

---

## 🧠 Ce generează agentul (5 tipuri)

| Tip | Ce e | Când |
|---|---|---|
| 🎬 **A — Anunț video** | hook + card cu titlul/subtitlul + link direct la clip | instant când RSS-ul vede video/live nou (la prima rulare anunță și ultimul video — *„mereu primul video postat ca post”*) |
| 🔥 **B — Trend adaptat** | subiect viral gaming/competitor rescris în stilul PokeCity + link | 1/zi, dacă există trend fierbinte |
| 📊 **C — Sondaj** | întrebare Minecraft + 2-5 variante (engagement maxim) | zilnic la 19:00 (sau orele învățate) |
| 😂 **D — Meme** | card meme despre viața de gamer/PokeCity (efectul „Bober”: 7.8K like-uri) | seară, alternat cu E |
| ❓ **E — Întrebare** | „Facem episod cu X?” — exact tactica lui Jocuri Horror | seară, alternat cu D |

Bonus automat: 🔴 **teaser pre-live** în zilele de live (marți/joi/sâmbătă, cu ~75 min înainte de 18:00).

Toate postările respectă caps: **max 3/zi**, **gap ≥ 90 min**, **fără postări noaptea (00–08)** —
conform best-practices (spam-ul omoară reach-ul și poate atrage restricții).

## 🧠 Creierul (AI)

- Implicit: **template engine offline** românesc, antrenat pe stilul tău real (PokeCity,
  Nocivanu, emoji, CTA-uri) + exemplarele de top ale lui Jocuri Horror. Merge 100% fără chei.
- Cu LLM (opțional): pune cheia în env `OPENAI_API_KEY` și `"llm_enabled": true`.
  Merge orice endpoint OpenAI-compatibil (OpenAI, Groq, OpenRouter, Ollama local) prin
  `llm_base_url` + `llm_model`.

## 🖥️ Dashboard

- **Drafturi** cu preview imagine, edit inline, ✔ Aprobă / 🚀 Publică acum / ✖ Sari
- **Ultimul video** (thumbnail live), **KPI** (drafturi, publicate azi, următorul slot)
- **Style Lab**: exemplarele reale cu like-uri de la @JocuriHorrorSky + histograma orelor lui
- **Trenduri gaming** cu viteză (views/oră) și **jurnal** de evenimente

## ⚙️ config.json — cele mai importante setări

| cheie | implicit | ce face |
|---|---|---|
| `autopublish` | `false` | `true` = publică direct fără aprobare (recomand numai după ce testezi) |
| `publish_driver` | `innertube` | `innertube` (automat real) / `queue` (manual copy-paste) |
| `max_posts_per_day` | `3` | plafon zilnic total |
| `mirror_channel` | `@JocuriHorrorSky` | pe cine oglindim ritmul |
| `competitors` | 16 canale | lista ta de youtuberi RO (se adaugă/șterg liber) |
| `poll_hours` | `[19]` | ora sondajului zilnic |
| `live_days` / `live_hour` | marți/joi/sâmbătă / 18 | programul tău de liveuri |

## 🔬 Cum funcționează sub capotă (pe scurt)

- **Trigere:** RSS Atom (`feeds/videos.xml?channel_id=…`) pentru canalul tău + competitori;
  scraping `ytInitialData` pentru /gaming/trending și pentru /posts-ul sursei de stil.
- **Publicare:** endpoint-ul intern folosit și de site-ul YouTube (`backstage/create_post`),
  semnat cu `SAPISIDHASH` derivat din cookie-urile tale (exact metoda open-source a
  pluginului FS Poster și a extensiei ReClip). Imaginile se încarcă prin
  `channel_image_upload/posts` (encryptedBlobId). Sondajele native: via Playwright în
  composer-ul real; fallback automat — sondaj-ca-imagine cu vot în comentarii.
- **Anti-spam & anti-plagiat:** caps zilnice, gap minim, dedupe 48h pe hash de text,
  verificare similaritate Jaccard < 0.45 față de titlul sursei pentru tipul B.

## ⚠️ Onestitate & siguranță

- Postările Community automat nu au API oficial; metoda InnerTube e cea folosită de industrița
  de autoposting, dar **nu e garantată de Google** — dacă YouTube își schimbă internele, doctorul
  îți va arăta ce s-a stricat. Păstrează `autopublish: false` până vezi că primele postări
  publicate de agent arată perfect.
- Nu posta mai mult de 3/zi (agentul are caps implicite corecte) — YouTube poate pune
  restricții temporare la frecvență mare.
- Agentul **nu copiază** conținutul altor creatori: doar detectează ce e în trend și scrie
  postări originale în stilul tău — exact ce ți-ai dorit („copieze dar să editeze varianta mea”).

## 📁 Structura

```
postsyt/
├── feeds.py        # RSS Atom parser (stdlib)
├── trends.py       # gaming trending + viteza competitorilor
├── stylelab.py     # citește /posts-ul competitorilor, învață orele
├── brain.py        # generator A/B/C/D/E (template RO + LLM opțional)
├── content_banks.py# formulări românești în stilul canalului
├── imagemaker.py   # cards SVG/PNG 1080x1080 brand
├── innertube.py    # publicarea (SAPISIDHASH + create_post + upload imagini)
├── studio_bot.py   # sondaje native via Playwright + captură cookies
├── publisher.py    # alege driverul, fallback-uri
├── agent.py        # orchestrare: scan → generează → programează → publică
├── scheduler.py    # sloturi, quiet hours, caps
├── dashboard.py    # web UI (stdlib)
└── cli.py          # init/doctor/login/tick/daemon/dashboard/publish/generate/demo
```

Teste: `python -m unittest discover -s tests -v` (19 teste).
