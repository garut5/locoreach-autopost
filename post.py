#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
locoreach_ai 毎日自動投稿（GitHub Actions 用）
- content.json から「今日（JST）の曜日」のジャンルを選び、カルーセルを投稿する
- アクセストークンは環境変数 IG_TOKEN（GitHubのSecretsに保存）から読む
- 該当曜日のコンテンツが無ければ何もしない（月・火など未設定の日はスキップ）
- DRY_RUN=1 のときは投稿せず内容だけ表示（テスト用）
"""
import os, sys, json, time, datetime, urllib.request, urllib.parse

GRAPH_VERSION = "v21.0"
BASE = f"https://graph.instagram.com/{GRAPH_VERSION}"
TOKEN = os.environ.get("IG_TOKEN", "").strip()
DRY = os.environ.get("DRY_RUN", "") == "1"

WEEKDAY_KEY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def jst_today_key():
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    return WEEKDAY_KEY[now.weekday()], now.strftime("%Y-%m-%d %H:%M JST")


def _get(path, params):
    with urllib.request.urlopen(f"{BASE}/{path}?{urllib.parse.urlencode(params)}") as r:
        return json.loads(r.read().decode())


def _post(path, params):
    req = urllib.request.Request(f"{BASE}/{path}", data=urllib.parse.urlencode(params).encode(), method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def main():
    key, stamp = jst_today_key()
    content = json.load(open(os.path.join(os.path.dirname(__file__), "content.json"), encoding="utf-8"))
    print(f"[{stamp}] 今日の曜日キー: {key}")

    item = content.get(key)
    if not item:
        print(f"  → {key} のコンテンツは未設定。今日は投稿しません。")
        return
    urls = item["image_urls"]
    caption = item["caption"]
    print(f"  → ジャンル: {item.get('genre')} / 画像 {len(urls)}枚")

    if DRY:
        print("[DRY_RUN] 投稿しません。以下を投稿予定でした:")
        print(caption)
        return
    if not TOKEN:
        raise SystemExit("IG_TOKEN が設定されていません（GitHubのSecretsを確認）。")

    me = _get("me", {"fields": "user_id,username", "access_token": TOKEN})
    uid = str(me.get("user_id") or me.get("id"))
    print(f"  投稿アカウント: {me.get('username')} (id={uid})")

    children = []
    for i, u in enumerate(urls, 1):
        it = _post(f"{uid}/media", {"image_url": u, "is_carousel_item": "true", "access_token": TOKEN})
        children.append(it["id"])
        print(f"    画像 {i}/{len(urls)} 準備OK")
        time.sleep(1)

    cont = _post(f"{uid}/media", {"media_type": "CAROUSEL", "children": ",".join(children),
                                  "caption": caption, "access_token": TOKEN})
    time.sleep(5)
    pub = _post(f"{uid}/media_publish", {"creation_id": cont["id"], "access_token": TOKEN})
    print("✅ 投稿完了:", pub)


if __name__ == "__main__":
    main()
