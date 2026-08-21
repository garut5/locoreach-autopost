#!/usr/bin/env python3
"""
スライド1枚ごとの読み上げ原稿を組み立てる。

    python3 video/script.py --day mon

## なぜキャプションから作らないのか
以前はキャプションから1本の連続した原稿を作り、画像は1枚2.4秒の固定で
送っていた。両者に対応関係がないので必ずずれる。しかもキャプションの
5項目と実際のスライドは別物だった（キャプションは「基本情報を100%埋める」
から始まるが、2枚目は「この投稿でわかること」の目次）。

video/slide_copy.json は**画像を生成しているのと同じ原稿**なので、
ここから作れば内容が一致する。10枚の構成は生成側と揃えてある。

  1 表紙        title / subtitle / badge
  2 目次        index 5件
  3 なぜ効くか   why_title / why_body / why_points
  4-8 コツ5つ   tips[i]: t / checks 2件 / ng / data
  9 まとめ      tips のタイトル5件
  10 CTA        cta_title

読み上げでは checks の2件までにしている。ng と data まで読むと
1枚あたり15秒を超え、10枚で3分に届いてショートの尺から外れるため。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY = ROOT / "video" / "slide_copy.json"
ORDINAL = ["ひとつめ", "ふたつめ", "みっつめ", "よっつめ", "いつつめ"]

# 読み上げに向かない記号を落とす
_DROP = re.compile(r'[“”"「」『』（）()【】\[\]]')

# 読み方だけを置き換える表。**画面に出る文字は変えない**。
# 略語は画面では短いほうが読みやすいが、音では正しく言ってほしい。
# HP は「エイチピー」ではなく「ホームページ」と読む。
# Q&A は下の & → と の置換で「QとA」になってしまうため、ここで先に潰す。
READING = {
    "Q&A": "キューアンドエー",
    "HP": "ホームページ",
}
_READ = re.compile("|".join(re.escape(k) for k in sorted(READING, key=len, reverse=True)))


def clean(text: str) -> str:
    text = _DROP.sub("", text)
    text = _READ.sub(lambda m: READING[m.group(0)], text)
    text = text.replace("＋", "と").replace("&", "と").replace("／", "、")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def lines_for(day: str) -> list[str]:
    """10枚ぶんの原稿を返す。スライドの並びと1対1で対応する。"""
    cfg = json.loads(COPY.read_text(encoding="utf-8"))[day]
    tips = cfg["tips"]
    out: list[str] = []

    # 1 表紙
    out.append(clean(f'{"".join(cfg["title"])}。{cfg["subtitle"]}。{cfg["badge"]}お伝えします。'))

    # 2 目次
    out.append(clean(f'この投稿でわかることは、{cfg["index"][0]}から、{cfg["index"][-1]}まで。順に見ていきます。'))

    # 3 なぜ効くか
    out.append(clean(f'{cfg["why_title"]}。{"".join(cfg["why_body"])}'))

    # 4〜8 コツ
    for i, tip in enumerate(tips):
        checks = "。".join(tip["checks"])
        out.append(clean(f'{ORDINAL[i]}、{tip["t"]}。{checks}。'))

    # 9 まとめ
    titles = "、".join(t["t"] for t in tips)
    out.append(clean(f"今日のまとめです。{titles}。この5つです。"))

    # 10 CTA
    out.append(clean(f'{"".join(cfg["cta_title"])}。後で見返せるように保存してください。'))

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--json", action="store_true", help="JSON で出す")
    args = ap.parse_args()

    lines = lines_for(args.day)
    if args.json:
        print(json.dumps(lines, ensure_ascii=False, indent=2))
        return 0

    for i, line in enumerate(lines, 1):
        # 日本語はおおよそ 6.5 文字/秒（VOICEVOX の speedScale 1.15 で実測）
        print(f"{i:2}枚目 ({len(line):3}字 / 約{len(line)/6.5:4.1f}秒)  {line}")
    total = sum(len(l) for l in lines) / 6.5
    print(f"\n合計 約{total:.0f}秒（{len(lines)}枚）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
