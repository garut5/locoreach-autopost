#!/usr/bin/env python3
"""
ショート（20〜30秒）の構成を組み立てる。

    python3 video/short.py --day fri

## カルーセルと何を変えたか
カルーセルは「5つのコツ」を網羅して保存してもらうもの。
ショートは**そのうち1つだけ**を、結論から言う。

  1 フック   いきなり結論。表紙も目次も置かない
  2 問題     やりがちな失敗（tips[i].ng）
  3 対策     コツ本体と確認事項（t / checks）
  4 裏づけ   なぜそうなのか（data）
  5 CTA      保存と、プロフィールからの無料診断

どのコツを取り上げるかと、フックの文言は slide_copy.json の
`short` に日ごとに持たせている。機械的に選ぶと、
一番刺さるコツが選ばれる保証がないため。

読み上げ原稿は**カードに書いてある文字と同じもの**から作る。
以前ずれた原因がここだったので、二度と別々のデータから作らない。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY = ROOT / "video" / "slide_copy.json"

GENRE_LABEL = {
    "meo": "MEO対策",
    "ig": "Instagram集客",
    "ai": "店舗×AI",
    "aio": "AIO・AI検索",
    "hp": "ホームページ集客",
    "review": "口コミ対策",
    "keiei": "店舗経営",
}

_DROP = re.compile(r'[“”"「」『』【】\[\]]')


def wrap(text: str, width: int = 12, limit: int = 3) -> list[str]:
    """日本語を折る。

    単純に width 字ごとに切ると「行動に繋／がりやすい」のように
    語の途中で割れる。行数を先に決めて**均等に**割り、
    その境目の前後2字に読点があればそこを優先する。
    """
    text = _DROP.sub("", text).replace("／", "・")
    n = min(limit, max(1, -(-len(text) // width)))
    if n == 1:
        return [text]

    # 句点があるならまずそこで切る。「Googleビジネスプロ／フィールの…」のような
    # 割れ方は、文の途中で折ろうとするから起きる
    if "。" in text[:-1]:
        head, _, tail = text.partition("。")
        head += "。"
        room = limit - max(1, -(-len(head) // width))
        if room >= 1:
            return wrap(head, width, limit - room) + wrap(tail, width, room)

    lines, start = [], 0
    for i in range(n - 1):
        ideal = start + round((len(text) - start) / (n - i))
        # 探す幅は広めに取る。狭いと「Googleビジネスプロ／フィール」のように
        # 語の切れ目が窓の外に落ちて、悪い位置で折るしかなくなる
        cut = max(
            (j for j in range(max(start + 1, ideal - 5), min(len(text), ideal + 6))),
            key=lambda j: (_break_score(text, j), -abs(j - ideal)),
            default=ideal,
        )
        lines.append(text[start:cut])
        start = cut
    lines.append(text[start:])
    return [l for l in lines if l]


def _cls(ch: str) -> str:
    """文字の種類。同じ種類が続いているところは語の途中である可能性が高い。"""
    o = ord(ch)
    if ch in "、。・":
        return "punct"
    if 0x3041 <= o <= 0x309F:
        return "hira"
    if 0x30A0 <= o <= 0x30FF:
        return "kata"
    if 0x4E00 <= o <= 0x9FFF:
        return "kanji"
    return "other"


def _break_score(text: str, j: int) -> int:
    """j の直前で改行してよさそうかを点数にする。

    「情／報」「取り／こぼし」のように語の途中で割れるのを避けたい。
    形態素解析を持ち込まずに済ませるため、文字種の変わり目を手がかりにする。
    """
    a, b = _cls(text[j - 1]), _cls(text[j])
    if a == "punct":
        return 4
    if a == b:                       # 同種が続く＝語の途中の可能性が高い
        return -3
    if a in ("kanji", "kata") and b == "hira":
        return 2                     # 送り仮名・助詞の手前。切ってよい
    if a == "hira" and b in ("kanji", "kata"):
        # 「打ち｜手」のように、送り仮名1字を挟んだ複合語の途中でもこの形になる。
        # 直前が漢字なら語の途中とみなして下げる
        if j >= 2 and _cls(text[j - 2]) == "kanji":
            return 1
        return 3                     # 次の語の頭。いちばん切りやすい
    return 0


def _cfg(day: str) -> tuple[dict, dict, dict]:
    data = json.loads(COPY.read_text(encoding="utf-8"))
    cfg = data[day]
    sh = cfg.get("short")
    if not sh:
        raise SystemExit(f"{day} に short の設定がありません。slide_copy.json を確認してください。")
    return cfg, sh, cfg["tips"][sh["tip"]]


def plan_for(day: str) -> list[dict]:
    """カード5枚の内容。cards.py がこれを描く。"""
    cfg, sh, tip = _cfg(day)
    label = GENRE_LABEL.get(cfg["genre"], cfg["genre"])
    return [
        {"kicker": label, "headline": sh["hook"], "big": True},
        {"kicker": "やりがちなのは", "headline": wrap(tip["ng"])},
        {"kicker": "こうする", "headline": wrap(tip["t"]), "body": [_DROP.sub("", c) for c in tip["checks"]]},
        {"kicker": "なぜそうなるか", "headline": wrap(tip["data"])},
        # CTA は**取り上げたコツ**に合わせる。cfg["cta_title"] は
        # カルーセル全体（5つ）の締めなので、1つに絞ったショートでは噛み合わない。
        {"kicker": "今日はここから",
         "headline": wrap(tip["t"]),
         "body": ["保存して見返してください", "プロフィールのリンクから無料診断"]},
    ]


def narration_for(day: str) -> list[str]:
    """カード5枚それぞれの読み上げ。カードの文字と同じ素材から作る。"""
    cfg, sh, tip = _cfg(day)

    def clean(t: str) -> str:
        t = _DROP.sub("", t).replace("＋", "と").replace("／", "、")
        t = t.replace("Q&A", "キューアンドエー").replace("HP", "ホームページ")
        return re.sub(r"\s+", " ", t).strip()

    checks = "。".join(tip["checks"])
    return [
        clean("".join(sh["hook"])),
        clean(f'やりがちなのは、{tip["ng"]}。'),
        clean(f'{tip["t"]}。{checks}。'),
        clean(f'{tip["data"]}。'),
        clean(f'今日はここからです。{tip["t"]}。保存して見返してください。'),
    ]


def caption(day: str) -> str:
    """ショート用の本文。

    カルーセルのキャプションは5つのコツを列挙するので、
    1つに絞った動画に付けると中身と食い違う。動画で言っていることだけを書く。
    ハッシュタグは content.json のものをそのまま使う（選定済みのため）。
    """
    cfg, sh, tip = _cfg(day)
    tags = ""
    try:
        content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
        for line in reversed((content.get(day, {}).get("caption") or "").splitlines()):
            if line.strip().startswith("#"):
                tags = line.strip()
                break
    except Exception:
        pass

    blocks = [
        "".join(sh["hook"]),
        f'やりがちなのは、{tip["ng"]}。',
        "▼こうする\n" + tip["t"] + "\n" + "\n".join(f"・{c}" for c in tip["checks"]),
        f'{tip["data"]}。',
        "無料のMEO診断はプロフィールのリンクから。\n"
        "店舗の集客・経営のヒントは @locoreach_ai から毎日発信中！",
    ]
    if tags:
        blocks.append(tags)
    return "\n\n".join(blocks)


# ── 記事から作る ────────────────────────────────────────────
# slide_copy.json は7ジャンル固定なので、毎週同じ7本になる。
# 記事は毎朝1本ずつ増えるので、そこから作れば動画も毎日変わる。

ARTICLE_STEPS = ["まず", "つぎに", "そして"]


def _hook(a: dict) -> str:
    """冒頭の1文。ここで見るかどうかが決まるので、短く言い切れるものを選ぶ。"""
    return (_sentence(a.get("description", ""), 34)
            or _sentence(a.get("title", ""), 34)
            or (a.get("title", "") or "")[:34])


def _sentence(text: str, limit: int = 46) -> str:
    """最初の1文。長すぎるときは**空を返す**。

    途中で切ると「…投稿画面まで」のように文が途切れたまま読み上げてしまう。
    入らないなら見出しだけにしたほうが、聞いても読んでも成立する。
    """
    text = (text or "").strip()
    for sep in ("。", "！", "？"):
        head = text.split(sep)[0]
        if head != text and len(head) <= limit:
            return head
    return text if len(text) <= limit else ""


def plan_for_article(a: dict) -> list[dict]:
    """記事1本から、ショート5枚ぶんのカードを組み立てる。"""
    secs = (a.get("sections") or [])[:3]
    if not secs:
        raise SystemExit("記事から見出しを取れませんでした。")
    chip = a.get("chip") or "店舗集客"
    hook = _hook(a)

    cards = [{"kicker": chip, "headline": wrap(hook, width=12, limit=3), "big": True}]
    for i, sec in enumerate(secs):
        lead = _sentence(sec.get("lead", ""), 46)
        body = wrap(lead, width=20, limit=2) if lead else []
        cards.append({"kicker": ARTICLE_STEPS[i], "headline": wrap(sec["title"], width=12, limit=3),
                      "body": body})
    cards.append({"kicker": "続きは記事で",
                  "headline": ["保存して", "あとで読む"],
                  "body": ["プロフィールのリンクから記事へ", "無料のMEO診断もそこから"]})
    return cards


def narration_for_article(a: dict) -> list[str]:
    """カードに書いてある文字と同じ素材から読み上げを作る。"""
    secs = (a.get("sections") or [])[:3]
    hook = _hook(a)

    def clean(t: str) -> str:
        t = _DROP.sub("", t).replace("＋", "と").replace("／", "、")
        t = t.replace("Q&A", "キューアンドエー").replace("HP", "ホームページ")
        return re.sub(r"\s+", " ", t).strip()

    lines = [clean(hook + "。")]
    for i, sec in enumerate(secs):
        lead = _sentence(sec.get("lead", ""), 46)
        lines.append(clean(f'{ARTICLE_STEPS[i]}、{sec["title"]}。{lead}。' if lead
                           else f'{ARTICLE_STEPS[i]}、{sec["title"]}。'))
    lines.append(clean("続きは記事にまとめています。プロフィールのリンクからどうぞ。"))
    return lines


def caption_for_article(a: dict) -> str:
    """ショートに付ける本文。動画で触れた見出しだけを書く。"""
    secs = (a.get("sections") or [])[:3]
    blocks = [
        a["title"],
        _sentence(a.get("description") or "", 60) + "。",
        "▼この動画でわかること\n" + "\n".join(f"{i:02d} {s['title']}" for i, s in enumerate(secs, 1)),
        "続きは記事にまとめています。プロフィールのリンクからどうぞ。\n"
        "無料のMEO診断もそこから受け取れます。",
        "店舗の集客・経営のヒントは @locoreach_ai から毎日発信中！",
    ]
    return "\n\n".join(blocks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--source", choices=["fixed", "article"], default="fixed")
    ap.add_argument("--slug", default="")
    args = ap.parse_args()

    if args.source == "article":
        import sys as _sys

        _sys.path.insert(0, str(ROOT / "scripts"))
        import article as _article

        a = _article.load(args.slug)
        plan, lines = plan_for_article(a), narration_for_article(a)
        print(f"{a['title']}\n{a['link']}\n")
    else:
        if not args.day:
            raise SystemExit("--day が要ります（--source fixed のとき）")
        plan, lines = plan_for(args.day), narration_for(args.day)
    total = 0.0
    for i, (card, line) in enumerate(zip(plan, lines), 1):
        sec = len(line) / 6.5      # VOICEVOX speedScale 1.15 での実測に近い値
        total += sec
        print(f"{i}. [{card['kicker']}] {' / '.join(card['headline'])}")
        for b in card.get("body", []):
            print(f"     - {b}")
        print(f"     読み: {line}  （{len(line)}字 / 約{sec:.1f}秒）")
    print(f"\n読み上げ合計 約{total:.0f}秒（カード{len(plan)}枚。実尺は余白を足して +6秒ほど）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
