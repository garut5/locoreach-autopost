#!/usr/bin/env python3
"""
リール動画を Instagram Reels へ投稿する。

    python3 video/publish.py --video-url https://media.camomile.co.jp/reels/xxx.mp4 --day fri
    python3 video/publish.py --video-url ... --dry-run

環境変数
  IG_TOKEN        Instagram Graph API のトークン（post.py と同じもの）
  IG_USER_ID      未設定なら /me から自動取得
  NARRATION_USED  ナレーションを入れた場合は 1。クレジット表記を自動で付ける
  TTS_CREDIT      クレジット文言。既定 "VOICEVOX:ずんだもん"

設計メモ
  post.py（フィード／ストーリーズ／Threads）とは別ファイルにしている。
  リールの失敗が既存3チャネルの投稿を巻き込まないようにするため。
  動画は公開URLから Instagram 側が取得するので、先に R2 へ置いておくこと。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IG_BASE = "https://graph.instagram.com/v21.0"
CAPTION_LIMIT = 2200
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _req(url: str, data: dict | None = None, method: str = "GET") -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "locoreach-reels/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None


def caption_for(day: str, narration_used: bool) -> str:
    """フィードと同じ本文を使い、必要ならクレジットを足す。"""
    if os.environ.get("REEL_FORMAT", "").strip() == "short":
        import sys as _sys

        _sys.path.insert(0, str(ROOT / "video"))
        import short as _short

        text = _short.caption(day)
    else:
        content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
        text = (content.get(day) or {}).get("caption", "")

    if narration_used:
        credit = os.environ.get("TTS_CREDIT", "VOICEVOX:ずんだもん").strip()
        if credit and credit not in text:
            # 規約上クレジット表記が必要なので、必ず入る位置（末尾）に置く
            line = f"\n\n音声: {credit}"
            if len(text) + len(line) > CAPTION_LIMIT:
                text = text[: CAPTION_LIMIT - len(line)]
            text += line
    return text[:CAPTION_LIMIT]


def create_container(uid: str, video_url: str, caption: str, token: str) -> str:
    r = _req(
        f"{IG_BASE}/{uid}/media",
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            # リールをプロフィールのフィードにも残す
            "share_to_feed": "true",
            "access_token": token,
        },
        method="POST",
    )
    return str(r["id"])


def wait_ready(container: str, token: str, timeout_sec: int = 600) -> None:
    """動画の取り込みが終わるまで待つ。REELS は即時に publish できない。"""
    deadline = time.time() + timeout_sec
    last = ""
    while time.time() < deadline:
        r = _req(f"{IG_BASE}/{container}?fields=status_code,status&access_token={urllib.parse.quote(token)}")
        code = r.get("status_code", "")
        if code != last:
            print(f"    取り込み状況: {code}")
            last = code
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"Instagram 側で動画の取り込みに失敗しました: {r.get('status')}")
        time.sleep(10)
    raise RuntimeError(f"{timeout_sec}秒経っても取り込みが完了しませんでした（最後の状態: {last}）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-url", required=True)
    ap.add_argument("--day")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.day:
        day = args.day
    else:
        import datetime

        jst = datetime.timezone(datetime.timedelta(hours=9))
        day = WEEKDAYS[datetime.datetime.now(jst).weekday()]

    narration_used = os.environ.get("NARRATION_USED", "").strip() == "1"
    caption = caption_for(day, narration_used)

    print("─" * 52)
    print(f"曜日: {day} / 動画: {args.video_url}")
    print(f"ナレーション: {'あり（クレジット付与）' if narration_used else 'なし'}")
    print("─" * 52)
    print(caption)
    print("─" * 52)
    print(f"{len(caption)} 文字 / 上限 {CAPTION_LIMIT}")

    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0

    token = os.environ.get("IG_TOKEN", "").strip()
    if not token:
        print("⚠ IG_TOKEN が未設定のため投稿をスキップします")
        return 0

    # 動画が本当に取得できるか、投稿前にこちらから確認する
    try:
        head = urllib.request.Request(args.video_url, method="HEAD")
        with urllib.request.urlopen(head, timeout=60) as res:
            size = int(res.headers.get("content-length") or 0)
            ctype = res.headers.get("content-type", "")
        print(f"  動画の到達確認: {size/1024/1024:.1f}MB / {ctype}")
    except Exception as e:
        sys.exit(f"動画URLに到達できません。投稿を中止します: {e}")

    uid = os.environ.get("IG_USER_ID", "").strip()
    if not uid:
        uid = str(_req(f"{IG_BASE}/me?fields=id&access_token={urllib.parse.quote(token)}")["id"])
        print(f"  IG_USER_ID を自動取得: {uid}")

    container = create_container(uid, args.video_url, caption, token)
    print(f"  コンテナ作成: {container}")
    wait_ready(container, token)

    r = _req(f"{IG_BASE}/{uid}/media_publish", {"creation_id": container, "access_token": token}, method="POST")
    print(f"✓ リールを投稿しました: {r.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
