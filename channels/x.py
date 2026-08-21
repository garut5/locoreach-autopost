#!/usr/bin/env python3
"""
X（旧Twitter）へ投稿する。

    python3 channels/x.py --day fri
    python3 channels/x.py --dry-run

環境変数（4つそろっていなければ何もせず終了する）
  X_API_KEY / X_API_SECRET              アプリの Consumer Key / Secret
  X_ACCESS_TOKEN / X_ACCESS_SECRET      アカウントの Access Token / Secret
  X_LINK                                誘導先。既定 https://media.camomile.co.jp/
  X_MAX_IMAGES                          添付枚数。既定 4（X の上限）

なぜ OAuth 1.0a なのか
  画像付きの投稿は OAuth 2.0 のアプリ専用トークンでは通らない。
  ユーザー文脈が要るので 1.0a のユーザートークンで署名している。
  外部パッケージを入れずに済むよう、署名は下に自前で書いた。

X の本文は 280 文字。content.json のキャプションは 350 文字前後あるので、
そのままでは入らない。見出し → 箇条書き → 誘導リンク の順に詰め、
入りきらない行から落とす。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import fetch, load_item  # noqa: E402

UPLOAD_V2 = "https://api.x.com/2/media/upload"
UPLOAD_V1 = "https://upload.twitter.com/1.1/media/upload.json"
TWEETS = "https://api.x.com/2/tweets"

# X はどんなURLも t.co に置き換えるので、長さは一律この値で数える
TCO_LEN = 23
TEXT_LIMIT = 280
# X の文字数は「重み付き」で、日本語と絵文字は1文字あたり2として数える。
# つまり日本語だけなら実質140字しか入らない。
# 重み1になるのは下の範囲だけ（X の twitter-text 実装に合わせている）。
LIGHT_RANGES = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))
X_HASHTAGS = 2
UTM = {"utm_source": "x", "utm_medium": "social", "utm_campaign": "sns"}


# ---------------- OAuth 1.0a ----------------
def _quote(s: str) -> str:
    return urllib.parse.quote(str(s), safe="~")


def oauth_header(method: str, url: str, creds: dict, extra: dict | None = None) -> str:
    """署名を作って Authorization ヘッダを返す。

    extra には「署名に含めるパラメータ」だけを渡す。URL のクエリと
    application/x-www-form-urlencoded のボディが該当する。
    JSON ボディと multipart のボディは署名に含めない（仕様どおり）。
    """
    params = {
        "oauth_consumer_key": creds["key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["token"],
        "oauth_version": "1.0",
    }
    parts = urllib.parse.urlsplit(url)
    base_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    signing = dict(params)
    signing.update(dict(urllib.parse.parse_qsl(parts.query)))
    signing.update(extra or {})
    encoded = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(signing.items()))
    base = f"{method.upper()}&{_quote(base_url)}&{_quote(encoded)}"
    signing_key = f"{_quote(creds['secret'])}&{_quote(creds['token_secret'])}"
    params["oauth_signature"] = base64.b64encode(
        hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(f'{_quote(k)}="{_quote(v)}"' for k, v in sorted(params.items()))


def _send(method: str, url: str, creds: dict, *, body: bytes | None = None,
          content_type: str | None = None, sign_extra: dict | None = None, timeout: int = 120) -> dict:
    headers = {"Authorization": oauth_header(method, url, creds, sign_extra),
               "User-Agent": "locoreach-autopost/1.0"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url}\n{e.read().decode()[:600]}") from None
    return json.loads(raw) if raw.strip() else {}


def multipart(field: str, filename: str, data: bytes, extra: dict | None = None) -> tuple[bytes, str]:
    boundary = "----locoreach" + secrets.token_hex(12)
    out = bytearray()
    for k, v in (extra or {}).items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    out += data + b"\r\n" + f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def upload_image(url: str, creds: dict) -> str:
    """画像を1枚上げて media_id を返す。v2 が通らない環境では v1.1 に落とす。"""
    data = fetch(url)
    name = url.rsplit("/", 1)[-1] or "image.png"
    body, ctype = multipart("media", name, data, {"media_category": "tweet_image"})
    try:
        r = _send("POST", UPLOAD_V2, creds, body=body, content_type=ctype)
        mid = (r.get("data") or {}).get("id") or r.get("media_id_string") or r.get("id")
        if mid:
            return str(mid)
        raise RuntimeError(f"media_id が返りませんでした: {r}")
    except RuntimeError as e:
        print(f"    v2 のアップロードが通らないため v1.1 で再試行します（{str(e)[:120]}）")
        body, ctype = multipart("media", name, data)
        r = _send("POST", UPLOAD_V1, creds, body=body, content_type=ctype)
        return str(r["media_id_string"])


# ---------------- 本文 ----------------
def weighted(text: str) -> int:
    """X の数え方で本文の長さを出す。URL は実長でなく t.co の 23 として数える。"""
    def chars(s: str) -> int:
        return sum(1 if any(lo <= ord(c) <= hi for lo, hi in LIGHT_RANGES) else 2 for c in s)

    total, idx = 0, 0
    for m in re.finditer(r"https?://\S+", text):
        total += chars(text[idx:m.start()]) + TCO_LEN
        idx = m.end()
    return total + chars(text[idx:])


def link_with_utm(day: str) -> str:
    base = os.environ.get("X_LINK", "https://media.camomile.co.jp/").strip()
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    present = {k for k, _ in query}
    for k, v in {**UTM, "utm_content": day}.items():
        if k not in present:
            query.append((k, v))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def text_for(day: str, item: dict) -> str:
    """280 文字に収める。行単位で削るので、途中で切れた文が残らない。"""
    override = (item.get("x_text") or "").strip()
    link = link_with_utm(day)
    if override:
        return override if len(override) <= TEXT_LIMIT else override[: TEXT_LIMIT - 1] + "…"

    blocks = [b.strip() for b in (item.get("caption") or "").split("\n\n") if b.strip()]
    tags = [t for t in (blocks[-1].split() if blocks and blocks[-1].startswith("#") else []) if t.startswith("#")]
    # Instagram のハンドルは X には無いので、その行だけ落とす（段落ごと消さない）
    body_blocks = []
    for b in blocks:
        if b.startswith("#"):
            continue
        kept = [ln for ln in b.split("\n") if "@locoreach_ai" not in ln]
        if kept:
            body_blocks.append("\n".join(kept))

    tail = "\n\n" + link + ("\n" + " ".join(tags[:X_HASHTAGS]) if tags else "")
    budget = TEXT_LIMIT - weighted(tail)

    lines: list[str] = []
    used = 0
    for block in body_blocks:
        # 「▼この投稿でわかること」の箇条書きは途中で切らない。
        # 見出しが「5つ」と件数を名乗るので、2つだけ並ぶと嘘になる。
        if block.startswith("▼"):
            add = weighted(block) + (1 if lines else 0)
            if used + add > budget:
                continue
            lines.extend(block.split("\n"))
            used += add
            if used + 1 <= budget:
                lines.append("")
                used += 1
            continue
        for line in block.split("\n"):
            add = weighted(line) + (1 if lines else 0)
            if used + add > budget:
                return "\n".join(lines).rstrip() + tail
            lines.append(line)
            used += add
        # 段落の切れ目に空行を入れる余地があれば入れる
        if used + 1 <= budget:
            lines.append("")
            used += 1
    return "\n".join(lines).rstrip() + tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day, item = load_item(args.day)
    if not item:
        print(f"{day} のコンテンツがないので何もしません")
        return 0

    text = text_for(day, item)
    images = (item.get("image_urls") or [])[: int(os.environ.get("X_MAX_IMAGES", "4"))]

    print("─" * 52)
    print(f"[X] {day} / {item.get('genre')} / 画像 {len(images)}枚")
    print("─" * 52)
    print(text)
    print("─" * 52)
    print(f"{len(text)} 文字 / X の数え方で {weighted(text)} 文字 / 上限 {TEXT_LIMIT}")
    if weighted(text) > TEXT_LIMIT:
        sys.exit("本文が X の上限を超えています。content.json に x_text を足して短くしてください。")

    creds = {
        "key": os.environ.get("X_API_KEY", "").strip(),
        "secret": os.environ.get("X_API_SECRET", "").strip(),
        "token": os.environ.get("X_ACCESS_TOKEN", "").strip(),
        "token_secret": os.environ.get("X_ACCESS_SECRET", "").strip(),
    }
    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0
    if not all(creds.values()):
        print("⚠ X の認証情報が未設定のため投稿をスキップします")
        return 0

    media_ids = []
    for url in images:
        mid = upload_image(url, creds)
        media_ids.append(mid)
        print(f"  画像をアップロード: {mid}")

    payload: dict = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    r = _send("POST", TWEETS, creds, body=json.dumps(payload).encode(), content_type="application/json")
    tid = (r.get("data") or {}).get("id")
    print(f"✓ X へ投稿しました: https://x.com/i/web/status/{tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
