"""ImageMaker: cards vizuale 1080x1080 pentru postări.

- SVG (stdlib, mereu disponibil) — perfect pentru preview/dashboard.
- PNG (dacă Pillow e instalat) — necesar la uploadul efectiv pe YouTube.
- Cu Pillow + internet: descarcă si thumbnailul clipului și îl compune în card (Tip A).
"""
from __future__ import annotations

import html
import os
import random
import textwrap
import urllib.request
from typing import Optional

BRAND_GRADIENTS = [
    ("#0ea5e9", "#7c3aed"), ("#f59e0b", "#ef4444"), ("#10b981", "#0ea5e9"),
    ("#ec4899", "#8b5cf6"), ("#22d3ee", "#3b82f6"), ("#f97316", "#f43f5e"),
]


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return lines


def _esc(t: str) -> str:
    return html.escape(t, quote=False)


def svg_card(title: str, subtitle: str = "", badge: str = "POKECITY",
             footer: str = "@isentric1", seed: Optional[int] = None,
             size: int = 1080) -> str:
    """Card brand: gradient + text mare + badge. Emoji-urile raman in text (fontul sistemului)."""
    rnd = random.Random(seed)
    c1, c2 = BRAND_GRADIENTS[seed % len(BRAND_GRADIENTS) if seed is not None else rnd.randrange(len(BRAND_GRADIENTS))]
    lines = _wrap(title, 16)
    sub_lines = _wrap(subtitle, 30)[:3] if subtitle else []
    total_rows = lines + ([""] if sub_lines else []) + sub_lines
    fs = 64 if max(len(l) for l in lines or [""]) <= 12 else 52
    lh = int(fs * 1.22)
    block_h = len(lines) * lh + (len(sub_lines) + 1) * int(lh * 0.72)
    y0 = (size - block_h) // 2 + fs

    deco = []
    for _ in range(6):
        x, y = rnd.randint(0, size), rnd.randint(0, size)
        r = rnd.randint(60, 220)
        deco.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="white" opacity="0.05"/>')
    for _ in range(3):
        x = rnd.randint(-200, size)
        deco.append(f'<rect x="{x}" y="{rnd.randint(0, size)}" width="420" height="26" '
                    f'transform="rotate({rnd.randint(-35, 35)} {x} 0)" fill="white" opacity="0.06" rx="13"/>')

    text_rows = []
    y = y0
    for ln in lines:
        text_rows.append(
            f'<text x="50%" y="{y}" text-anchor="middle" font-size="{fs}" '
            f'font-family="DejaVu Sans, Arial, sans-serif" font-weight="800" fill="#fff" '
            f'style="text-shadow:0 4px 14px rgba(0,0,0,.45)">{_esc(ln)}</text>')
        y += lh
    y += int(lh * 0.25)
    for ln in sub_lines:
        text_rows.append(
            f'<text x="50%" y="{y}" text-anchor="middle" font-size="{int(fs*0.56)}" '
            f'font-family="DejaVu Sans, Arial, sans-serif" font-weight="600" fill="#eef2ff" '
            f'opacity="0.95">{_esc(ln)}</text>')
        y += int(lh * 0.72)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
    <linearGradient id="shine" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#000" stop-opacity="0.16"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <rect width="{size}" height="{size}" fill="url(#g)"/>
  <rect width="{size}" height="{size}" fill="url(#shine)"/>
  {''.join(deco)}
  <rect x="40" y="34" width="{len(badge)*22 + 46}" height="58" rx="29" fill="#000" opacity="0.42"/>
  <text x="{40 + 23}" y="72" font-family="DejaVu Sans, Arial" font-size="30" font-weight="700" fill="#ffd166" letter-spacing="3">{_esc(badge)}</text>
  {''.join(text_rows)}
  <rect x="0" y="{size-88}" width="{size}" height="88" fill="#000" opacity="0.30"/>
  <text x="{size//2}" y="{size-36}" text-anchor="middle" font-family="DejaVu Sans, Arial"
        font-size="34" font-weight="700" fill="#ffffff" opacity="0.96">{_esc(footer)}</text>
</svg>'''


def svg_poll(question: str, options: list[str], seed: Optional[int] = None,
             size: int = 1080) -> str:
    """Card de sondaj (pentru preview când sondajul real nu poate fi creat automat)."""
    rnd = random.Random(seed)
    c1, c2 = BRAND_GRADIENTS[seed % len(BRAND_GRADIENTS) if seed is not None else rnd.randrange(len(BRAND_GRADIENTS))]
    qlines = _wrap(question, 26)[:3]
    letters = "ABCDE"
    y = 250
    rows = [
        f'<text x="{size//2}" y="150" text-anchor="middle" font-size="42" font-weight="800" '
        f'fill="#ffd166" font-family="DejaVu Sans, Arial">📊 SONDALJ</text>'
    ]
    for ln in qlines:
        rows.append(f'<text x="{size//2}" y="{y}" text-anchor="middle" font-size="48" font-weight="800" '
                    f'fill="#fff" font-family="DejaVu Sans, Arial">{_esc(ln)}</text>')
        y += 62
    y += 40
    for i, opt in enumerate(options[:5]):
        rows.append(f'<rect x="120" y="{y-48}" width="{size-240}" height="86" rx="43" fill="#000" opacity="0.32"/>')
        rows.append(f'<text x="160" y="{y+9}" font-size="40" font-weight="800" fill="#ffd166" '
                    f'font-family="DejaVu Sans, Arial">{letters[i]}</text>')
        rows.append(f'<text x="230" y="{y+9}" font-size="38" font-weight="600" fill="#fff" '
                    f'font-family="DejaVu Sans, Arial">{_esc(opt[:34])}</text>')
        y += 108
    rows.append(f'<text x="{size//2}" y="{size-48}" text-anchor="middle" font-size="32" '
                f'font-weight="700" fill="#fff" opacity="0.9" font-family="DejaVu Sans, Arial">@isentric1</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>
  </linearGradient></defs>
  <rect width="{size}" height="{size}" fill="url(#g)"/>
  {''.join(rows)}
</svg>'''


# ------------------------------------------------------------------ PNG (opțional)
def try_png_from_svg(svg_path: str, png_path: str) -> bool:
    """Rasterizează SVG → PNG (cairosvg sau Pillow+rasterio indisponibile => False)."""
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=1080, output_height=1080)
        return True
    except Exception:
        pass
    # fallback simplu: desenăm cardul direct cu Pillow (fără SVG)
    try:
        from PIL import Image, ImageDraw  # type: ignore
        import re as _re
        text = open(svg_path, encoding="utf-8").read()
        m1 = _re.search(r'stop-color="(#[0-9a-fA-F]{6})"', text)
        m2 = _re.findall(r'stop-color="(#[0-9a-fA-F]{6})"', text)
        c1 = m1.group(1) if m1 else "#0ea5e9"
        c2 = m2[1] if len(m2) > 1 else "#7c3aed"
        S = 1080
        img = Image.new("RGB", (S, S))
        px = img.load()
        def hex2rgb(h):
            return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        a, b = hex2rgb(c1), hex2rgb(c2)
        for yy in range(S):
            for xx in range(0, S, 4):
                t = (xx + yy) / (2 * S)
                col = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
                for dx in range(4):
                    px[min(xx + dx, S - 1), yy] = col
        d = ImageDraw.Draw(img)
        # extragem textele mari
        texts = _re.findall(r'<text[^>]*font-size="(\d+)"[^>]*>([^<]+)</text>', text)
        y = 380
        for fs, t in texts[:8]:
            size = int(fs)
            w = d.textlength(t)
            d.text(((S - w) / 2, y), t, fill="white")
            y += int(size * 1.3)
        img.save(png_path, "PNG")
        return True
    except Exception:
        return False


class ImageMaker:
    def __init__(self, images_dir: str):
        self.dir = images_dir
        os.makedirs(images_dir, exist_ok=True)

    def _save(self, name: str, svg: str, want_png: bool = False) -> str:
        path = os.path.join(self.dir, name + ".svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        if want_png:
            png = os.path.join(self.dir, name + ".png")
            if try_png_from_svg(path, png):
                return png
        return path

    def for_video(self, title: str, seed: int, want_png: bool = True) -> str:
        svg = svg_card(title, subtitle="EPISOD NOU pe canal ▶️", badge="POKECITY", seed=seed)
        return self._save(f"video_{seed}", svg, want_png)

    def for_meme(self, top: str, bottom: str, seed: int) -> str:
        svg = svg_card(f"{top}\n{bottom}", badge="MEME", footer="@isentric1", seed=seed)
        return self._save(f"meme_{seed}", svg, want_png=True)

    def for_poll(self, question: str, options: list[str], seed: int) -> str:
        svg = svg_poll(question, options, seed=seed)
        return self._save(f"poll_{seed}", svg, want_png=True)

    def for_question(self, text: str, seed: int) -> str:
        svg = svg_card(text, subtitle="zi-mi în comentarii 👇", badge="VOTEAZĂ", seed=seed)
        return self._save(f"question_{seed}", svg, want_png=True)

    def for_trend(self, hook: str, seed: int) -> str:
        svg = svg_card(hook, subtitle="trend check 🔥", badge="TREND", seed=seed)
        return self._save(f"trend_{seed}", svg, want_png=True)
