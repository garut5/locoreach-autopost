#!/usr/bin/env python3
"""
リール用のナレーション音声を作る。

    python3 video/narrate.py --day fri --out /tmp/narration.wav

原稿は content.json の caption から機械的に組み立てる。
別に原稿を書き起こす運用にすると、投稿本文と内容がずれるため。

## 音声合成のバックエンド
環境変数で切り替える。どちらも未設定なら何もせず終了する（BGMのみの動画になる）。

  VOICEVOX_URL        VOICEVOX ENGINE の URL（例 http://127.0.0.1:50021）
                      無料。日本語専用。商用利用可だが**クレジット表記が必要**。
  GOOGLE_TTS_API_KEY  Google Cloud Text-to-Speech の APIキー
                      1本あたり0.01円未満。クレジット表記は不要。

両方あれば Google を優先する（クレジット表記の義務が無いため）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# 読み上げに向かない文字を落とす
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️✨‼⁉]+"
)


def narration_text(caption: str, limit: int) -> str:
    """
    caption から読み上げ原稿を組み立てる。

    caption の構造:
        1行目  見出し（「〜5つ」のように件数を含むことがある）
        2行目  リード文
        ▼この投稿でわかること
        01 …  〜  05 …
        締めの文・ハッシュタグ

    見出しが件数を名乗るので、**ポイントは削らない**。
    尺に収まらないときはリード文から落とす。
    """
    lines = [l.strip() for l in caption.splitlines() if l.strip()]
    lines = [_EMOJI.sub("", l).strip() for l in lines]

    head = lines[0] if lines else ""
    lead = ""
    tips: list[str] = []
    for l in lines[1:]:
        if l.startswith("▼") or l.startswith("#") or l.startswith("@"):
            continue
        m = re.match(r"^(\d{1,2})[\.\s\u3000]+(.+)$", l)
        if m:
            tips.append(m.group(2).strip())
        elif not tips and not lead and "発信中" not in l:
            lead = l

    def assemble(with_lead: bool, n_tips: int) -> str:
        parts = [head]
        if with_lead and lead:
            parts.append(lead)
        if n_tips:
            parts.append(f"ポイントは{n_tips}つです")
            parts.extend(tips[:n_tips])
        parts.append("詳しくはプロフィールから")
        text = "。".join(p.rstrip("。") for p in parts if p) + "。"
        return re.sub(r"。+", "。", text)

    # 優先順位: 全ポイントを残す > リード文を残す
    for with_lead, n in ((True, len(tips)), (False, len(tips))):
        t = assemble(with_lead, n)
        if len(t) <= limit:
            return t
    # それでも入らなければ最後の手段としてポイントを後ろから削る
    n = len(tips)
    while n > 1:
        n -= 1
        t = assemble(False, n)
        if len(t) <= limit:
            return t
    return assemble(False, 1)[:limit]


def synth_voicevox(text: str, base: str, speaker: int, out: Path) -> None:
    q = urllib.request.Request(
        f"{base.rstrip('/')}/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": speaker}),
        method="POST",
    )
    with urllib.request.urlopen(q, timeout=120) as res:
        query = json.loads(res.read().decode())
    # 少し速めに読ませて尺に収める
    query["speedScale"] = float(os.environ.get("VOICEVOX_SPEED", "1.15"))

    s = urllib.request.Request(
        f"{base.rstrip('/')}/synthesis?" + urllib.parse.urlencode({"speaker": speaker}),
        data=json.dumps(query).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(s, timeout=300) as res:
        out.write_bytes(res.read())


def synth_google(text: str, key: str, out: Path) -> None:
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "ja-JP", "name": os.environ.get("GOOGLE_TTS_VOICE", "ja-JP-Neural2-B")},
        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000, "speakingRate": 1.1},
    }
    req = urllib.request.Request(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={urllib.parse.quote(key)}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        payload = json.loads(res.read().decode())
    out.write_bytes(base64.b64decode(payload["audioContent"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=150, help="読み上げ原稿の最大文字数")
    ap.add_argument("--print-only", action="store_true", help="原稿だけ出力して合成しない")
    args = ap.parse_args()

    content = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    if args.day:
        key = args.day
    else:
        import datetime

        jst = datetime.timezone(datetime.timedelta(hours=9))
        key = WEEKDAYS[datetime.datetime.now(jst).weekday()]

    item = content.get(key)
    if not item:
        print(f"{key} のコンテンツがありません。")
        return 0

    text = narration_text(item["caption"], args.limit)
    print(f"[{key}] 原稿 {len(text)}文字:\n  {text}")
    if args.print_only:
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    gkey = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
    vurl = os.environ.get("VOICEVOX_URL", "").strip()

    if gkey:
        synth_google(text, gkey, out)
        print(f"✓ Google Cloud TTS で合成 → {out}")
    elif vurl:
        speaker = int(os.environ.get("VOICEVOX_SPEAKER", "3"))
        synth_voicevox(text, vurl, speaker, out)
        print(f"✓ VOICEVOX（speaker={speaker}）で合成 → {out}")
        print("  ※ VOICEVOX は商用利用可だがクレジット表記が必要です")
    else:
        print("⚠ GOOGLE_TTS_API_KEY / VOICEVOX_URL が未設定のためナレーションをスキップします")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
