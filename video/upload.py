#!/usr/bin/env python3
"""
リール動画を Cloudflare R2 へ置き、公開URLを返す。

    python3 video/upload.py --file /tmp/reel.mp4 --name 2026-08-22-fri.mp4

環境変数
  CLOUDFLARE_API_TOKEN   R2 の読み書き権限を持つトークン
  CLOUDFLARE_ACCOUNT_ID  アカウントID
  R2_BUCKET              既定 locoreach-reels
  REELS_BASE_URL         既定 https://media.camomile.co.jp/reels

なぜ R2 か
  Instagram / YouTube / TikTok はいずれも「公開URLから動画を取得する」方式で、
  取得元が安定している必要がある。リポジトリに mp4 をコミットする案は
  年間1〜3GB 肥大するため採らない。
  R2 の r2.dev 直配信は本番非推奨のため、Owned-Media 側の Pages に
  R2 をバインドし media.camomile.co.jp/reels/ から返している。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"


def put_object(account: str, bucket: str, key: str, path: Path, token: str) -> None:
    url = f"{API}/accounts/{account}/r2/buckets/{bucket}/objects/{key}"
    data = path.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            body = json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"R2 へのアップロードに失敗しました: HTTP {e.code} {e.read().decode()[:300]}")
    if not body.get("success"):
        sys.exit(f"R2 へのアップロードに失敗しました: {body.get('errors')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--name", required=True, help="R2 上のオブジェクト名（そのままURLになる）")
    args = ap.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account:
        print("⚠ CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID が未設定のためアップロードをスキップします")
        return 0

    bucket = os.environ.get("R2_BUCKET", "locoreach-reels")
    base = os.environ.get("REELS_BASE_URL", "https://media.camomile.co.jp/reels").rstrip("/")

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"ファイルがありません: {path}")

    size = path.stat().st_size / 1024 / 1024
    put_object(account, bucket, args.name, path, token)
    url = f"{base}/{args.name}"
    print(f"✓ アップロード完了 {size:.1f}MB → {url}")

    # 後段（投稿処理）が拾えるように GitHub Actions の出力へ流す
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"video_url={url}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
