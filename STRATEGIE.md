# 🎯 STRATEGIE — research + ce am furat de la cei mai buni + cum e implementat

*Cercetare făcută pe 2026-10-04: articole de strategie (vidIQ, AIR Media-Tech, Opus.pro,
FluxNote), comunitatea Make/Reddit, proiecte open-source reale (FS Poster, ReClip,
YoutubeCommunityScraper, comment-bots) și canalele-tintă (Jocuri Horror, trending gaming RO).*

---

## 1. Adevărul tehnic: cum se postează AUTOMAT pe Community

**API-ul oficial YouTube Data API v3 NU are endpoint pentru postări Community** (confirmat în
documentație și de comunitatea Make.com). Toate tool-urile serioase folosesc una din două metode:

| Metodă | Cine o folosește | Plusuri / minusuri |
|---|---|---|
| **`backstage/create_post` (InnerTube) + SAPISIDHASH** | FS Poster (plugin comercial WP), extensia ReClip, comment-boturile | ✅ instant, headless, text+imagini ✅ metodă dovedită în producție ⚠️ sondajele native nu-s documentate |
| **Playwright/Selenium pe UI-ul real** | comment-boturile (y-t-bot), SeleniumBase/Driver-ului | ✅ sondaje reale, orice face site-ul ⚠️ fragil la schimbări de UI, mai lent |

**Ce am implementat:** ambele. `innertube.py` = postări text/imagine instant (chiar forma
din codul FS Poster: `createBackstagePostParams` luat din pagina /community, upload imagini prin
`channel_image_upload/posts` → `encryptedBlobId`, semnătură `SAPISIDHASH ts_sha1(ts SAPISID origin)`);
`studio_bot.py` = sondaje native prin browser; fallback elegant: sondaj-ca-imagine cu vot prin
comentarii (aceeași mecanică de engagement).

## 2. Ce face canale ca @JocuriHorrorSky să explodeze pe Community

### ⭐ Insight-ul cheie: postările apar direct în feed-ul de SHORTS

Community posts nu stau doar în tab-ul Community — YouTube le bagă **între Shorts-uri, în
același feed de scroll**. Adică postarea stă în aceeași conductă cu traficul cel mai mare de pe
platformă. De aceea „Bober” (un cuvânt + o imagine) a luat 7.8K like-uri: lumea nu l-a căutat,
i-a apărut în față ca orice Short. Reguli derivate (toate aplicate de agent):

- **hook în primele 1–2 rânduri** (≤160 caractere) — restul e sub „expand” și nu-l vede nimeni
- **imagine pătrată 1080×1080** mare, lizibilă pe mobil — exact ce generează ImageMaker
- **opțiuni de sondaj ≤45 caractere** — vot dintr-o singură privire, ca pe un Short
- **linkul mereu LA FINAL** — nu împinge conținutul sub fold
- **efect compus cu Shorts-urile proprii**: Short (#pokecity) → viewer nou → postare în feed →
  click pe episodul lung. Shorts-urile și postările se amplifică reciproc în același feed.

Din 8 postări reale citite azi de pe /posts-ul lui (4.1K–7.8K like-uri fiecare):

1. **Meme-ul banal bate totul** — postarea „Bober” (un cuvânt + o imagine amuzantă):
   **7.863 like-uri, 456 comentarii**. → Tipul D al agentului (meme cards).
2. **Întrebările DA/BA despre viitorul conținut** („Fac EPISODUL 2 din Jocul cu VOCILE ? 👀”):
   5–8K like-uri + sute de comentarii. → Tipul E al agentului.
3. **Teasere cu zi precisă** („➡️Apare SAMBATA !!!”), **anunțuri de live/oră exactă**
   („ASTAZI LA ORA 20:00 …”). → teaserul pre-live automat (marți/joi/sâmbătă 17:15).
4. **Mulțumiri comunității** („Va MULTUMESC MULT pentru toata sustinerea 🤗💗”).
   → în banca de conținut (rotație ocazională).
5. Toate postările lui **au imagine**. Niciodată text singur.

## 3. Strategii validate de research (cu surse)

- **Frecvența:** 2–3 postări/săptămână e optimul clasic; **max 1–2/zi** — peste, reach-ul
  scade și YouTube poate da restricții temporare (vidIQ). Noi mergem **max 3/zi cu gap ≥90 min**
  doar în fazele de lansare (canal mic = trebuie volum, dar controlat).
- **Sondajele = cel mai mare reach** pe Community; AIR Media: +26% engagement într-o lună la
  frecvență săptămânală legată de conținut. → Tipul C zilnic.
- **„Feed warming” 24–48h pre-upload:** un sondaj/post cu 24h înainte de clip **crește reach-ul
  timpuriu al clipului cu 5–15%** (FluxNote) — cine votează azi primeşte clipul în home mâine.
  → Agentul programează teaserul/postul de seară înainte de sloturile în care publici video.
- **Orele de aur gaming:** seară (audiența RO e activă 17:00–21:00; studiul Opus pe 242K clipuri
  gaming: peak UTC 18–21 = 21–24 RO... dar pentru copii/adolescenți RO peak-ul real e 16–20).
  → sloturi default **12 / 16 / 19 / 21**, rafinate automat cu orele observate la Jocuri Horror.
- **„Rule of 4” + decizii de 1 secundă la sondaje** (SocialWick): întrebări simple, max 4
  variante scurte, câteodată cu imagine. → toate sondajele agentului au 3–4 variante ≤60 chars.
- **Sondaje care expiră în 24h** creează urgență (vidIQ best practice 4) → C zilnic = mereu proaspăt.
- **Mix de formate** (polls > GIF/imagine > clipuri > text) — niciodată un singur tip (vidIQ).
  → rotirea A/B/C/D/E.
- **Comentariile contează:** creatorii care răspund cresc retenția — postările agentului cer
  explicit comentarii („Zi-mi în comentarii…”), și replica ca-s-sondaj contează voturile din comments.

## 4. Ce „inventează de la alți youtuberi dar editează varianta ta” (tipul B)

- **Surse:** /gaming/trending + feedurile celor 16 creatori RO din lista ta + viteza
  (views/oră) ca să prindem subiectele în urcare, nu doar cele mari.
- **Morphing:** extragem subiectul/tema („vampir în Minecraft”, „Steal an Egg”, „GTA stunt”),
  rescriem o postare originală legată de **PokeCity** („Văd că toată scena vorbește despre X…
  la noi pe server ar fi nebunie — cine vrea episod?”) + link la clipul tău.
- **Gard anti-plagiat:** similaritate Jaccard cu titlul sursei < 0.45, altfel regenerare pe șablon.
- **Anti-spam subiect:** același trend nu se re-morph-ează (registry în DB).

## 5. Ritmul „la aceeași oră cu Jocuri Horror” (mirror)

1. Scanăm /posts-ul lui la fiecare 20 min.
2. Postare nouă detectată → **planificăm instant** una dintre C/D/E la `+45 min` (cu jitter),
   în limita caps-urilor. Canalul tău nu pare mort niciodată când el e activ.
3. În fundal, **histograma orelor lui** (Style Lab din dashboard) actualizează automat
   `learned_hours` → sloturile tale devin din ce în ce mai precis „ale lui”.

## 6. Planul de creștere care rezultă (complet automat)

```
O zi obișnuită (max 3 postări):
  12:00  ❓/😂  întrebare sau meme (D/E)        ← feed warming
  16:00  🔥 B   trend adaptat (dacă există fierbinte) + link ultimul clip
  19:00  📊 C   sondajul zilnic (+link „până votezi, vezi clipul nou”)
+ instant oricând: 🎬 A la fiecare video/live nou (primul video = mereu anunțat)
+ marți/joi/sâmbătă 16:45: 🔴 teaser live la 18:00
+ mirror: ori de câte ori postează Jocuri Horror → +45min una de-a noastră (în caps)
```

Metrici de urmărit în YouTube Studio (o dată/săptămână): voturi/sondaj, comentarii/post,
share-uri, click-uri din posts pe clipuri (Traffic sources → Posts). Dacă un tip depășește
celelalte constant, urcă-i frecvența în config.

## 7. Roadmap opțional (dacă vrei nivelul următor)

- citire automată „când sunt fanii tăi online” din YouTube Studio → recalibrare ore
- A/B testing de hook-uri pe săptămâni (două formulări, păstrezi câștigătoarea)
- roboțel care-ți răspunde la primele 5 comentarii ale fiecărui post (urcă engagementul)
- legare sondaje de calendarul de upload (știi când scoți episodul → poll exact cu 24h înainte)
