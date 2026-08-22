#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
locoreach_ai 毎日自動投稿（GitHub Actions 用）
チャネル: Instagramフィード（カルーセル）＋ Instagramストーリーズ（表紙）＋ Threads（カルーセル）
- content.json から「今日（JST）の曜日」のジャンルを選ぶ
- IGトークンは環境変数 IG_TOKEN、Threadsトークンは THREADS_TOKEN（GitHub Secrets）
- 各チャネルは独立。1つ失敗しても他は続行する
- 該当曜日のコンテンツが無ければ何もしない（月・火など未設定日はスキップ）
- DRY_RUN=1 のときは投稿せず内容だけ表示（テスト用）
"""
import os, sys, json, time, datetime, urllib.request, urllib.parse

IG_VERSION = "v21.0"
IG_BASE = f"https://graph.instagram.com/{IG_VERSION}"
TH_VERSION = "v1.0"
TH_BASE = f"https://graph.threads.net/{TH_VERSION}"

IG_TOKEN = os.environ.get("IG_TOKEN", "").strip()
TH_TOKEN = os.environ.get("THREADS_TOKEN", "").strip()
DRY = os.environ.get("DRY_RUN", "") == "1"

WEEKDAY_KEY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def jst_today_key():
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    return WEEKDAY_KEY[now.weekday()], now.strftime("%Y-%m-%d %H:%M JST")


def _get(base, path, params):
    url = f"{base}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode())


def _post(base, path, params):
    req = urllib.request.Request(
        f"{base}/{path}", data=urllib.parse.urlencode(params).encode(), method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def threads_text(caption, limit=490):
    """Threadsは1投稿500字まで。改行の切れ目で自然に短縮する。"""
    if len(caption) <= limit:
        return caption
    cut = caption[:limit]
    nl = cut.rfind("\n")
    if nl > limit * 0.5:
        cut = cut[:nl]
    return cut.rstrip() + "…"


# ---------------- Instagram: フィード（カルーセル） ----------------
def post_ig_feed(urls, caption):
    me = _get(IG_BASE, "me", {"fields": "user_id,username", "access_token": IG_TOKEN})
    uid = str(me.get("user_id") or me.get("id"))
    print(f"  [IGフィード] アカウント: {me.get('username')} (id={uid})")
    children = []
    for i, u in enumerate(urls, 1):
        it = _post(IG_BASE, f"{uid}/media",
                   {"image_url": u, "is_carousel_item": "true", "access_token": IG_TOKEN})
        children.append(it["id"])
        print(f"    画像 {i}/{len(urls)} 準備OK")
        time.sleep(1)
    cont = _post(IG_BASE, f"{uid}/media",
                 {"media_type": "CAROUSEL", "children": ",".join(children),
                  "caption": caption, "access_token": IG_TOKEN})
    time.sleep(5)
    pub = _post(IG_BASE, f"{uid}/media_publish",
                {"creation_id": cont["id"], "access_token": IG_TOKEN})
    print("  ✅ IGフィード投稿完了:", pub)
    return uid


# ---------------- Instagram: ストーリーズ（表紙画像） ----------------
def post_ig_story(uid, cover_url):
    cont = _post(IG_BASE, f"{uid}/media",
                 {"media_type": "STORIES", "image_url": cover_url, "access_token": IG_TOKEN})
    time.sleep(3)
    pub = _post(IG_BASE, f"{uid}/media_publish",
                {"creation_id": cont["id"], "access_token": IG_TOKEN})
    print("  ✅ IGストーリーズ投稿完了:", pub)


# ---------------- Threads: カルーセル ----------------
def post_threads(urls, caption):
    me = _get(TH_BASE, "me", {"fields": "id,username", "access_token": TH_TOKEN})
    uid = str(me.get("id"))
    print(f"  [Threads] アカウント: {me.get('username')} (id={uid})")
    text = threads_text(caption)
    children = []
    for i, u in enumerate(urls, 1):
        it = _post(TH_BASE, f"{uid}/threads",
                   {"media_type": "IMAGE", "image_url": u,
                    "is_carousel_item": "true", "access_token": TH_TOKEN})
        children.append(it["id"])
        print(f"    画像 {i}/{len(urls)} 準備OK")
        time.sleep(1)
    cont = _post(TH_BASE, f"{uid}/threads",
                 {"media_type": "CAROUSEL", "children": ",".join(children),
                  "text": text, "access_token": TH_TOKEN})
    time.sleep(8)  # Threadsはカルーセル処理に少し時間が必要
    pub = _post(TH_BASE, f"{uid}/threads_publish",
                {"creation_id": cont["id"], "access_token": TH_TOKEN})
    print("  ✅ Threads投稿完了:", pub)


def main():
    key, stamp = jst_today_key()
    content = json.load(open(os.path.join(os.path.dirname(__file__), "content.json"), encoding="utf-8"))
    print(f"[{stamp}] 今日の曜日キー: {key}")

    # 記事から作った投稿があればそれを使う（scripts/make_post.py の出力）。
    # content.json は月〜日の7セット固定で、毎週同じ内容が繰り返されるため、
    # ふだんはこちらを使い、作れなかった日だけ従来の固定セットに落ちる。
    item = content.get(key)
    override = os.environ.get("POST_ITEM", "").strip()
    if override and os.path.exists(override):
        item = json.load(open(override, encoding="utf-8"))
        print(f" → 記事から作った投稿を使います: {override}")

    if not item:
        print(f" → {key} のコンテンツは未設定。今日は投稿しません。")
        return
    urls = item["image_urls"]
    caption = item["caption"]
    # ストーリーズ専用画像（9:16）。未設定なら従来どおりフィード1枚目を流用する。
    story_url = item.get("story_url") or urls[0]
    print(f" → ジャンル: {item.get('genre')} / 画像 {len(urls)}枚")

    if DRY:
        print("[DRY_RUN] 投稿しません。予定内容:")
        print(f"  IGフィード: カルーセル{len(urls)}枚 + キャプション")
        print(f"  IGストーリーズ: {'専用9:16' if item.get('story_url') else 'フィード1枚目の流用'} {story_url}")
        print(f"  Threads: カルーセル{len(urls)}枚 + テキスト（{len(threads_text(caption))}字）")
        print("--- caption ---")
        print(caption)
        return

    results = {}

    # Instagram（フィード → ストーリーズ）
    if IG_TOKEN:
        try:
            uid = post_ig_feed(urls, caption)
            results["ig_feed"] = "OK"
            try:
                # ストーリーズ専用画像があればそれを使う（無ければ従来どおり1枚目）
                post_ig_story(uid, story_url)
                results["ig_story"] = "OK"
            except Exception as e:
                results["ig_story"] = f"NG: {e}"
                print("  ⚠ IGストーリーズ失敗:", e)
        except Exception as e:
            results["ig_feed"] = f"NG: {e}"
            print("  ⚠ IGフィード失敗:", e)
    else:
        print("  IG_TOKEN 未設定のためInstagramはスキップ")

    # Threads
    if TH_TOKEN:
        try:
            post_threads(urls, caption)
            results["threads"] = "OK"
        except Exception as e:
            results["threads"] = f"NG: {e}"
            print("  ⚠ Threads失敗:", e)
    else:
        print("  THREADS_TOKEN 未設定のためThreadsはスキップ")

    print("=== 投稿結果 ===", json.dumps(results, ensure_ascii=False))
    # いずれかが失敗したら異常終了（Actionsで気づけるように）
    if any(v != "OK" for v in results.values()):
        raise SystemExit("一部のチャネルで投稿に失敗しました: " + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
