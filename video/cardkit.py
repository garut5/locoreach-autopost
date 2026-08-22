#!/usr/bin/env python3
"""
文字だけのカードを描く共通部分。

リール（1080x1920）と、記事から作るカルーセル（1080x1350）で
同じ見た目にしたいので、描画をここにまとめてある。

## 色について
色は theme.json（唯一の正）に載っているものだけを使う。ここで新しい色を作らない。
使うのは背景 primary、文字 white / light_gray、そして
アクセント3色（#0A7D5A / #1F6FEB / #D14F96）のいずれか1つだけ。
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = "#14171A"
WHITE = "#FFFFFF"
MUTED = "#9AA1AC"
FOOTER = "#5B6472"
ACCENTS = ["#0A7D5A", "#1F6FEB", "#D14F96"]

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Black.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]

_FONT: str | None = None


def font_path() -> str:
    global _FONT
    if _FONT is None:
        for p in FONT_CANDIDATES:
            if Path(p).exists():
                _FONT = p
                break
        else:
            raise SystemExit(
                "日本語フォントが見つかりません。apt-get install -y fonts-noto-cjk を実行してください。"
            )
    return _FONT


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(), size)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def nearest_accent(rgb: tuple[int, int, int]) -> str:
    """拾った色を、許されている3色のうち最も近いものに丸める。"""
    return min(ACCENTS, key=lambda a: sum((x - y) ** 2 for x, y in zip(rgb, hex_rgb(a))))


def accent_from_image(url: str) -> str:
    """既存の画像から、いちばん目立つ有彩色を拾って3色に丸める。

    暗い画素は彩度が当てにならないので捨てる。拾えなければ先頭を返す。
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "locoreach-reels/1.0"})
        with urllib.request.urlopen(req, timeout=60) as res:
            img = Image.open(res).convert("RGB")
    except Exception:
        return ACCENTS[0]
    raw = img.resize((160, 160)).tobytes()
    best, score = None, 0
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        mx, mn = max(r, g, b), min(r, g, b)
        if mx < 90:
            continue
        sat = (mx - mn) / mx
        if sat < 0.35:
            continue
        if sat * mx > score:
            score, best = sat * mx, (r, g, b)
    return nearest_accent(best) if best else ACCENTS[0]


def fit(draw: ImageDraw.ImageDraw, lines: list[str], size: int, width: int):
    """一番長い行が幅に収まるまで文字を小さくする。"""
    while size > 26:
        f = font(size)
        if all(draw.textlength(l, font=f) <= width for l in lines):
            return f
        size -= 4
    return font(size)


def render(
    path: Path,
    kicker: str,
    headline: list[str],
    body: list[str],
    accent: str,
    size: tuple[int, int] = (1080, 1920),
    head_size: int = 86,
    corner: str = "",
    safe: tuple[float, float] = (0.21, 0.75),
) -> None:
    """1枚描く。

    文字は安全域の**中央**に置く。上詰めにすると縦長の画面では
    上に寄って下が大きく空いて見える。
    """
    w, h = size
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    margin = round(w * 0.089)          # 1080 なら 96px
    inner = w - margin * 2
    # リールは上下に端末のUIが載るので内側に寄せる。
    # カルーセルは何も載らないので広く使える
    top = round(h * safe[0])
    bottom = round(h * safe[1])

    kf = font(round(w * 0.037))
    hf = fit(d, headline, head_size, inner)
    bf = fit(d, body, round(w * 0.046), inner) if body else None
    lh = int(hf.size * 1.38)

    block = (round(h * 0.054) if kicker else 0) + lh * len(headline)
    if body:
        block += round(h * 0.023) + round(h * 0.027) + int(bf.size * 1.55) * len(body)
    y = max(top, (top + bottom - block) // 2)

    if kicker:
        d.rectangle([margin, y + 6, margin + 8, y + kf.size + 12], fill=accent)
        d.text((margin + 30, y), kicker, font=kf, fill=accent)
        y += round(h * 0.054)

    for line in headline:
        d.text((margin, y), line, font=hf, fill=WHITE)
        y += lh

    if body:
        y += round(h * 0.023)
        d.rectangle([margin, y, margin + 120, y + 6], fill=accent)
        y += round(h * 0.027)
        for line in body:
            d.text((margin, y), line, font=bf, fill=MUTED)
            y += int(bf.size * 1.55)

    ff = font(round(w * 0.031))
    d.text((margin, bottom + round(h * 0.031)), "LOCOREACH", font=ff, fill=FOOTER)
    d.text((margin, bottom + round(h * 0.057)), "店舗集客をAIで半自動に",
           font=font(round(w * 0.028)), fill=FOOTER)
    if corner:
        cf = font(round(w * 0.031))
        d.text((w - margin - d.textlength(corner, font=cf), bottom + round(h * 0.031)),
               corner, font=cf, fill=FOOTER)

    img.save(path)
