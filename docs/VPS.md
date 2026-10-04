# 🌐 PostsYT 24/7 — server permanent (PC-ul tău poate fi și STINS)

Varianta recomandată când îți resetezi des PC-ul: agentul trăiește pe un mini-server
care nu se oprește NICIODATĂ. PC-ul îl folosești o singură dată (3 minute) ca să
exporți cookie-urile — atât. Alegerea mea: **Oracle Cloud Free Tier (GRATIS pe viață)**.

---

## 🏆 Varianta A — Oracle Cloud FREE (recomandat, 0 €)

Server ARM gratuit: până la 4 nuclee / 24 GB RAM în „Always Free”. De departe cea mai
bună ofertă de pe piață pentru un bot mic ca al nostru.

1. **Cont gratuit:** intră pe [oracle.com/cloud/free](https://www.oracle.com/cloud/free/)
   → „Start for free” → îți faci cont (îți cere un card pentru verificare, **nu plătești nimic**).
2. **Creează mașina:** din meniu → *Compute → Instances → Create instance*:
   - Name: `postsyt`
   - Image: **Ubuntu 22.04** (sau 24.04)
   - Shape: **VM.Standard.A1.Flex (ARM)** — bifează „Always Free eligible”, 1 CPU / 6GB e ARHI suficient
   - SSH keys: uploadezi cheia ta sau generează una (descarcă fișierul `.key`)
   - *Create instance* → aștepți ~1 min, apare IP-ul public.
3. **Te conectezi** cu Terminal/PowerShell/PuTTY:
   ```bash
   ssh -i cheia-ta.key ubuntu@IP-UL-TAU
   ```
4. **Comanda magică** (o lipești așa cum e):
   ```bash
   curl -sSL https://raw.githubusercontent.com/iZentric/PostsYT/arena/01a103b1-postsyt/deploy/INSTALL-VPS.sh | sudo bash
   ```
   Durează 2-3 minute și îți arată la final **linkul secret al dashboardului tău**.
5. **Deschide portul** (o singură dată): în consola Oracle, la *Instance → Virtual Cloud Network →
   Subnet → Default Security List → Add Ingress Rules*:
   - Source CIDR: `0.0.0.0/0`, Destination Port: `8787`, Protocol: TCP → Save.
6. **Cookie-urile** (ultimul pas — de pe PC-ul tău, în browserul logat pe YouTube):
   - instalează extensia **Cookie-Editor** (Chrome/Edge/Firefox)
   - intră pe `youtube.com` → clik pe Cookie-Editor → **Export → Netscape** (copiază în clipboard)
   - pe server rulezi: `bash /opt/postsyt/app/deploy/install-cookies.sh` → **lipești** → `Ctrl+D`
7. **Verificare finală:**
   ```bash
   cd /opt/postsyt/app && python3 -m postsyt doctor
   ```
   Vrei să vezi `✅ sesiune YouTube: Autentificat`.
8. Gata! Dashboardul: `http://IP-UL-TAU:8787/?key=CHEIA-SECRETA` (o ai în outputul instalării).
   Agentul postează 24/7 chiar dacă PC-ul tău e stins săptămâni întregi. 🎉

---

## 💶 Varianta B — VPS plătit (dacă Oracle e indisponibil în regiune)

Oricare merge (Ubuntu 22.04, 1 CPU/1-2GB RAM):
- **Hetzner CX11** ~€4/lună — cel mai bun raport calitate/preț UE
- **Contabo** ~€4/lună
- **Hostinger/IONOS** oferte de la €1-3/lună

Procedura apoi e IDENTICĂ: ssh → comanda magică de la pasul 4 → port 8787 deschis → cookie-uri.

---

## 🪟 Varianta C — rămâi pe PC, dar imun la reseturi (GRATIS)

Dacă nu vrei server: rulezi o dată fișierul **`deploy/INSTALEAZA-PORNIRE-AUTOMATA.bat`**
→ agentul pornește **singur la fiecare boot/logare** Windows (Task Scheduler).
Resetezi PC-ul de 5 ori pe zi? Agentul revine singur de fiecare dată. Cost: 0 €.

---

## 🔐 Note de siguranță (important!)

- Dashboardul pe server e protejat cu **token secret** (`?key=...`) — nu da linkul nimănui.
- Cookie-urile YouTube = cheia contului tău. Nu le trimite pe email/chat public; stau doar pe serverul tău.
- Dacă îți schimbi parola Google sau te deloghezi din toate sesiunile, re-expotezi cookie-urile (pasul 6).
- Vrei sondaje native (fără fallback)? Re-rulezi instalarea cu
  `sudo WITH_PLAYWRIGHT=1 bash INSTALL-VPS.sh` (descarcă Chromium headless, ~500MB).

## 🔎 Întreținere pe server (15 secunde/ săptămână sau deloc)

```bash
systemctl status postsyt-daemon       # trăiește?
journalctl -u postsyt-daemon -n 50    # ultimele loguri
systemctl restart postsyt-daemon      # restart dacă l-ai blocat
cd /opt/postsyt/app && git pull       # update cod + systemctl restart postsyt-daemon
```

## Actualizări (după instalare)
```
curl -sSL https://raw.githubusercontent.com/iZentric/PostsYT/arena/01a103b1-postsyt/deploy/UPDATE-VPS.sh | sudo bash
```
Singura comandă necesară vreodată pentru a aduce serverul la zi (păstrează configul + datele).
