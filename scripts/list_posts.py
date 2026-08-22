#!/usr/bin/env python3
"""
Instagram / Threads に実際に何が載っているかを、API から読んで並べる。

    python3 scripts/list_posts.py

「投稿したはず」と「載っている」は別物なので、投稿側のログではなく
アカウント側を見る。permalink をそのまま開けば現物を確認できる。

環境変数
  IG_TOKEN       未設定ならスキップ
  THREADS_TOKEN  未設定ならスキップ
  YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN  未設定ならスキップ
  LIMIT          取得件数。既定 10

YouTube は**どのチャンネルのトークンなのか**も出す。ブランドアカウントは
本人アカウントと別物なので、承認時に選び違えると別のチャンネルに上がる。
投稿してから気づくのは遅いので、先に名前で確かめる。

読み取りだけ。投稿も削除もしない。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

IG = "https://graph.instagram.com/v21.0"
TH = "https://graph.threads.net/v1.0"
LIMIT = os.environ.get("LIMIT", "10")


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "locoreach-autopost"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code} {e.read().decode()[:300]}"}


def show(title: str, base: str, path: str, fields: str, token: str) -> None:
    print("─" * 60)
    print(title)
    print("─" * 60)
    if not token:
        print("  トークンが未設定のためスキップします\n")
        return
    q = urllib.parse.urlencode({"fields": fields, "limit": LIMIT, "access_token": token})
    body = get(f"{base}/{path}?{q}")
    if "error" in body:
        print(f"  取得に失敗しました: {body['error']}\n")
        return
    items = body.get("data") or []
    if not items:
        print("  1件もありません\n")
        return
    for it in items:
        head = (it.get("caption") or it.get("text") or "").replace("\n", " ")[:40]
        kind = it.get("media_type", "")
        print(f"  {it.get('timestamp','')}  {kind:10} {it.get('permalink','(permalink なし)')}")
        if head:
            print(f"      {head}…")
    print(f"\n  {len(items)} 件\n")


def youtube() -> None:
    print("─" * 60)
    print("YouTube に載っているもの")
    print("─" * 60)
    cid = os.environ.get("YT_CLIENT_ID", "").strip()
    sec = os.environ.get("YT_CLIENT_SECRET", "").strip()
    ref = os.environ.get("YT_REFRESH_TOKEN", "").strip()
    if not (cid and sec and ref):
        print("  認証情報が未設定のためスキップします\n")
        return

    data = urllib.parse.urlencode({
        "client_id": cid, "client_secret": sec,
        "refresh_token": ref, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            token = json.loads(res.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        print(f"  トークンを更新できません: HTTP {e.code} {e.read().decode()[:200]}\n")
        return

    api = "https://www.googleapis.com/youtube/v3"
    q = urllib.parse.urlencode({
        "part": "snippet,contentDetails", "mine": "true", "access_token": token})
    body = get(f"{api}/channels?{q}")
    items = body.get("items") or []
    if not items:
        print(f"  チャンネルを取得できません: {body.get('error', '0件')}\n")
        return
    ch = items[0]
    print(f"  チャンネル: {ch['snippet']['title']}  ({ch['id']})")

    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    q = urllib.parse.urlencode({
        "part": "snippet", "playlistId": uploads, "maxResults": LIMIT, "access_token": token})
    body = get(f"{api}/playlistItems?{q}")
    vids = body.get("items") or []
    if not vids:
        print("  動画は1本もありません\n")
        return
    for v in vids:
        sn = v["snippet"]
        vid = sn["resourceId"]["videoId"]
        print(f"  {sn['publishedAt']}  https://youtube.com/shorts/{vid}")
        print(f"      {sn['title'][:50]}")
    print(f"\n  {len(vids)} 本\n")


def main() -> int:
    show(
        "Instagram に載っているもの",
        IG, "me/media", "id,permalink,timestamp,media_type,caption",
        os.environ.get("IG_TOKEN", "").strip(),
    )
    show(
        "Threads に載っているもの",
        TH, "me/threads", "id,permalink,timestamp,text",
        os.environ.get("THREADS_TOKEN", "").strip(),
    )
    youtube()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
