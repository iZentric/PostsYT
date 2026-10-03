"""Playwright: creare sondaje reale (UI composer) + capturare cookies la login.

Opțional: pip install playwright && playwright install chromium
Dacă Playwright lipsește, funcțiile ridică excepție — publisherul face fallback.
"""
from __future__ import annotations

import json
import os
import re
import time

from .models import Draft
from .util import utcnow, iso


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        return sync_playwright
    except ImportError as e:
        raise RuntimeError("Playwright nu e instalat: pip install playwright && playwright install chromium") from e


def capture_login_cookies(out_json: str, wait_seconds: int = 180) -> str:
    """Deschide un browser vizibil: utilizatorul se logează pe Google, apoi ENTER."""
    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://accounts.google.com/ServiceLogin?service=youtube")
        print(f"➡️  Loghează-te în browserul deschis. Aștept detectarea login-ului "
              f"(max {wait_seconds}s)...")
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            cookies = ctx.cookies("https://www.youtube.com")
            names = {c["name"] for c in cookies}
            if "SAPISID" in names or "__Secure-3PAPISID" in names:
                os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
                with open(out_json, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, indent=2, ensure_ascii=False)
                browser.close()
                return out_json
            time.sleep(2)
        browser.close()
    raise RuntimeError("Timeout — nu am detectat login. Reîncearcă `python -m postsyt login`.")


def publish_poll_via_browser(cfg, draft: Draft, timeout_s: int = 120) -> str:
    """Deschide composer-ul de Community și crează sondajul real (question + choices)."""
    sync_playwright = _import_playwright()
    cookies_path = cfg.cookies_json
    if not os.path.exists(cookies_path):
        raise RuntimeError(f"Lipsește {cookies_path} — rulează `python -m postsyt login` mai întâi.")
    cookies = json.load(open(cookies_path, encoding="utf-8"))
    url = f"https://www.youtube.com/channel/{cfg.own_channel_id}/community"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bool(cfg.get("playwright_headless", True)) if hasattr(cfg, "get") else True)
        ctx = browser.new_context(locale="ro-RO")
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)

        # 1. deschide composerul (placeholder-text variază; încercăm mai multe căi)
        for sel in (
            "ytd-backstage-post-dialog-wrapper ytd-button-renderer",
            "#post-mini-app ytd-button-renderer",
            "yt-formatted-string#placeholder-text",
            "div[contenteditable='true'][role='textbox']",
            "#input-text yt-formatted-string",
        ):
            try:
                if page.locator(sel).first.is_visible(timeout=4000):
                    page.locator(sel).first.click()
                    break
            except Exception:
                continue
        page.wait_for_timeout(1500)

        # 2. apasă butonul "Sondaj"/"Poll"
        for txt in ("Sondaj", "Poll", "sondaj"):
            try:
                page.get_by_text(txt, exact=False).first.click(timeout=4000)
                break
            except Exception:
                continue
        page.wait_for_timeout(1200)

        # 3. completează întrebarea + opțiunile
        boxes = page.locator("yt-formatted-string[contenteditable='true'], div[contenteditable='true']")
        count = boxes.count()
        if count >= 1:
            boxes.nth(0).click()
            boxes.nth(0).fill(draft.poll_question)
        for i, opt in enumerate(d.poll_options):
            idx = 1 + i
            if idx < count:
                boxes.nth(idx).click()
                boxes.nth(idx).fill(opt)
            else:
                # adaugă câmp nou dacă există buton "Adaugă opțiune"
                try:
                    page.get_by_text("Adaugă opțiune", exact=False).first.click(timeout=2500)
                    page.wait_for_timeout(600)
                    boxes = page.locator("div[contenteditable='true']")
                    boxes.nth(idx).click()
                    boxes.nth(idx).fill(opt)
                except Exception:
                    break
        # textul din jurul sondajului (link) nu poate fi în poll nativ — îl lăsăm alături dacă există câmp
        page.wait_for_timeout(800)

        # 4. publică
        for sel in (
            "ytd-button-renderer#confirm-button",
            "button:has-text('Postează')",
            "button:has-text('Post')",
            "tp-yt-paper-button:has-text('Postează')",
        ):
            try:
                page.locator(sel).first.click(timeout=4000)
                break
            except Exception:
                continue
        page.wait_for_timeout(4000)
        # caută linkul postării proaspete în feed
        m = re.search(r"/post/(Ugkx[\w-]+)", page.content() or "")
        browser.close()
        return m.group(0).split("/post/")[1] if m else f"poll@{iso(utcnow())}"
    raise RuntimeError("Nu am putut finaliza sondajul prin browser.")
