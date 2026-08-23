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
import sys
from pathlib import Path

import cardkit
import short

ROOT = Path(__file__).resolve().parent.parent
SIZE = (1080, 1920)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--source", choices=["fixed", "article"], default="fixed")
    ap.add_argument("--slug", default="")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.source == "article":
        sys.path.insert(0, str(ROOT / "scripts"))
        import article as _article

        a = _article.load(args.slug)
        plan = short.plan_for_article(a)
        accent = a.get("accent") or cardkit.ACCENTS[0]
        # 本文とタイトルは投稿側でも要るので、ここで書き出しておく。
        # 各チャンネルが記事を取り直すと、その間に記事が入れ替わる可能性がある
        (outdir / "post.json").write_text(json.dumps({
            "title": a["title"], "url": a["link"], "slug": a["slug"],
            "caption": short.caption_for_article(a),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{a['title']}")
    else:
        if not args.day:
            raise SystemExit("--day が要ります（--source fixed のとき）")
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
