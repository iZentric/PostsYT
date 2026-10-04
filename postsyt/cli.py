"""CLI PostsYT: python -m postsyt <comanda> [optiuni]"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone


def _build(cfg_path=None):
    from .config import load_config
    from .store import Store
    from .agent import Agent
    cfg = load_config(cfg_path)
    store = Store(cfg.db_path)
    agent = Agent(cfg, store)
    return cfg, store, agent


def cmd_init(args):
    from .config import ROOT, default_config_json
    path = os.path.join(ROOT, "config.json")
    if os.path.exists(path) and not args.force:
        print(f"Există deja {path} (folosește --force ca să suprascrii)")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(default_config_json())
    print(f"✅ Config creat: {path}\n   Editează-l după gust (README.md explică fiecare setare).")


def cmd_doctor(args):
    cfg, store, agent = _build(args.config)
    print("🩺 PostsYT — verificare sistem\n")
    ok = True
    # deps opționale
    for mod, desc in [("PIL", "imagine PNG la upload"), ("playwright", "sondaje native"),
                      ("requests", "HTTP îmbunătățit"), ("yaml", "config YAML")]:
        try:
            __import__(mod)
            print(f"  ✅ {mod} — {desc}")
        except ImportError:
            print(f"  ⚪ {mod} lipsește ({desc}) — opțional")
    # cookies
    from .innertube import AuthError, check_auth, load_cookies
    try:
        cookies = load_cookies(cfg.cookies_file, cfg.cookies_json)
        names = {"SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID"} & set(cookies)
        print(f"  ✅ cookies încărcate ({len(cookies)} buc, chei auth: {', '.join(names) or 'NICIUNA!'})")
        if not names:
            ok = False
        else:
            good, msg = check_auth(cookies)
            print(f"  {'✅' if good else '❌'} sesiune YouTube: {msg}")
            ok = ok and good
    except AuthError as e:
        print(f"  ❌ {e}\n     → soluție: python -m postsyt login  SAU export cookies.txt (vezi README)")
        ok = False
    except Exception as e:
        print(f"  ⚠️  nu am putut testa sesiunea (offline?): {e}")
    # feed
    try:
        from . import feeds
        vids = feeds.fetch_feed(cfg.own_channel_id)
        print(f"  ✅ feed canal: {len(vids)} clipuri (ultimul: «{vids[0].title[:50]}»)" if vids else "  ⚠️ feed gol")
    except Exception as e:
        print(f"  ⚠️  feed canal necitibil acum: {e}")
    print(f"\n  DB: {cfg.db_path}  ·  imagini: {cfg.images_dir}")
    print("\nGata de drum! 🚀" if ok else "\nMai ai câțiva pași de configurare (vezi ❌ de mai sus).")


def cmd_login(args):
    from .studio_bot import capture_login_cookies
    cfg, _, _ = _build(args.config)
    out = capture_login_cookies(cfg.cookies_json)
    print(f"✅ Cookies salvate în {out}\n   Rulează: python -m postsyt doctor (verificare)")


def cmd_tick(args):
    cfg, store, agent = _build(args.config)
    os.environ["POSTSYT_DAEMON"] = "0"
    rep = agent.tick(quick=args.quick)
    print(json.dumps(rep, indent=2, ensure_ascii=False))


def cmd_daemon(args):
    cfg, store, agent = _build(args.config)
    os.environ["POSTSYT_DAEMON"] = "1"
    store.log("🟢 Daemon pornit")
    print("🟢 Daemon PostsYT pornit. Ctrl+C pentru stop.")
    last: dict[str, float] = {"feeds": 0, "mirror": 0, "trends": 0, "plan": 0}
    try:
        while True:
            now = time.time()
            if now - last["feeds"] >= cfg.feed_check_minutes * 60:
                agent.scan_own_feed()
                last["feeds"] = now
            if now - last["mirror"] >= cfg.mirror_check_minutes * 60:
                try:
                    agent.scan_mirror_posts()
                    agent.learn_schedule()
                except Exception as e:
                    store.log(f"mirror scan: {e}", "WARN")
                last["mirror"] = now
            if now - last["trends"] >= cfg.trend_check_hours * 3600:
                try:
                    agent.scan_trends()
                except Exception as e:
                    store.log(f"trend scan: {e}", "WARN")
                last["trends"] = now
            if now - last["plan"] >= 30 * 60:
                agent.plan_daily()
                last["plan"] = now
            agent.publish_due()
            time.sleep(45)
    except KeyboardInterrupt:
        store.log("🔴 Daemon oprit de utilizator")
        print("\n🔴 Oprit.")


def cmd_dashboard(args):
    cfg, store, agent = _build(args.config)
    from .dashboard import run_dashboard
    run_dashboard(cfg, store, agent, port=args.port)


def cmd_publish(args):
    cfg, store, agent = _build(args.config)
    d = store.get_draft(args.id)
    if not d:
        print(f"Nu există draftul #{args.id}")
        return
    res = agent.publisher.publish(d)
    print(res)


def cmd_generate(args):
    cfg, store, agent = _build(args.config)
    kind = args.kind.upper()
    did = agent.force_generate(kind)
    if did:
        d = store.get_draft(did)
        print(f"✅ Draft #{did} creat:\n\n{d.text}\n\n📷 {d.image_path}")
    else:
        print("Nu am putut genera (lipsesc date? fă întâi `tick` cu internet).")


def cmd_demo(args):
    """Seed cu datele reale ale canalului (offline, pentru previzualizare)."""
    cfg, store, agent = _build(args.config)
    from .demo_seed import seed
    seed(cfg, store, agent)
    print("✅ Date demo încărcate (videoclipuri reale iSentric + stil Jocuri Horror + trenduri).")
    print("   Deschide dashboardul:  python -m postsyt dashboard")


def cmd_export_config(args):
    from .config import ROOT
    src = os.path.join(ROOT, "config.example.json")
    print(open(src, encoding="utf-8").read())


def cmd_analytics(args):
    cfg, store, agent = _build(args.config)
    from . import ytanalytics
    res = ytanalytics.get_channel_analytics(cfg)
    print(ytanalytics.format_summary(res))
    if res.get("salvat_in"):
        print(f"\n   💾 JSON complet: {res['salvat_in']}")
    store.log(f"📊 Analytics citit ({len(res.get('video_recente', []))} clipuri, "
              f"surse: {', '.join(res.get('surse', [])) or 'niciuna'})")


def _videoclipuri_pentru_scan(cfg, limita: int) -> list:
    """[{id, titlu}] din analytics (video+shorts), fallback feed RSS."""
    vids = []
    try:
        from . import ytanalytics
        res = ytanalytics.get_channel_analytics(cfg, save=False)
        vids = [{"id": v["id"], "titlu": v["titlu"]} for v in res.get("video_recente", [])]
    except Exception:
        pass
    if not vids:
        try:
            from . import feeds
            vids = [{"id": v.video_id, "titlu": v.title}
                    for v in feeds.fetch_feed(cfg.own_channel_id)]
        except Exception:
            pass
    return vids[:limita]


def cmd_deepstats(args):
    cfg, store, agent = _build(args.config)
    from . import deepstats
    vids = _videoclipuri_pentru_scan(cfg, args.limita)
    if not vids:
        print("❌ Nu am găsit videoclipuri de analizat (internet? cookies?).")
        sys.exit(1)
    print(f"🔬 Analiză adâncă pe {len(vids)} clipuri (transcript: "
          f"{'NU' if args.fara_transcript else 'DA'})...")
    rez = deepstats.depth_scan(cfg, vids, want_transcripts=not args.fara_transcript,
                               top_comentarii=args.comentarii)
    print()
    print(deepstats.format_summary(rez))
    store.log(f"🔬 Deepstats: {rez['total']} clipuri, {rez.get('cu_transcript', 0)} "
              f"cu transcript, {rez.get('intebari_in_top_comentarii', 0)} întrebări")
    print(f"\n💾 JSON complet: {rez['salvat_in']}")


def cmd_comments(args):
    cfg, store, agent = _build(args.config)
    from .comments import Commenter
    c = Commenter(cfg, store=store)
    if args.action == "scan":
        vids = _videoclipuri_pentru_scan(cfg, args.max_videos)
        if not vids:
            print("❌ Nu am găsit videoclipuri de scanat (internet? cookies?).")
            sys.exit(1)
        print(f"🔍 Scanare comentarii pe {len(vids)} clipuri (istoric {args.zile} zile)...")
        rez = c.scan(vids, zile=args.zile, max_pages=args.pagini,
                     doar_fara_raspuns=not args.cu_raspuns)
        print(f"\n💬 {rez['total']} comentarii care așteaptă răspuns "
              f"(din {rez['videoclipuri_scanate']} clipuri). "
              f"Erori: {len(rez['erori'])}")
        for i, t in enumerate(rez["threaduri_raspundibile"][:15], 1):
            print(f"  {i:>2}. {t['autor'][:20]} la «{t['video_titlu'][:36]}» "
                  f"({t['publicat']}): {t['text'][:60]}")
        if rez["total"] > 15:
            print(f"  ... și încă {rez['total'] - 15}")
        print(f"\n💾 Fișier: {rez['salvat_in']}")
        print("   Trimite-mi fișierul ăsta — îți scriu planul de răspunsuri, "
              "tu îl aprobi, apoi: comments reply --plan ...")
    else:  # reply
        import json as j
        if not os.path.exists(args.plan):
            print(f"❌ Nu găsesc planul: {args.plan}")
            sys.exit(1)
        with open(args.plan, encoding="utf-8") as f:
            plan = j.load(f)
        n = len(plan.get("raspunsuri") or [])
        print(f"{'🧪 MOD USCAT — nimic nu se publică' if args.uscat else '📮 Publicare'} "
              f"plan cu {n} răspunsuri (limită zilnică {args.limita})...")
        rez = c.apply_plan(plan, limita_zilnica=args.limita, uscat=args.uscat)
        print(f"\n✅ Postate: {rez['postate']}   Sărite: {rez['sarite']}   "
              f"Erori: {len(rez['erori'])}")
        for e in rez["erori"][:5]:
            print(f"   ⚠️ {e}")


def cmd_upload(args):
    cfg, store, agent = _build(args.config)
    from . import uploader
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    def progress(sent, total):
        pct = int(sent * 100 / total) if total else 100
        print(f"\r   ⬆️  {sent / 1048576:.0f}/{total / 1048576:.0f} MB ({pct}%)",
              end="", flush=True)

    res = uploader.upload_video(
        cfg, args.file, title=args.title, description=args.description or "",
        tags=tags, privacy=args.privacy.upper(), on_progress=progress)
    print()
    if res["ok"]:
        store.log(f"🎬 Upload reușit: {args.file} → {res['url'] or 'procesare în Studio'}")
        if res["url"]:
            print(f"\n🔗 {res['url']}")
        if res.get("eroare"):
            print(f"ℹ️  {res['eroare']}")
    else:
        store.log(f"❌ Upload eșuat ({res['etapa']}): {res['eroare']}", "ERROR")
        print(f"\nDetalii debug: {res.get('debug_path', '?')}")
        sys.exit(1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="postsyt",
                                description="⚡ PostsYT — agent de postări YouTube Community pentru iSentric")
    p.add_argument("--config", help="cale către config.json/yaml", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="creează config.json")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", help="verifică setup-ul (cookies, feed, deps)")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("login", help="deschide browser, salvează cookies.json (Playwright)")
    s.set_defaults(fn=cmd_login)

    s = sub.add_parser("tick", help="o trecere completă (scanări + planificări + publicări)")
    s.add_argument("--quick", action="store_true", help="doar feed propriu + plan + publish")
    s.set_defaults(fn=cmd_tick)

    s = sub.add_parser("daemon", help="rulează continuu (loop)")
    s.set_defaults(fn=cmd_daemon)

    s = sub.add_parser("dashboard", help="pornește dashboardul web")
    s.add_argument("--port", type=int, default=None)
    s.set_defaults(fn=cmd_dashboard)

    s = sub.add_parser("publish", help="publică un draft după ID")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_publish)

    s = sub.add_parser("generate", help="generează manual un draft (A/B/C/D/E)")
    s.add_argument("kind")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("demo", help="seed demo cu datele reale ale canalului (offline)")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("show-config", help="afișează configul exemplu")
    s.set_defaults(fn=cmd_export_config)

    s = sub.add_parser("analytics", help="statisticile REALE ale canalului (abonați, views, Studio 28z)")
    s.set_defaults(fn=cmd_analytics)

    s = sub.add_parser("upload", help="urcă un videoclip pe canal (Studio flow, cookie-urile existente)")
    s.add_argument("file", help="calea către fișierul video (.mp4 etc)")
    s.add_argument("--title", default=None, help="titlul clipului (implicit: numele fișierului)")
    s.add_argument("--description", default="", help="descrierea clipului")
    s.add_argument("--tags", default="", help="taguri separate prin virgulă")
    s.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"],
                   help="vizibilitate (implicit: private — cel mai sigur)")
    s.set_defaults(fn=cmd_upload)

    s = sub.add_parser("comments", help="comentariile canalului: scan + reply (cu plan aprobat)")
    s.add_argument("action", choices=["scan", "reply"],
                   help="scan = adună ce așteaptă răspuns | reply = publică planul aprobat")
    s.add_argument("--zile", type=int, default=60,
                   help="cât de vechi pot fi comentariile (implicit 60 zile)")
    s.add_argument("--max-videos", type=int, default=15,
                   help="câte clipuri recente scanez (implicit 15)")
    s.add_argument("--pagini", type=int, default=4,
                   help="pagini de comentarii per clip (implicit 4 ≈ 80 thread-uri)")
    s.add_argument("--cu-raspuns", action="store_true",
                   help="include și comentariile la care am răspuns deja")
    s.add_argument("--plan", default="data/replies_plan.json",
                   help="fișierul plan aprobat (la action=reply)")
    s.add_argument("--limita", type=int, default=40,
                   help="max răspunsuri/zi (implicit 40 — prag anti-spam)")
    s.add_argument("--uscat", action="store_true",
                   help="dry-run: arată ce ar publica, fără să publice")
    s.set_defaults(fn=cmd_comments)

    s = sub.add_parser("deepstats", help="analiză ADÂNCĂ per clip: metadate, transcript, top comentarii")
    s.add_argument("--limita", type=int, default=8, help="câte clipuri recente (implicit 8)")
    s.add_argument("--fara-transcript", action="store_true", help="sari peste transcript (mai rapid)")
    s.add_argument("--comentarii", type=int, default=5, help="top comentarii per clip")
    s.set_defaults(fn=cmd_deepstats)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
