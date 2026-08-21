#!/usr/bin/env python3
"""
リール動画を TikTok へ投稿する。

    python3 channels/tiktok.py --video-url https://media.camomile.co.jp/reels/x.mp4 --day fri
    python3 channels/tiktok.py --video-url ... --dry-run

環境変数（3つそろっていなければ何もせず終了する）
  TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET   開発者ポータルのアプリ
  TIKTOK_REFRESH_TOKEN                       video.publish（または video.upload）スコープ
  TIKTOK_MODE                                direct / inbox。既定 inbox
  TIKTOK_PRIVACY                             direct のときの公開範囲
  TIKTOK_LINK                                本文の誘導先。既定 https://media.camomile.co.jp/

## 最初は inbox（下書き）で始める理由
TikTok は審査が通るまで、直接公開できる範囲が SELF_ONLY（自分だけ）に制限される。
inbox は「アプリの下書き箱に送る」方式で、審査前でも使えて、
最後の公開だけスマホで押す運用になる。審査が通ったら TIKTOK_MODE=direct にする。

## PULL_FROM_URL の前提
動画は TikTok 側が URL から取りに来る。そのため media.camomile.co.jp を
開発者ポータルの URL プロパティとして所有権確認しておく必要がある。
未確認のまま呼ぶと url_ownership_unverified が返る。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_item, post_form, post_json, reachable, reel_caption  # noqa: E402

API = "https://open.tiktokapis.com/v2"
TITLE_LIMIT = 2200
UTM = {"utm_source": "tiktok", "utm_medium": "social", "utm_campaign": "sns"}


def access_token() -> str:
    r = post_form(f"{API}/oauth/token/", {
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
    })
    if "access_token" not in r:
        raise RuntimeError(f"トークンの更新に失敗しました: {r}")
    return r["access_token"]


def link_with_utm(day: str) -> str:
    base = os.environ.get("TIKTOK_LINK", "https://media.camomile.co.jp/").strip()
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    present = {k for k, _ in query}
    for k, v in {**UTM, "utm_content": day}.items():
        if k not in present:
            query.append((k, v))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def title_for(day: str, item: dict) -> str:
    """TikTok の本文。リンクはタップできないので短く1行だけ添える。"""
    blocks = [b.strip() for b in reel_caption(day, item).split("\n\n") if b.strip()]
    tags = [t for t in (blocks[-1].split() if blocks and blocks[-1].startswith("#") else []) if t.startswith("#")]
    body = []
    for b in blocks:
        if b.startswith("#"):
            continue
        kept = [ln for ln in b.split("\n") if "@locoreach_ai" not in ln]
        if kept:
            body.append("\n".join(kept))
    text = "\n\n".join(body)
    text += "\n\n詳しくは " + link_with_utm(day)
    if tags:
        text += "\n" + " ".join(tags[:6])
    if os.environ.get("NARRATION_USED", "").strip() == "1":
        credit = os.environ.get("TTS_CREDIT", "VOICEVOX:ずんだもん").strip()
        if credit and credit not in text:
            text += f"\n音声: {credit}"
    return text[:TITLE_LIMIT]


def creator_info(token: str) -> dict:
    r = post_json(f"{API}/post/publish/creator_info/query/", {},
                  {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    return r.get("data") or {}


def init_publish(token: str, video_url: str, title: str, mode: str, privacy: str) -> str:
    source = {"source": "PULL_FROM_URL", "video_url": video_url}
    if mode == "direct":
        path = "post/publish/video/init/"
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": source,
        }
    else:
        # 下書き箱へ送るだけ。本文はアプリ側で付ける仕様なので post_info は無い
        path = "post/publish/inbox/video/init/"
        payload = {"source_info": source}

    r = post_json(f"{API}/{path}", payload,
                  {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    err = (r.get("error") or {}).get("code", "ok")
    if err not in ("ok", ""):
        raise RuntimeError(f"投稿の開始に失敗しました: {r.get('error')}")
    return (r.get("data") or {})["publish_id"]


def wait_done(token: str, publish_id: str, timeout_sec: int = 600) -> str:
    deadline = time.time() + timeout_sec
    last = ""
    while time.time() < deadline:
        r = post_json(f"{API}/post/publish/status/fetch/", {"publish_id": publish_id},
                      {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
        data = r.get("data") or {}
        status = data.get("status", "")
        if status != last:
            print(f"    取り込み状況: {status}")
            last = status
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return status
        if status == "FAILED":
            raise RuntimeError(f"TikTok 側で失敗しました: {data.get('fail_reason')}")
        time.sleep(10)
    raise RuntimeError(f"{timeout_sec}秒経っても完了しませんでした（最後の状態: {last}）")


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

    mode = (os.environ.get("TIKTOK_MODE", "inbox").strip() or "inbox").lower()
    title = title_for(day, item)

    print("─" * 52)
    print(f"[TikTok] {day} / モード {mode} / 動画 {args.video_url}")
    print("─" * 52)
    print(title if mode == "direct" else "（inbox は本文を送れないため、公開時にアプリ側で入力します）")
    if mode != "direct":
        print("― 参考：direct に切り替えた場合の本文 ―")
        print(title)
    print("─" * 52)
    print(f"{len(title)} 文字 / 上限 {TITLE_LIMIT}")

    if args.dry_run:
        print("→ dry-run のため投稿しません")
        return 0

    need = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
    if not all(os.environ.get(k, "").strip() for k in need):
        print("⚠ TikTok の認証情報が未設定のため投稿をスキップします")
        return 0

    size, ctype = reachable(args.video_url)
    print(f"  動画の到達確認: {size/1024/1024:.1f}MB / {ctype}")

    token = access_token()

    privacy = os.environ.get("TIKTOK_PRIVACY", "").strip()
    if mode == "direct":
        info = creator_info(token)
        allowed = info.get("privacy_level_options") or []
        print(f"  選べる公開範囲: {allowed}")
        if not privacy:
            # 審査前は SELF_ONLY しか返らない。返ってきたものから素直に選ぶ
            privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in allowed else (allowed[0] if allowed else "SELF_ONLY")
        elif allowed and privacy not in allowed:
            sys.exit(f"TIKTOK_PRIVACY={privacy} はこのアカウントで使えません。選べるのは {allowed} です。")
        print(f"  公開範囲: {privacy}")

    publish_id = init_publish(token, args.video_url, title, mode, privacy)
    print(f"  publish_id: {publish_id}")
    status = wait_done(token, publish_id)
    if status == "SEND_TO_USER_INBOX":
        print("✓ TikTok アプリの下書き箱に届きました。アプリで本文を付けて公開してください。")
    else:
        print("✓ TikTok へ投稿しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
