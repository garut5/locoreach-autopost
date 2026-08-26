#!/usr/bin/env python3
"""会社サイトに、その日の記事が本当に載ったかを確かめる。

    python3 scripts/corporate_check.py

投稿そのものはサイトの中の mu-plugin が行う。ここは結果だけを見る。
載っていなければ終了コード1で落ち、Google Chat に通知が飛ぶ。

「動いているはず」で放置すると、8/23〜8/26 のように何日も
気づかないまま止まる。載ったことを外から確かめて初めて、
動いていると言える。
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import article as _article  # noqa: E402

BASE = "https://camomile.co.jp"
PREFIX = "media-"
UA = {"User-Agent": "locoreach-autopost/1.0"}
TRIES = 6
WAIT = 20


def reachable(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=45) as res:
            return res.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def main() -> int:
    a = _article.load()
    url = f"{BASE}/{PREFIX}{a['slug']}/"
    print(f"今日の記事: {a['title']}")
    print(f"確認先    : {url}")

    for i in range(1, TRIES + 1):
        code = reachable(url)
        print(f"  試行 {i}: HTTP {code}")
        if code == 200:
            print("✓ 会社サイトに載っています")
            return 0
        if i < TRIES:
            time.sleep(WAIT)

    print(
        "会社サイトに今日の記事が載っていません。\n"
        "  mu-plugin: wp-content/mu-plugins/camomilemediabridge.php を確認してください",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
