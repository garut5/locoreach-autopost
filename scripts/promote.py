#!/usr/bin/env python3
"""
media.camomile.co.jp の最新記事を Threads へ投稿する。

    python3 scripts/promote.py            # 直近1本
    python3 scripts/promote.py --dry-run  # 投稿せず内容だけ表示
    python3 scripts/promote.py --slug xxx # 特定の記事

環境変数
  THREADS_TOKEN    Threads の長期アクセストークン
  THREADS_USER_ID  未設定なら /me から自動取得
  FEED_URL         既定 https://media.camomile.co.jp/feed.xml

## なぜ記事リポジトリではなく RSS を読むのか
Owned-Media は private で、private の Actions は GitHub の無料枠を消費する。
このリポジトリは public なので Actions が無料・無制限になる。
記事の中身は公開済みの RSS から取れるため、private 側を触らずに済む。

投稿済みの記録は posted.json に残す。同じ記事を二度出さないため。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "posted.json"
API = "https://graph.threads.net/v1.0"
LIMIT = 500  # Threads の本文上限
UTM_MEDIUM = "social"
UTM_CAMPAIGN = "media"

# 記事URLのカテゴリ部分 → ハッシュタグ。Owned-Media の theme.json と同じ7分類。
TAGS = {
    "meo": "#MEO #Googleビジネスプロフィール #店舗集客",
    "review": "#口コミ #Google口コミ #店舗集客",
    "website": "#ホームページ制作 #店舗集客 #Web集客",
    "aio": "#AI検索 #AIO #店舗集客",
    "ai-tool": "#店舗DX #AI活用 #個人店",
    "subsidy": "#補助金 #IT導入補助金 #店舗経営",
    "keiei": "#店舗経営 #集客 #個人店",
}


def http(url: str, data: dict | None = None, method: str = "GET") -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"User-Agent": "locoreach-media/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"HTTP {err.code}: {err.read().decode(errors='replace')[:400]}") from None


def fetch_items(feed_url: str) -> list[dict]:
    """RSS を新しい順に返す。"""
    req = urllib.request.Request(feed_url, headers={"User-Agent": "locoreach-media/1.0"})
    with urllib.request.urlopen(req, timeout=45) as res:
        root = ET.fromstring(res.read().decode())

    items = []
    for node in root.findall("./channel/item"):
        link = (node.findtext("link") or "").strip()
        path = urllib.parse.urlsplit(link).path.strip("/").split("/")
        if len(path) < 2:
            continue
        items.append({
            "title": (node.findtext("title") or "").strip(),
            "description": (node.findtext("description") or "").strip(),
            "link": link,
            "category": path[-2],   # /meo/gbp-.../ の meo
            "slug": path[-1],
        })
    return items


def with_utm(url: str, source: str, slug: str) -> str:
    """記事URLに UTM を付ける。既に同名のクエリがあれば上書きしない。"""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    present = {k for k, _ in query}
    for key, value in (("utm_source", source), ("utm_medium", UTM_MEDIUM),
                       ("utm_campaign", UTM_CAMPAIGN), ("utm_content", slug)):
        if key not in present:
            query.append((key, value))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def compose(item: dict) -> str:
    """Threads 用の本文。500字を超えないよう説明文側で詰める。"""
    url = with_utm(item["link"], "threads", item["slug"])
    title = item["title"]
    desc = item["description"]
    tags = TAGS.get(item["category"], "#店舗集客 #MEO")

    tail = f"\n\n▼続きはこちら\n{url}\n\n{tags}"
    room = LIMIT - len(tail) - len(title) - 2
    if room < 40:
        desc = ""
    elif len(desc) > room:
        desc = desc[: room - 1] + "…"

    text = f"{title}\n\n{desc}{tail}" if desc else f"{title}{tail}"
    return text[:LIMIT]


def post_to_threads(text: str, token: str, user_id: str) -> str:
    created = http(f"{API}/{user_id}/threads",
                   {"media_type": "TEXT", "text": text, "access_token": token}, method="POST")
    container = created.get("id")
    if not container:
        raise RuntimeError(f"コンテナ作成に失敗: {created}")

    time.sleep(5)  # Meta の推奨待機

    published = http(f"{API}/{user_id}/threads_publish",
                     {"creation_id": container, "access_token": token}, method="POST")
    pid = published.get("id")
    if not pid:
        raise RuntimeError(f"公開に失敗: {published}")
    return pid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    feed_url = os.environ.get("FEED_URL", "https://media.camomile.co.jp/feed.xml").strip()
    items = fetch_items(feed_url)
    if not items:
        print("RSS に記事がありません")
        return 0

    if args.slug:
        item = next((i for i in items if i["slug"] == args.slug), None)
        if item is None:
            sys.exit(f"slug={args.slug} の記事が RSS に見つかりません")
    else:
        item = items[0]

    text = compose(item)
    print("─" * 52)
    print(text)
    print("─" * 52)
    print(f"{len(text)} 文字 / 上限 {LIMIT}")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    done = state.setdefault("threads", [])
    if item["slug"] in done:
        print(f"→ {item['slug']} は投稿済みのためスキップします")
        return 0

    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0

    token = os.environ.get("THREADS_TOKEN", "").strip()
    if not token:
        print("⚠ THREADS_TOKEN が未設定のため投稿をスキップします")
        return 0

    user_id = os.environ.get("THREADS_USER_ID", "").strip()
    if not user_id:
        user_id = str(http(f"{API}/me?fields=id&access_token={urllib.parse.quote(token)}")["id"])
        print(f"  THREADS_USER_ID を自動取得: {user_id}")

    pid = post_to_threads(text, token, user_id)
    print(f"✓ Threads へ投稿しました: {pid}")

    done.append(item["slug"])
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
