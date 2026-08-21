#!/usr/bin/env python3
"""
ショート用のカードを描く。1080x1920。

    python3 video/cards.py --day fri --outdir /tmp/cards

## なぜ既存のカルーセル画像を使わないのか
カルーセルの10枚は「表紙 → 目次 → 理由 → コツ5つ → まとめ → CTA」で
組まれている。保存して読み返す前提なら正しいが、リールでは冒頭2秒が全てで、
目次と表紙にそれを使うと見られないまま終わる。
ショートは**コツ1つ**に絞るので、そのぶんのカードをここで描く。

## 色について
色は theme.json（Owned-Media 側の唯一の正）から取る。ここで新しい色を作らない。
使うのは背景 primary、文字 white / light_gray、そして
アクセント3色（#0A7D5A / #1F6FEB / #D14F96）のいずれか1つだけ。
どの日にどれを使うかは、その日のカルーセル画像から拾った色を
**3色のうち最も近いものに丸めて**決める。勝手な割り当てをしないため。
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
VW, VH = 1080, 1920

# 端末のUIに隠れない範囲。下は再生バーとキャプション、右はボタンが載る
MARGIN_X = 96
TOP = 400
BOTTOM = 1440

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


def font_path() -> str:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit(
        "日本語フォントが見つかりません。apt-get install -y fonts-noto-cjk を実行してください。"
    )


def font(size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(), size, index=index)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def nearest_accent(rgb: tuple[int, int, int]) -> str:
    """拾った色を、許されている3色のうち最も近いものに丸める。"""
    return min(ACCENTS, key=lambda a: sum((x - y) ** 2 for x, y in zip(rgb, hex_rgb(a))))


def accent_from_image(url: str) -> str:
    """その日のカルーセル画像から、いちばん目立つ有彩色を拾う。

    暗い画素は彩度が不安定なので捨てる。拾えなければ最初のアクセントを返す。
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "locoreach-reels/1.0"})
        with urllib.request.urlopen(req, timeout=60) as res:
            img = Image.open(res).convert("RGB")
    except Exception:
        return ACCENTS[0]
    img = img.resize((160, 160))
    raw = img.tobytes()
    best, score = None, 0
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        mx, mn = max(r, g, b), min(r, g, b)
        if mx < 90:            # 暗すぎる画素は色として当てにならない
            continue
        sat = (mx - mn) / mx
        if sat < 0.35:
            continue
        if sat * mx > score:
            score, best = sat * mx, (r, g, b)
    return nearest_accent(best) if best else ACCENTS[0]


def fit(draw: ImageDraw.ImageDraw, lines: list[str], size: int, width: int, f_index: int = 0):
    """一番長い行が幅に収まるまで文字を小さくする。"""
    while size > 28:
        f = font(size, f_index)
        if all(draw.textlength(l, font=f) <= width for l in lines):
            return f
        size -= 4
    return font(size, f_index)


def render(
    path: Path,
    kicker: str,
    headline: list[str],
    body: list[str],
    accent: str,
    big: bool = False,
) -> None:
    img = Image.new("RGB", (VW, VH), BG)
    d = ImageDraw.Draw(img)
    inner = VW - MARGIN_X * 2

    kf = font(40)
    hf = fit(d, headline, 104 if big else 86, inner)
    bf = fit(d, body, 50, inner) if body else None
    lh = int(hf.size * 1.38)

    # 先に高さを測って、安全域の中央に置く。上詰めにすると
    # 縦長の画面では文字が上に寄って、下が大きく空いて見える。
    h = (104 if kicker else 0) + lh * len(headline)
    if body:
        h += 44 + 52 + int(bf.size * 1.55) * len(body)
    y = max(TOP, (TOP + BOTTOM - h) // 2)

    if kicker:
        # アクセントの短い縦棒。面積を持たせず、色は1色だけに留める
        d.rectangle([MARGIN_X, y + 6, MARGIN_X + 8, y + 52], fill=accent)
        d.text((MARGIN_X + 30, y), kicker, font=kf, fill=accent)
        y += 104

    for line in headline:
        d.text((MARGIN_X, y), line, font=hf, fill=WHITE)
        y += lh

    if body:
        y += 44
        d.rectangle([MARGIN_X, y, MARGIN_X + 120, y + 6], fill=accent)
        y += 52
        for line in body:
            d.text((MARGIN_X, y), line, font=bf, fill=MUTED)
            y += int(bf.size * 1.55)

    d.text((MARGIN_X, BOTTOM + 60), "LOCOREACH", font=font(34), fill=FOOTER)
    d.text((MARGIN_X, BOTTOM + 110), "店舗集客をAIで半自動に", font=font(30), fill=FOOTER)

    img.save(path)


def main() -> int:
    import short  # 同じディレクトリ

    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    first = (content.get(args.day, {}).get("image_urls") or [""])[0]
    accent = accent_from_image(first) if first else ACCENTS[0]

    plan = short.plan_for(args.day)
    for i, card in enumerate(plan, 1):
        p = outdir / f"card_{i:02d}.png"
        render(p, card["kicker"], card["headline"], card.get("body", []), accent,
               big=card.get("big", False))
        print(f"  ✓ {p.name}  {card['kicker']} / {' '.join(card['headline'])}")
    print(f"\n{len(plan)} 枚 / アクセント {accent} → {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
