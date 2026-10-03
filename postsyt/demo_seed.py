"""Seed demo: date REALE culese la 2026-10-04 (feed iSentric + /posts Jocuri Horror +
trending gaming). Permite previzualizarea completă a agentului fără internet."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Exemplar, Trend, Video
from .util import iso, utcnow

# ---------------- videoclipurile reale iSentric (din feedul Atom, 2026-10-04)
VIDEOS = [
    ("n0wjz5kTAtI", "POKEMONII ĂȘTIA SUNT PREA INTELIGENȚI?! 🧠 #minecraft #pokecity #shorts",
     "2026-10-03T11:53:11+00:00", 0, False, True),
    ("o4atrxEkiUU", "O SA FIU JUDECAT IN MINECRAFT ?! POKECITY?! 😱",
     "2026-10-01T13:44:50+00:00", 0, False, False),
    ("waLxtsQAEZ8", "POKECITY?! 😱 AM PRINS UN LEU IN NETHER !",
     "2026-09-30T10:08:35+00:00", 0, False, False),
    ("pl3ik3aXuOw", "POKECITY?! POKEMONUL S-A TRANSFORMAT ?!",
     "2026-09-29T11:14:02+00:00", 0, False, False),
    ("AM4nPoUOrao", "GAINA ZBURATOARE ?! POKECITY?! 😱",
     "2026-09-28T15:36:03+00:00", 0, False, False),
    ("YsHdthL-Coo", "AM GASIT DIAMANTE in PESTERA ! 😱 PokeCity",
     "2026-09-28T11:12:04+00:00", 0, False, True),
    ("sIwsG4aMvEc", "Final tragic în Pokecity: Am murit! 🌋 #minecraft #pokecity #romania",
     "2026-09-25T18:59:06+00:00", 0, False, False),
    ("ZcSy0AyrDWQ", "🔴 CONSTRUIM CAMERA CU GOLEMI DE COPRU în POKECITY!",
     "2026-09-18T16:30:18+00:00", 0, True, False),
]

# ---------------- postările reale Community ale lui @JocuriHorrorSky (2026-10-04)
EXEMPLARS = [
    ("Bober", 7863, 456, 16),
    ("Episodul 3 din seria cu CASA din spate... este cam nebun 😂 Tatal Strict e pe combinatii, nu pe salvat copilul ala nebun 😂\n➡️Apare SAMBATA !!!", 7411, 370, 19),
    ("Gata de SCOALA ?😎\n➡️Program EPISOADE pe TIMPUL SCOLII:\n👀de LUNI pana VINERI: Episod ZILNIC La ora 18:00 !\n👀SAMBATA-DUMINICA: Episod La ora 12:00 !\n⭐SPOR MAINE in Noul AN SCOLAR !", 6904, 606, 12),
    ("🔥 UNDE o sa fie URMATORUL EPISOD de HIDE and SEEK ??? 👀", 6295, 525, 18),
    ("Fac EPISODUL 2 din Jocul cu VOCILE ? 👀", 5805, 350, 14),
    ("Va MULTUMESC MULT pentru toata sustinerea de la EPISOADE 🤗", 4142, 288, 13),
    ("RIP LED 💀", 3614, 234, 21),
    ("👀 Fac un EPISOD ca sa va arat cum este VIATA de ADMIN ?", 3375, 298, 12),
    ("🔥ASTAZI LA ORA 20:00 o sa fie ADMIN ABUSE + UPDATE pe Jocul Meu: DANCE or DIE 🔥", 3385, 103, 17),
    ("⭐ Cum a fost PRIMA ZI de SCOALA ?", 1174, 229, 17),
]

# ---------------- trending gaming (din pagina /gaming/trending, 2026-10-04)
TRENDS = [
    ("L-am GASIT in Padure pe Roblox !", "Jocuri Horror", 111000, 2800),
    ("Spionul..", "Klorna", 81000, 4400),
    ("CE POTI FACE CU 1 ROBUX...??", "INSANITY", 69000, 1200),
    ("AM GASIT AVIOANE PRABUSITE in GTA 5!", "Mario Robert", 58000, 441),
    ("CAT de SUS pot URCA MASINILE in GTA 5?", "Amasico Playz", 36000, 1200),
    ("Am mers SUS pe Luna !", "Bonus SKY", 75000, 1400),
    ("NE-AM FACUT de RAS 😭", "Silentiosu'", 69000, 1300),
    ("Imita ANIMALUL sa SUPRAVIETUIESTI!", "Nocivanu'", 31000, 128),
    ("ADOPTAT de REGELE GORILĂ în Steal an Egg!", "Zoomy", 1300000, 97600),
    ("M-am transformat în VAMPIR ca să EVADEZ din ÎNCHISOAREA FETELOR în Minecraft!", "Dagar", 1800000, 51000),
    ("How I Saved the World's Largest Minecraft Server", "Wemmbu", 21000000, 22900),
    ("TOATE SECRETELE ASCUNSE DIN EVENTUL GUS SI PASS GRATIS?!", "Madalin", 30000, 635),
    ("I Found My 13 Year Old Minecraft World", "MrBeast Gaming", 34000000, 141300),
    ("Escaping the Minecraft Underworld", "Parrot", 6600000, 6000),
    ("Sunt *2 CRIMINALI* ... ?! (EP.5)", "MARIUS IANCU Plays", 32000, 216),
    ("Revizitez SMPURI UITATE !", "zaSami", 91000, 139),
]


def seed(cfg, store, agent):
    now = utcnow()
    for vid, title, pub, views, is_live, is_short in VIDEOS:
        v = Video(video_id=vid, channel_id=cfg.own_channel_id,
                  channel_title=cfg.channel_name, title=title,
                  url=f"https://www.youtube.com/watch?v={vid}",
                  published=datetime.fromisoformat(pub),
                  views=None, is_live=is_live, is_short=is_short)
        store.add_video(v)
        # toate se consideră deja anunțate — în demo generăm manual
        store.mark_announced(vid)
    # ultima postare a "competitorului" e observată la orele din listă (17:00 e pattern)
    for i, (text, likes, comments, hour) in enumerate(EXEMPLARS):
        ago = timedelta(hours=(i + 1) * 14)
        store.add_exemplar(Exemplar(
            source=cfg.mirror_channel, text=text, likes=likes, comments=comments,
            post_id=f"demo{i}", published_guess=(now - ago).replace(hour=hour)))
    for i, (title, channel, views, vph) in enumerate(TRENDS):
        store.add_trend(Trend(source="gaming_trending", channel=channel, title=title,
                              url=f"https://www.youtube.com/results?search_query={title.replace(' ','+')}",
                              views=views, vph=vph, score=vph, fetched_at=now))
    store.set_kv("learned_hours", [12, 16, 19, 21])
    store.log("🎬 Date demo reale încărcate — 8 clipuri iSentric, 10 exemplare Jocuri Horror, 16 trenduri")

    # generează câte un draft din fiecare tip (vizibile instant în dashboard)
    from .models import KIND_VIDEO, KIND_POLL, KIND_MEME, KIND_QUESTION, KIND_TREND, KIND_RECAP, KIND_SCHEDULE
    for kind in (KIND_VIDEO, KIND_POLL, KIND_MEME, KIND_QUESTION, KIND_TREND, KIND_RECAP, KIND_SCHEDULE):
        agent.force_generate(kind)
    store.log("🧠 7 drafturi demo generate (câte unul din fiecare tip)")
