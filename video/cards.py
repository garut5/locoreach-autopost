#!/usr/bin/env python3
"""
ショート（縦動画）用のカードを描く。1080x1920。

    python3 video/cards.py --day fri --outdir /tmp/cards

## なぜ既存のカルーセル画像を使わないのか
カルーセルの10枚は「表紙 → 目次 → 理由 → コツ5つ → まとめ → CTA」で
組まれている。保存して読み返す前提なら正しいが、リールでは冒頭2秒が全てで、
目次と表紙にそれを使うと見られないまま終わる。
ショートは**コツ1つ**に絞るので、そのぶんのカードをここで描く。

描画そのものは video/cardkit.py にある（記事から作るカルーセルと共通）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cardkit
import short

ROOT = Path(__file__).resolve().parent.parent
SIZE = (1080, 1920)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    first = (content.get(args.day, {}).get("image_urls") or [""])[0]
    accent = cardkit.accent_from_image(first) if first else cardkit.ACCENTS[0]

    plan = short.plan_for(args.day)
    for i, card in enumerate(plan, 1):
        p = outdir / f"card_{i:02d}.png"
        cardkit.render(
            p, card["kicker"], card["headline"], card.get("body", []), accent,
            size=SIZE, head_size=104 if card.get("big") else 86,
        )
        print(f"  ✓ {p.name}  {card['kicker']} / {' '.join(card['headline'])}")
    print(f"\n{len(plan)} 枚 / アクセント {accent} → {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
