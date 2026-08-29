#!/usr/bin/env python3
"""
同じ記事を二度出さないための記録。

    python3 scripts/posted.py check  --channel carousel --item out/post/post.json
    python3 scripts/posted.py record --channel carousel --item out/post/post.json

check は、その記事をそのチャネルで既に出していれば **終了コード 1** を返す。
record は出したことを posted.json に書く。

## なぜ要るのか

GitHub の cron は遅れる。2026-08-27 は丸一日発火せず、8/28 分は
翌朝 05:45〜06:19 JST に流れた。記事の公開は 07:03 JST なので、
その時刻にはまだ前日の記事しか無い。

一方、発火しなかった日は見張りが手で投げ直している。結果、

  8/28 22:26 JST  見張りが投げ直す      → 8/28 の記事を投稿
  8/29 06:19 JST  遅れた cron が発火    → 8/28 の記事を **もう一度** 投稿

同じ記事がカルーセルで2回、動画で2回、アカウントに並んだ。
「実行が重なったか」ではなく「その記事をもう出したか」で判断する。

Threads への記事拡散（scripts/promote.py）が同じ posted.json を
使っているので、記録先はそこに揃える。チャネルごとにキーを分ける。

曜日固定の7セットは毎週くり返すのが仕様なので、slug が無い回は
何も見ない（check は通し、record は書かない）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "posted.json"


def slug_of(item: str, slug: str) -> str:
    if slug:
        return slug.strip()
    if item and Path(item).exists():
        return (json.loads(Path(item).read_text(encoding="utf-8")).get("slug") or "").strip()
    return ""


def load() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["check", "record"])
    ap.add_argument("--channel", required=True, help="carousel / reel / threads")
    ap.add_argument("--item", default="", help="slug を持つ post.json")
    ap.add_argument("--slug", default="")
    args = ap.parse_args()

    slug = slug_of(args.item, args.slug)
    if not slug:
        # 記事から作れなかった回（曜日固定の7セット）。重複判定の対象外
        print("スラッグが無いため、重複の判定はしません")
        return 0

    state = load()
    done = state.setdefault(args.channel, [])

    if args.mode == "check":
        if slug in done:
            print(f"✗ {slug} は {args.channel} で投稿済みです。二重投稿になるので出しません")
            return 1
        print(f"✓ {slug} は {args.channel} で未投稿です")
        return 0

    if slug in done:
        print(f"{slug} はすでに記録済みです")
        return 0
    done.append(slug)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ {args.channel} に {slug} を記録しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
