#!/usr/bin/env python3
"""
公開済みの記事を読んで、SNSに使える形に分解する。

    python3 scripts/article.py                 最新の記事
    python3 scripts/article.py --slug xxxx     スラッグ指定

公開RSSと記事ページだけを見る。private リポジトリを参照しないので、
public リポジトリの Actions から動かせる。
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request

FEED = "https://media.camomile.co.jp/feed.xml"
UA = {"User-Agent": "locoreach-autopost/1.0"}

# 本文の見出しではないもの。カルーセルの中身にしない
SKIP_HEADINGS = ("まとめ", "参照した一次情報", "あわせて読みたい")


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read().decode("utf-8", "replace")


def strip_tags(html: str) -> str:
    html = re.sub(r"<[^>]+>", "", html)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        html = html.replace(a, b)
    return re.sub(r"\s+", " ", html).strip()


def feed_items() -> list[dict]:
    xml = get(FEED)
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)

        def pick(tag: str) -> str:
            t = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return strip_tags(t.group(1)) if t else ""

        link = pick("link")
        items.append({
            "title": pick("title"),
            "link": link,
            "description": pick("description"),
            "category": pick("category"),
            "slug": link.rstrip("/").rsplit("/", 1)[-1],
            "section": link.rstrip("/").rsplit("/", 2)[-2] if link.count("/") >= 4 else "",
        })
    return items


# 出典ドメイン → 画面に出す名前。確信のあるものだけ書き、
# 知らないドメインはホスト名をそのまま出す（間違った名前を付けるより正確）。
SOURCE_NAMES = {
    "support.google.com": "Google 公式ヘルプ",
    "developers.google.com": "Google 公式ドキュメント",
    "developers.openai.com": "OpenAI 公式ドキュメント",
    "developers.cloudflare.com": "Cloudflare 公式ドキュメント",
    "www.ppc.go.jp": "個人情報保護委員会",
}


def _sources(html: str) -> list[str]:
    """「参照した一次情報」の出典名。重複を除いて出てきた順に返す。

    動画の裏づけカードに使う。数字や体験談を作らずに済ませるための素材で、
    ここが空なら裏づけカードは出さない（無い根拠を演出しない）。
    """
    i = html.find('class="sources"')
    if i < 0:
        return []
    block = html[i:html.find("</section>", i)]
    names, seen = [], set()
    for m in re.finditer(r'href="(https?://[^"]+)"', block):
        host = urllib.parse.urlsplit(m.group(1)).netloc
        name = SOURCE_NAMES.get(host) or host.removeprefix("www.")
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def parse(url: str) -> dict:
    """記事ページから、SNS に必要なものを取り出す。

    アクセント色は記事ページ自身が持っている（<article class="post" style="--accent:...">）。
    theme.json は private リポジトリにあって読めないので、
    ここから取れば二重管理にならず、ずれようがない。
    """
    html = get(url)
    out = {"accent": "", "chip": "", "sections": [], "sources": []}

    m = re.search(r'<article class="post"[^>]*--accent:\s*(#[0-9A-Fa-f]{6})', html)
    if m:
        out["accent"] = m.group(1).upper()
    m = re.search(r'<span class="chip"[^>]*>(.*?)</span>', html, re.S)
    if m:
        out["chip"] = strip_tags(m.group(1))

    out["sections"] = _sections(html)
    out["sources"] = _sources(html)
    return out


def _sections(html: str) -> list[dict]:
    """記事の h2 と、その直後の1段落を取り出す。"""
    i = html.find('<div class="post-body">')
    if i < 0:
        return []
    body = html[i:]
    for end in ('<section class="sources"', '<div class="cta', "<footer"):
        j = body.find(end)
        if j > 0:
            body = body[:j]
            break

    out = []
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|\Z)", body, re.S):
        title = strip_tags(m.group(1))
        if not title or any(title.startswith(s) for s in SKIP_HEADINGS):
            continue
        p = re.search(r"<p[^>]*>(.*?)</p>", m.group(2), re.S)
        out.append({"title": title, "lead": strip_tags(p.group(1)) if p else ""})
    return out


def load(slug: str = "") -> dict:
    items = feed_items()
    if not items:
        raise SystemExit("RSS から記事を取得できませんでした。")
    item = next((i for i in items if i["slug"] == slug), None) if slug else items[0]
    if not item:
        raise SystemExit(f"スラッグ {slug} の記事が見つかりません。")
    item.update(parse(item["link"]))
    return item


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    a = load(args.slug)
    if args.json:
        print(json.dumps(a, ensure_ascii=False, indent=2))
        return 0
    print(f"{a['title']}\n{a['link']}\nカテゴリ: {a['category']} / {a['chip']} / {a['accent']}\n")
    for i, s in enumerate(a["sections"], 1):
        print(f"  {i}. {s['title']}")
        print(f"     {s['lead'][:70]}")
    print(f"\n見出し {len(a['sections'])} 本 / 出典 {'・'.join(a['sources']) or 'なし'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
