#!/usr/bin/env python3
"""
ディレクトリの中身を Cloudflare R2 へ置く。

    python3 tools/upload_r2.py <ディレクトリ> --prefix sns

環境変数
  CLOUDFLARE_API_TOKEN   R2 の読み書き権限を持つトークン
  CLOUDFLARE_ACCOUNT_ID  アカウントID
  R2_BUCKET              既定 locoreach-reels

video/upload.py は mp4 を1本置くためのもので、
複数ファイルと Content-Type の出し分けができない。ここは画像用。
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
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4"}


def put(account: str, bucket: str, key: str, path: Path, token: str) -> None:
    req = urllib.request.Request(
        f"{API}/accounts/{account}/r2/buckets/{bucket}/objects/{key}",
        data=path.read_bytes(),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": TYPES.get(path.suffix.lower(), "application/octet-stream"),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as res:
            body = json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"アップロードに失敗しました {key}: HTTP {e.code} {e.read().decode()[:300]}")
    if not body.get("success"):
        sys.exit(f"アップロードに失敗しました {key}: {body.get('errors')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--prefix", default="sns", help="R2 上のキーの接頭辞")
    args = ap.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account:
        print("⚠ CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID が未設定のためスキップします")
        return 0

    bucket = os.environ.get("R2_BUCKET", "locoreach-reels")
    files = sorted(p for p in Path(args.directory).iterdir() if p.suffix.lower() in TYPES)
    if not files:
        sys.exit(f"置くファイルがありません: {args.directory}")

    total = 0
    for p in files:
        key = f"{args.prefix.strip('/')}/{p.name}"
        put(account, bucket, key, p, token)
        total += p.stat().st_size
        print(f"  ✓ {key}  {p.stat().st_size/1024:.0f}KB")

    print(f"\n{len(files)} 件 / {total/1024/1024:.1f}MB を {bucket} に置きました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
