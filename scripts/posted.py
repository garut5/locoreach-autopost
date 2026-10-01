#!/usr/bin/env python3
"""
同じ記事を二度出さないための記録。

    python3 scripts/posted.py check  --channel carousel --item out/post/post.json
    python3 scripts/posted.py record --channel carousel --item out/post/post.json
    python3 scripts/posted.py record-result --channel carousel \
        --item out/post/post.json --result out/post/result.json

check は、その記事をそのチャネルで既に出していれば **終了コード 1** を返す。
record は出したことを posted.json に書く。

record-result は、**一部のチャネルだけ成功した回**のための書き方。
post.py が残した結果を読み、成功したチャネルを "carousel:threads" の
ように個別のキーへ書き、全チャネルが揃ったときだけ "carousel" にも書く。

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

## 一部だけ成功した回

2026-09-30、IGフィードだけが Meta 側のメディア取得エラーで落ちた。
Threads は成功していたが、実行が失敗で終わったので "carousel" に
記録されず、遅れて走った定期実行が Threads へ同じ投稿を重ねて出した。

そこで "carousel" は「3チャネルすべて出した」印のまま残し
（見張りと promote.py がこれを見ている）、途中まで出せた回は
"carousel:ig_feed" のように分けて書く。post.py はこれを読んで、
出し終えたチャネルを飛ばす。

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


# 成功とみなす値。「済」は前回すでに出していて今回は飛ばした、の意味
OK = ("OK", "済")


def record_result(args) -> int:
    """post.py の結果を読み、出せたチャネルだけを記録する。

    ここが落ちると記録が残らず二重投稿に戻るので、
    読めなかった場合も終了コード0で抜ける（投稿自体は済んでいる）。
    """
    path = Path(args.result)
    if not args.result or not path.exists():
        print("結果ファイルがないため、記録しません")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"結果ファイルを読めません（記録しません）: {e}")
        return 0

    results = data.get("results") or {}
    slug = slug_of(args.item, args.slug) or (data.get("slug") or "").strip()
    if not slug or not results:
        print("スラッグか結果が無いため、記録しません")
        return 0

    state = load()
    wrote = []
    for ch, v in results.items():
        if v not in OK:
            continue
        done = state.setdefault(f"{args.channel}:{ch}", [])
        if slug not in done:
            done.append(slug)
            wrote.append(ch)

    # 全チャネルが揃ったときだけ、まとめのキーに書く。
    # 見張りと promote.py は、こちらを「出し終えた」印として見ている。
    if all(v in OK for v in results.values()):
        done = state.setdefault(args.channel, [])
        if slug not in done:
            done.append(slug)
            wrote.append(args.channel)
            print(f"✓ {args.channel} に {slug} を記録しました（全チャネル完了）")

    if not wrote:
        print("記録する変更はありません")
        return 0

    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ 記録しました: {', '.join(wrote)}（{slug}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["check", "record", "record-result"])
    ap.add_argument("--channel", required=True, help="carousel / reel / threads")
    ap.add_argument("--item", default="", help="slug を持つ post.json")
    ap.add_argument("--slug", default="")
    ap.add_argument("--result", default="", help="post.py が残した結果（record-result 用）")
    args = ap.parse_args()

    if args.mode == "record-result":
        return record_result(args)

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
