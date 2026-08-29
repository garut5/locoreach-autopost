#!/usr/bin/env python3
"""
縦動画を Threads へ投稿する。

    python3 channels/threads_video.py --video-url https://media.camomile.co.jp/reels/x.mp4 --day fri
    python3 channels/threads_video.py --video-url ... --dry-run

環境変数
  THREADS_TOKEN     Threads の長期アクセストークン（post.py と同じもの）
  THREADS_USER_ID   未設定なら /me から自動取得
  NARRATION_USED    ナレーションを入れた場合は 1
  TTS_CREDIT        クレジット文言

設計メモ
  毎日20:00のカルーセル投稿（post.py）には手を出さない。
  あちらは画像4枚で完成しているので、動画に置き換えると別の判断が要る。
  ここは縦動画を作ったときに、その投稿先として選べるようにするためのもの。

  Threads の本文は500字。リールのキャプションは350字前後あるので
  だいたい収まるが、超える場合は改行の切れ目で詰める。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (ROOT, load_item, post_form, reachable, reel_caption, reel_target,
                     request, strip_lines, PROFILE_LINE)  # noqa: E402

API = "https://graph.threads.net/v1.0"
LIMIT = 500
UTM = {"utm_source": "threads", "utm_medium": "social", "utm_campaign": "sns"}


def link_with_utm(day: str) -> str:
    """記事へのリンク。Threads は本文中のURLを踏める。"""
    base, slug = reel_target(
        os.environ.get("THREADS_LINK", "https://media.camomile.co.jp/").strip())
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    present = {k for k, _ in query}
    for k, v in {**UTM, "utm_content": slug or day}.items():
        if k not in present:
            query.append((k, v))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def text_for(day: str, item: dict, narration_used: bool) -> str:
    """フィードと同じ本文を使い、500字に収める。"""
    blocks = [b.strip() for b in reel_caption(day, item).split("\n\n") if b.strip()]
    tags = [t for t in (blocks[-1].split() if blocks and blocks[-1].startswith("#") else [])
            if t.startswith("#")]
    body = strip_lines([b for b in blocks if not b.startswith("#")], (PROFILE_LINE,))

    credit = ""
    if narration_used:
        c = os.environ.get("TTS_CREDIT", "").strip()
        if c:
            credit = f"\n\n音声: {c}"

    # リンクは tail に入れて先に予算を取る。本文と同じ扱いにすると、
    # 500字に収める過程で最初に落ちるのがリンクになる
    tail = ("\n\n▼続きはこちら\n" + link_with_utm(day)
            + ("\n\n" + " ".join(tags[:5]) if tags else "") + credit)
    budget = LIMIT - len(tail)

    out: list[str] = []
    used = 0
    for block in body:
        add = len(block) + (2 if out else 0)
        if used + add > budget:
            break
        out.append(block)
        used += add
    return ("\n\n".join(out) + tail)[:LIMIT]


def create_container(uid: str, video_url: str, text: str, token: str) -> str:
    r = post_form(f"{API}/{uid}/threads", {
        "media_type": "VIDEO",
        "video_url": video_url,
        "text": text,
        "access_token": token,
    })
    cid = r.get("id")
    if not cid:
        raise RuntimeError(f"コンテナ作成に失敗しました: {r}")
    return str(cid)


def wait_ready(container: str, token: str, timeout_sec: int = 600) -> None:
    """動画の取り込みが終わるまで待つ。VIDEO は即時に publish できない。"""
    deadline = time.time() + timeout_sec
    last = ""
    while time.time() < deadline:
        r = request(f"{API}/{container}?fields=status,error_message"
                    f"&access_token={urllib.parse.quote(token)}")
        status = r.get("status", "")
        if status != last:
            print(f"    取り込み状況: {status}")
            last = status
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Threads 側で取り込みに失敗しました: {r.get('error_message')}")
        time.sleep(10)
    raise RuntimeError(f"{timeout_sec}秒経っても取り込みが完了しませんでした（最後の状態: {last}）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-url", required=True)
    ap.add_argument("--day")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day, item = load_item(args.day)
    if not item:
        print(f"{day} のコンテンツがないので何もしません")
        return 0

    narration_used = os.environ.get("NARRATION_USED", "").strip() == "1"
    text = text_for(day, item, narration_used)

    print("─" * 52)
    print(f"[Threads 動画] {day} / {args.video_url}")
    print("─" * 52)
    print(text)
    print("─" * 52)
    print(f"{len(text)} 文字 / 上限 {LIMIT}")

    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0

    token = os.environ.get("THREADS_TOKEN", "").strip()
    if not token:
        print("⚠ THREADS_TOKEN が未設定のため投稿をスキップします")
        return 0

    size, ctype = reachable(args.video_url)
    print(f"  動画の到達確認: {size/1024/1024:.1f}MB / {ctype}")

    uid = os.environ.get("THREADS_USER_ID", "").strip()
    if not uid:
        uid = str(request(f"{API}/me?fields=id&access_token={urllib.parse.quote(token)}")["id"])
        print(f"  THREADS_USER_ID を自動取得: {uid}")

    container = create_container(uid, args.video_url, text, token)
    print(f"  コンテナ作成: {container}")
    wait_ready(container, token)

    r = post_form(f"{API}/{uid}/threads_publish",
                  {"creation_id": container, "access_token": token})
    print(f"✓ Threads へ動画を投稿しました: {r.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
