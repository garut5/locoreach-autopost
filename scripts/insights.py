#!/usr/bin/env python3
"""
Instagram の反応を読んで、どの軸が伸びているかを集計する。

    python3 scripts/insights.py            人が読む形で出す
    python3 scripts/insights.py --write    insights.json に書き出す

## なぜやるか
「バズる題材」を先読みすることは誰にもできない。できるのは
**反応が出た方向に寄せ続けること**だけ。そのための材料を機械的に作る。

出した insights.json は public なので、記事生成側（private リポジトリ）から
raw で読める。次に書くキーワードの優先度に反映させるのが目的。

## 対応づけの方法
投稿の本文の1行目は記事タイトルそのもの（make_post.py / short.py がそう組む）。
公開RSSのタイトルと突き合わせれば、その投稿がどのカテゴリの記事だったかが分かる。
一致しない投稿（記事連動より前のもの）は「その他」に入れる。

環境変数
  IG_TOKEN   未設定なら何もしない
  LIMIT      さかのぼる投稿数。既定 60
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

IG = "https://graph.instagram.com/v21.0"
# 取れる指標はメディアの種類やアカウントの状態で変わる。
# 多いものから試して、断られたら順に減らす
METRIC_LADDER = [
    "reach,saved,total_interactions,profile_visits,follows",
    "reach,saved,total_interactions",
    "reach,saved",
    "reach",
]


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "locoreach-autopost/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read().decode() or "{}").get("error", {"message": str(e)})}


def media(token: str, limit: int) -> list[dict]:
    q = urllib.parse.urlencode({
        "fields": "id,caption,timestamp,media_type,permalink",
        "limit": limit, "access_token": token})
    body = get(f"{IG}/me/media?{q}")
    if "error" in body:
        sys.exit(f"投稿一覧を取れません: {body['error'].get('message')}")
    return body.get("data") or []


def insights(mid: str, token: str) -> dict:
    for metrics in METRIC_LADDER:
        q = urllib.parse.urlencode({"metric": metrics, "access_token": token})
        body = get(f"{IG}/{mid}/insights?{q}")
        if "error" not in body:
            return {d["name"]: d["values"][0]["value"] for d in body.get("data", [])}
    return {}


def article_index() -> dict[str, dict]:
    """公開記事のタイトル → カテゴリ。投稿の1行目と突き合わせる。"""
    import article

    out = {}
    try:
        for it in article.feed_items():
            out[it["title"].strip()] = it
    except Exception as e:
        print(f"  ⚠ RSS を読めませんでした（{e}）。カテゴリ別の集計は省きます")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="insights.json に書き出す")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMIT", "60")))
    args = ap.parse_args()

    token = os.environ.get("IG_TOKEN", "").strip()
    if not token:
        print("IG_TOKEN が未設定のため何もしません")
        return 0

    posts = media(token, args.limit)
    index = article_index()
    print(f"投稿 {len(posts)} 件 / 記事 {len(index)} 本と突き合わせます\n")

    by_cat: dict[str, list[dict]] = {}
    rows = []
    for p in posts:
        head = (p.get("caption") or "").splitlines()[0].strip() if p.get("caption") else ""
        art = index.get(head)
        cat = (art or {}).get("category", "その他")
        m = insights(p["id"], token)
        if not m:
            continue
        rec = {"permalink": p.get("permalink"), "timestamp": p.get("timestamp"),
               "title": head[:40], "category": cat, **m}
        rows.append(rec)
        by_cat.setdefault(cat, []).append(rec)

    if not rows:
        print("指標を取れた投稿がありませんでした。")
        return 0

    def avg(items, key):
        vals = [i[key] for i in items if isinstance(i.get(key), (int, float))]
        return round(statistics.mean(vals), 1) if vals else 0.0

    print(f"{'カテゴリ':<28} {'本数':>4} {'平均リーチ':>9} {'平均保存':>8} {'保存率':>7}")
    ranked = []
    for cat, items in by_cat.items():
        r, sv = avg(items, "reach"), avg(items, "saved")
        rate = round(sv / r * 100, 1) if r else 0.0
        ranked.append({"category": cat, "posts": len(items), "reach": r, "saved": sv, "save_rate": rate})
    ranked.sort(key=lambda x: (-x["save_rate"], -x["reach"]))
    for x in ranked:
        print(f"{x['category']:<28} {x['posts']:>4} {x['reach']:>9} {x['saved']:>8} {x['save_rate']:>6}%")

    print("\n伸びている投稿（保存の多い順に5件）")
    for r in sorted(rows, key=lambda x: -(x.get("saved") or 0))[:5]:
        print(f"  保存 {r.get('saved', 0):>4}  リーチ {r.get('reach', 0):>5}  {r['title']}")
        print(f"        {r['permalink']}")

    if args.write:
        out = {
            "generated_from": "instagram",
            "posts_analyzed": len(rows),
            "by_category": ranked,
            "note": "save_rate の高い軸を、次のキーワード選定で優先する",
        }
        (ROOT / "insights.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n→ insights.json に書き出しました（{len(ranked)} 軸）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
