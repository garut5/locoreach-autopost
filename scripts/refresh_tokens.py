#!/usr/bin/env python3
"""
Instagram / Threads の長期アクセストークンをリフレッシュし、
GitHub Actions の Secret を上書きする。

    python3 scripts/refresh_tokens.py instagram
    python3 scripts/refresh_tokens.py threads

仕様（Meta側）
  - 長期トークンの有効期間は60日。リフレッシュすると60日延びる。
  - リフレッシュできるのは「発行から24時間以上経過したトークン」のみ。
  - 60日を超えて放置したトークンは失効し、プログラムからは復旧できない
    （ブラウザでOAuthをやり直して再発行が必要）。

環境変数
  IG_TOKEN / THREADS_TOKEN   現在のトークン
  GH_TOKEN                   Secrets: Read and write 権限のある PAT
  SECRET_REPOS               更新先の owner/repo をカンマ区切りで。
                             未設定なら GITHUB_REPOSITORY（実行中のリポジトリ）だけ
  GITHUB_REPOSITORY          Actions が自動で設定する owner/repo

## なぜ複数リポジトリに書くのか
同じ IG_TOKEN / THREADS_TOKEN を garut5/locoreach-autopost（毎日20:00の投稿）と
garut5/Owned-Media（記事のThreads拡散）の両方が持っている。
片方だけ更新すると、もう片方は60日で失効して静かに止まる。
実際、以前は Owned-Media 側でしか更新しておらず、
locoreach-autopost のトークンは一度も更新されていなかった。
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROVIDERS = {
    "instagram": {
        "env": "IG_TOKEN",
        "secret": "IG_TOKEN",
        "url": "https://graph.instagram.com/refresh_access_token",
        "grant": "ig_refresh_token",
    },
    "threads": {
        "env": "THREADS_TOKEN",
        "secret": "THREADS_TOKEN",
        "url": "https://graph.threads.net/refresh_access_token",
        "grant": "th_refresh_token",
    },
}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "locoreach-media/1.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode())


def api(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "locoreach-media/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        raw = res.read().decode()
        return json.loads(raw) if raw.strip() else {}


def seal(public_key_b64: str, value: str) -> str:
    """libsodium sealed box。PyNaCl があれば使い、無ければ pip で入れる。"""
    try:
        from nacl import encoding, public  # type: ignore
    except ImportError:
        import subprocess

        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pynacl"], check=True)
        from nacl import encoding, public  # type: ignore

    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    return base64.b64encode(public.SealedBox(pk).encrypt(value.encode())).decode()


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in PROVIDERS:
        print(f"usage: {sys.argv[0]} [{'|'.join(PROVIDERS)}]", file=sys.stderr)
        return 2

    name = sys.argv[1]
    cfg = PROVIDERS[name]

    token = os.environ.get(cfg["env"], "").strip()
    if not token:
        print(f"⚠ {cfg['env']} が未設定のためスキップします")
        return 0

    url = f"{cfg['url']}?{urllib.parse.urlencode({'grant_type': cfg['grant'], 'access_token': token})}"
    try:
        data = get(url)
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:500]
        print(f"✗ {name} のリフレッシュに失敗しました（HTTP {err.code}）\n{detail}", file=sys.stderr)
        print(
            "  60日を超えて失効した場合、APIからは復旧できません。"
            "ブラウザでOAuthをやり直してトークンを再発行してください。",
            file=sys.stderr,
        )
        return 1

    new_token = data.get("access_token")
    expires_in = int(data.get("expires_in", 0))
    if not new_token:
        print(f"✗ {name}: access_token が返りませんでした: {data}", file=sys.stderr)
        return 1

    print(f"✓ {name} のトークンを更新しました（残り約 {expires_in // 86400} 日）")

    gh_token = os.environ.get("GH_TOKEN", "").strip()
    repos = [r.strip() for r in os.environ.get("SECRET_REPOS", "").split(",") if r.strip()]
    if not repos:
        here = os.environ.get("GITHUB_REPOSITORY", "").strip()
        repos = [here] if here else []

    if not gh_token or not repos:
        print("  GH_TOKEN / 更新先リポジトリが無いため、Secret の書き換えはスキップします")
        print("  （手元で実行した場合は、新しいトークンを手動で登録してください）")
        return 0

    if new_token == token:
        print("  値が変わらなかったため Secret はそのままにします")
        return 0

    # 1つ失敗しても残りは更新する。片方だけ古いまま残る方が事故が大きいため。
    failed = []
    for repo in repos:
        try:
            key = api("GET", f"/repos/{repo}/actions/secrets/public-key", gh_token)
            api(
                "PUT",
                f"/repos/{repo}/actions/secrets/{cfg['secret']}",
                gh_token,
                {"encrypted_value": seal(key["key"], new_token), "key_id": key["key_id"]},
            )
            print(f"  {repo} の Secret {cfg['secret']} を更新しました")
        except Exception as e:
            failed.append(repo)
            print(f"  ✗ {repo} の更新に失敗しました: {e}", file=sys.stderr)

    if failed:
        print(f"✗ 更新できなかったリポジトリ: {', '.join(failed)}", file=sys.stderr)
        print("  PAT がそのリポジトリの Secrets: Read and write を持っているか確認してください。",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
