#!/usr/bin/env python3
"""
リール動画を YouTube ショートとして投稿する。

    python3 channels/youtube.py --file out/reel.mp4 --day fri
    python3 channels/youtube.py --file out/reel.mp4 --dry-run

環境変数（3つそろっていなければ何もせず終了する）
  YT_CLIENT_ID / YT_CLIENT_SECRET   Google Cloud の OAuth クライアント（デスクトップ）
  YT_REFRESH_TOKEN                  youtube.upload スコープのリフレッシュトークン
  YT_PRIVACY                        public / unlisted / private。既定 public
  YT_LINK                           概要欄の誘導先。既定 https://media.camomile.co.jp/
  TTS_CREDIT / NARRATION_USED       ナレーションを入れた回のクレジット表記

ショート判定は投稿時の指定ではなく、YouTube 側が動画の形で行う。
縦（9:16）で3分以内なら自動でショート扱いになるので、build.py の出力を
そのまま上げれば足りる。#Shorts は保険で概要欄に入れている。

アップロードは resumable を使う。単発 PUT だと数十MBで切れることがあるため。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_item, post_form  # noqa: E402

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
TITLE_LIMIT = 100
DESC_LIMIT = 4800  # 上限は5000。ハッシュタグ追記の余地を残す
UTM = {"utm_source": "youtube", "utm_medium": "social", "utm_campaign": "sns"}
# 「ハウツーとスタイル」。店舗運営のノウハウなのでここに置く
CATEGORY_ID = "26"


def access_token() -> str:
    r = post_form(TOKEN_URL, {
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    return r["access_token"]


def link_with_utm(day: str) -> str:
    base = os.environ.get("YT_LINK", "https://media.camomile.co.jp/").strip()
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    present = {k for k, _ in query}
    for k, v in {**UTM, "utm_content": day}.items():
        if k not in present:
            query.append((k, v))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def title_and_description(day: str, item: dict) -> tuple[str, str, list[str]]:
    caption = item.get("caption") or ""
    blocks = [b.strip() for b in caption.split("\n\n") if b.strip()]
    headline = blocks[0].split("\n")[0] if blocks else item.get("genre", "")
    headline = headline.replace("<", "＜").replace(">", "＞")
    title = headline if len(headline) <= TITLE_LIMIT else headline[: TITLE_LIMIT - 1] + "…"

    tags = [t.lstrip("#") for t in (blocks[-1].split() if blocks and blocks[-1].startswith("#") else [])
            if t.startswith("#")]

    # YouTube はタイトル・概要欄に < > を置けない。Instagram のハンドルは
    # ここでは別人の @ 扱いになるので、その行ごと落とす。
    body = []
    for b in blocks:
        if b.startswith("#"):
            continue
        kept = [ln for ln in b.split("\n") if "@locoreach_ai" not in ln]
        if kept:
            body.append("\n".join(kept))
    parts = ["\n\n".join(body), "", link_with_utm(day), "", "#Shorts " + " ".join(f"#{t}" for t in tags[:8])]
    if os.environ.get("NARRATION_USED", "").strip() == "1":
        credit = os.environ.get("TTS_CREDIT", "VOICEVOX:ずんだもん").strip()
        if credit:
            parts += ["", f"音声: {credit}"]
    desc = "\n".join(parts).replace("<", "＜").replace(">", "＞")
    return title, desc[:DESC_LIMIT], tags[:15]


def start_session(token: str, meta: dict, size: int) -> str:
    req = urllib.request.Request(
        f"{UPLOAD_URL}?{urllib.parse.urlencode({'uploadType': 'resumable', 'part': 'snippet,status'})}",
        data=json.dumps(meta).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            location = res.headers.get("Location")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"アップロードの開始に失敗しました HTTP {e.code}\n{e.read().decode()[:600]}") from None
    if not location:
        raise RuntimeError("アップロード先の URL が返りませんでした")
    return location


def upload(location: str, path: Path, token: str) -> dict:
    req = urllib.request.Request(
        location, data=path.read_bytes(), method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4",
                 "Content-Length": str(path.stat().st_size)},
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"アップロードに失敗しました HTTP {e.code}\n{e.read().decode()[:600]}") from None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--day")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day, item = load_item(args.day)
    if not item:
        print(f"{day} のコンテンツがないので何もしません")
        return 0

    title, description, tags = title_and_description(day, item)
    privacy = os.environ.get("YT_PRIVACY", "public").strip() or "public"

    print("─" * 52)
    print(f"[YouTube ショート] {day} / 公開設定 {privacy}")
    print(f"タイトル: {title}（{len(title)}/{TITLE_LIMIT}）")
    print("─" * 52)
    print(description)
    print("─" * 52)

    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0

    need = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if not all(os.environ.get(k, "").strip() for k in need):
        print("⚠ YouTube の認証情報が未設定のため投稿をスキップします")
        return 0

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"動画がありません: {path}")
    size = path.stat().st_size
    print(f"  動画: {size/1024/1024:.1f}MB")

    token = access_token()
    meta = {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": CATEGORY_ID},
        # 「子ども向け」の自己申告。店舗経営者向けなので false
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    location = start_session(token, meta, size)
    r = upload(location, path, token)
    vid = r.get("id")
    print(f"✓ YouTube へ投稿しました: https://www.youtube.com/shorts/{vid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
