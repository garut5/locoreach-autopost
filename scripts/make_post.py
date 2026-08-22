#!/usr/bin/env python3
"""
その日の記事から、SNS投稿一式を作る。

    python3 scripts/make_post.py --outdir out/post
    python3 scripts/make_post.py --slug xxxx --outdir out/post

出るもの
  <接頭辞>01.png … 1080x1350 のカルーセル（表紙＋見出し＋CTA）
  <接頭辞>story.png … 1080x1920 のストーリーズ
  post.json     … content.json の1日ぶんと同じ形。post.py に POST_ITEM で渡せる

ファイル名に日付を入れるのは、R2 の配信が immutable キャッシュだから。
同じ名前で上書きしても古い画像が返り続ける。

## なぜこれを作るのか
content.json は月〜日の7セットが固定で、どこからも書き換えられていない。
つまり**毎週まったく同じ投稿が繰り返される**。フォローした人には
毎週同じものが見えるし、伸ばそうとした時点で頭打ちになる。

記事は毎朝1本ずつ新しく公開されているので、そこから作れば
中身が毎日変わり、しかも記事（＝診断フォームへの導線）に送客できる。

見た目とアクセント色は記事ページ自身から取る。色の二重管理をしない。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "video"))
sys.path.insert(0, str(ROOT / "scripts"))

import article  # noqa: E402
import cardkit  # noqa: E402
from short import wrap  # noqa: E402

CAROUSEL = (1080, 1350)
STORY = (1080, 1920)
MAX_POINTS = 6          # 表紙とCTAを足して最大8枚
UTM = "utm_source=instagram&utm_medium=social&utm_campaign=media"
CDN = "https://media.camomile.co.jp/sns"


def first_sentence(text: str, limit: int = 60) -> str:
    for sep in ("。", "！", "？"):
        if sep in text[:limit]:
            return text.split(sep)[0] + sep
    return text[:limit]


def build(a: dict, outdir: Path, prefix: str) -> dict:
    accent = a.get("accent") or cardkit.ACCENTS[0]
    chip = a.get("chip") or "店舗集客"
    points = a["sections"][:MAX_POINTS]
    if not points:
        raise SystemExit("記事から見出しを取れませんでした。")

    outdir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []

    def card(n: int, kicker: str, headline: list[str], body: list[str], head_size: int, corner: str = "") -> None:
        name = f"{prefix}{n:02d}.png"
        cardkit.render(outdir / name, kicker, headline, body, accent,
                       size=CAROUSEL, head_size=head_size, corner=corner, safe=(0.13, 0.83))
        names.append(name)

    # 1 表紙。1枚目で「何の話か」と「何本あるか」を出す
    card(1, chip, wrap(a["title"], width=13, limit=5),
         [f"確認すること {len(points)}つ"], 78)

    # 2〜 見出し
    for i, s in enumerate(points, 1):
        body = wrap(first_sentence(s["lead"]), width=22, limit=3) if s["lead"] else []
        card(i + 1, f"{i:02d}", wrap(s["title"], width=12, limit=3), body, 74,
             corner=f"{i}/{len(points)}")

    # 最後 CTA
    card(len(points) + 2, "続きは記事で",
         ["保存して", "あとで読む"],
         ["プロフィールのリンクから記事へ", "無料のMEO診断もそこから"], 78)

    story = f"{prefix}story.png"
    cardkit.render(outdir / story, chip, wrap(a["title"], width=12, limit=4),
                   ["詳しくはプロフィールのリンクから"], accent, size=STORY, head_size=80)

    caption = "\n\n".join([
        a["title"],
        first_sentence(a["description"], 100),
        "▼この投稿でわかること\n" + "\n".join(f"{i:02d} {s['title']}" for i, s in enumerate(points, 1)),
        "続きは記事にまとめています。プロフィールのリンクからどうぞ。\n"
        "無料のMEO診断もそこから受け取れます。",
        f"店舗の集客・経営のヒントは @locoreach_ai から毎日発信中！",
    ])

    # content.json の1日ぶんと同じ形にしておく。post.py がそのまま食える
    meta = {
        "genre": f'記事連動：{chip}',
        "image_urls": [f"{CDN}/{n}" for n in names],
        "story_url": f"{CDN}/{story}",
        "caption": caption,
        "title": a["title"],
        "url": f'{a["link"]}?{UTM}',
        "accent": accent,
        "slug": a["slug"],
    }
    (outdir / "post.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--name-prefix", dest="prefix", default="",
                    help="ファイル名の接頭辞。既定は a<YYYYMMDD>-")
    args = ap.parse_args()

    prefix = args.prefix
    if not prefix:
        import datetime

        jst = datetime.timezone(datetime.timedelta(hours=9))
        prefix = "a" + datetime.datetime.now(jst).strftime("%Y%m%d") + "-"

    a = article.load(args.slug)
    meta = build(a, Path(args.outdir), prefix)
    print(f"{meta['title']}")
    print(f"{meta['url']}")
    print(f"アクセント {meta['accent']} / カルーセル {len(meta['image_urls'])}枚 + ストーリーズ1枚\n")
    print("─" * 52)
    print(meta["caption"])
    print("─" * 52)
    print(f"{len(meta['caption'])} 文字")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
