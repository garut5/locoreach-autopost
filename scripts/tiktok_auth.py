#!/usr/bin/env python3
"""
TikTok の認可を通してリフレッシュトークンを得る。

    python3 scripts/tiktok_auth.py url               認可URLを出す
    python3 scripts/tiktok_auth.py exchange --code X 認可コードを交換する

## なぜこの形か
TikTok には Google の OAuth Playground にあたるものが無い。
リフレッシュトークンを取るには、登録済みのリダイレクト先で認可コードを
受け取り、シークレットと一緒に交換する必要がある。

コードの受け取りは media.camomile.co.jp/tiktok/callback（表示するだけ）。
交換はここで行い、得たトークンはそのまま Secrets に書き戻す。
**シークレットもリフレッシュトークンも、画面にもログにも出さない。**

環境変数
  TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET   開発者ポータルのアプリ
  TIKTOK_REDIRECT_URI  既定 https://media.camomile.co.jp/tiktok/callback
  GH_TOKEN             exchange のとき、Secrets を書き戻すために使う
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

AUTHORIZE = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "user.info.basic,video.upload"
REDIRECT = os.environ.get(
    "TIKTOK_REDIRECT_URI", "https://media.camomile.co.jp/tiktok/callback"
)


def need(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"{name} が未設定です。Secrets に登録してください。")
    return v


def url_cmd() -> int:
    key = need("TIKTOK_CLIENT_KEY")
    q = urllib.parse.urlencode({
        "client_key": key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT,
        # CSRF 対策の値。使い捨てなので固定でよい（人が1回押すだけの導線）
        "state": "locoreach",
    })
    print("─" * 60)
    print("この URL を開いて、TikTok アカウントで許可してください。")
    print("投稿させたいアカウントでログインしていることを確認してください。")
    print("─" * 60)
    print(f"{AUTHORIZE}?{q}")
    print("─" * 60)
    print(f"許可すると {REDIRECT} に戻り、認可コードが表示されます。")
    print("そのコードを『TikTok の認可コードを交換する』に貼ってください。")
    return 0


def exchange_cmd(code: str) -> int:
    key, secret = need("TIKTOK_CLIENT_KEY"), need("TIKTOK_CLIENT_SECRET")
    data = urllib.parse.urlencode({
        "client_key": key,
        "client_secret": secret,
        "code": urllib.parse.unquote(code.strip()),
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
    }).encode()
    req = urllib.request.Request(
        TOKEN, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            body = json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"交換に失敗しました HTTP {e.code}: {e.read().decode()[:400]}")

    if body.get("error"):
        sys.exit(f"交換に失敗しました: {body.get('error')} / {body.get('error_description')}")

    token = body.get("refresh_token")
    if not token:
        sys.exit(f"refresh_token が返りませんでした。応答のキー: {list(body)}")

    print(f"✓ 認可できました（scope: {body.get('scope')}）")
    print(f"  open_id: {str(body.get('open_id'))[:6]}…")
    print(f"  refresh_token の有効期限: 約 {int(body.get('refresh_expires_in', 0)) // 86400} 日")

    repo = os.environ.get("SECRET_REPO", "garut5/locoreach-autopost")
    r = subprocess.run(
        ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", repo],
        input=token, text=True, capture_output=True,
    )
    if r.returncode != 0:
        sys.exit(f"Secrets への書き戻しに失敗しました: {r.stderr[:300]}")
    print(f"  {repo} の Secret TIKTOK_REFRESH_TOKEN を更新しました")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["url", "exchange"])
    ap.add_argument("--code", default="")
    args = ap.parse_args()
    if args.mode == "url":
        return url_cmd()
    if not args.code.strip():
        sys.exit("--code が空です。認可コードを渡してください。")
    return exchange_cmd(args.code)


if __name__ == "__main__":
    raise SystemExit(main())
