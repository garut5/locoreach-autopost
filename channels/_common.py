#!/usr/bin/env python3
"""
各チャネル共通の小道具。外部パッケージには依存しない（Actions の起動を軽くするため）。
"""
from __future__ import annotations

import os

import datetime
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def today_key() -> str:
    """JST の曜日キー。post.py と同じ基準にそろえている。"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return WEEKDAYS[datetime.datetime.now(jst).weekday()]


def load_item(day: str | None) -> tuple[str, dict]:
    """content.json から当日分を取り出す。投稿本文の出どころを1か所にするため。"""
    day = day or today_key()
    content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    return day, (content.get(day) or {})


def request(url: str, *, data: bytes | None = None, headers: dict | None = None,
            method: str = "GET", timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": "locoreach-autopost/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url.split('?')[0]}\n{e.read().decode()[:600]}") from None
    return json.loads(body) if body.strip() else {}


def post_json(url: str, payload: dict, headers: dict | None = None, **kw) -> dict:
    return request(url, data=json.dumps(payload).encode(), method="POST",
                   headers={"Content-Type": "application/json", **(headers or {})}, **kw)


def post_form(url: str, payload: dict, headers: dict | None = None, **kw) -> dict:
    return request(url, data=urllib.parse.urlencode(payload).encode(), method="POST",
                   headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}, **kw)


def fetch(url: str, timeout: int = 120) -> bytes:
    """画像などをそのまま取ってくる。"""
    req = urllib.request.Request(url, headers={"User-Agent": "locoreach-autopost/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def reachable(url: str, timeout: int = 60) -> tuple[int, str]:
    """投稿先に渡す前に、その URL がこちらから取得できるか確かめる。"""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "locoreach-autopost/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return int(res.headers.get("content-length") or 0), res.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"URL に到達できません（HTTP {e.code}）: {url}") from None


def reel_caption(day: str, item: dict) -> str:
    """縦動画に付ける本文を返す。

    REEL_FORMAT=short のときは、動画で扱っている**1つのコツ**だけを書く。
    カルーセルのキャプションは5つを列挙するので、そのまま付けると
    動画の中身と食い違う。
    """
    # 記事から作った回は、カード生成のときに書き出した本文をそのまま使う。
    # 各チャンネルが記事を取り直すと、その間に記事が入れ替わりうる
    src = os.environ.get("REEL_ITEM", "").strip()
    if src and os.path.exists(src):
        import json as _json

        return _json.load(open(src, encoding="utf-8")).get("caption") or ""
    if os.environ.get("REEL_FORMAT", "").strip() != "short":
        return item.get("caption") or ""
    import sys as _sys
    from pathlib import Path as _Path

    vd = str(_Path(__file__).resolve().parent.parent / "video")
    if vd not in _sys.path:
        _sys.path.insert(0, vd)
    import short as _short

    return _short.caption(day)
