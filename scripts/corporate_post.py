#!/usr/bin/env python3
"""その日の記事を、会社サイト（camomile.co.jp）のブログにも載せる。

    python3 scripts/corporate_post.py --dry-run     出す内容だけ見る
    python3 scripts/corporate_post.py               実際に投稿する

## なぜ全文を転載しないのか

同じ本文を2つのドメインに置くと、検索エンジンがどちらを本命か決められず、
**両方の評価が落ちる**（重複コンテンツ）。会社サイトは会社の顔、
media は集客の受け皿で、診断フォームへの導線もそちらにある。
なので会社サイトには「入口」を置き、本文は media へ送る。

## 二重投稿について

同じスラッグの投稿があれば何もせずに終わる（終了コード0）。
定期実行が二重に走っても、手で叩き直しても、記事は増えない。
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import article as _article  # noqa: E402
from wp import WordPress, WordPressError  # noqa: E402

# 会社サイト側のスラッグ。media 側と同じ文字列だと紛らわしいので前置きする
SLUG_PREFIX = "media-"


def build(a: dict) -> dict:
    """記事1本から、会社サイトに載せる本文を組み立てる。

    事実は記事から取ったものだけを使う。要約を創作しない。
    """
    title = a["title"]
    url = a["link"]
    lead = a.get("description", "").strip()
    chip = a.get("chip") or a.get("category", "")

    parts = []
    if lead:
        parts.append(f"<p>{html.escape(lead)}</p>")

    sections = a.get("sections") or []
    if sections:
        parts.append("<h2>この記事で扱っていること</h2>")
        parts.append("<ul>")
        for s in sections:
            parts.append(f"<li>{html.escape(s['title'])}</li>")
        parts.append("</ul>")

    parts.append(
        f'<p><a href="{html.escape(url)}" rel="noopener">'
        f"続きはロコリーチMEDIAで読む（{html.escape(title)}）</a></p>"
    )
    parts.append(
        '<p>店舗の集客について個別に知りたい方は、'
        f'<a href="https://media.camomile.co.jp/diagnose/" rel="noopener">'
        "無料のMEO診断</a>をご利用ください。</p>"
    )

    return {
        "title": title,
        "content": "\n".join(parts),
        "slug": SLUG_PREFIX + a["slug"],
        "excerpt": lead[:120],
        "chip": chip,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="", help="media 側のスラッグ。既定は最新")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", default="publish", choices=["publish", "draft"])
    args = ap.parse_args()

    a = _article.load(args.slug)
    post = build(a)

    print("─" * 52)
    print(f"タイトル: {post['title']}")
    print(f"スラッグ: {post['slug']}")
    print(f"元記事  : {a['link']}")
    print("─" * 52)
    print(post["content"])
    print("─" * 52)

    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0

    try:
        wp = WordPress()
    except WordPressError as e:
        print(f"⚠ {e} のため投稿をスキップします")
        return 0

    who = wp.whoami()
    print(f"  接続確認: {who.get('name')}（ID {who.get('id')}）")

    if wp.find_by_slug(post["slug"]):
        print(f"✓ すでに投稿済みのため何もしません: {post['slug']}")
        return 0

    r = wp.create_post(
        title=post["title"], content=post["content"], slug=post["slug"],
        excerpt=post["excerpt"], status=args.status,
    )
    print(f"✓ 会社サイトへ投稿しました: {r.get('link')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
