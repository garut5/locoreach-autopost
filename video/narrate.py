#!/usr/bin/env python3
"""
リール用のナレーション音声を作る。

    python3 video/narrate.py --day fri --out /tmp/narration.wav

原稿は video/script.py が slide_copy.json から組み立てる。
これは**画像を生成しているのと同じ原稿**なので、読み上げと画面が一致する。

スライド1枚につき1ファイルを書き出し、それぞれの秒数を manifest.json に残す。
build.py がその秒数どおりに画像を送るので、音と画がずれない。

## 音声合成のバックエンド
環境変数で切り替える。どちらも未設定なら何もせず終了する（BGMのみの動画になる）。

  VOICEVOX_URL        VOICEVOX ENGINE の URL（例 http://127.0.0.1:50021）
  VOICEVOX_SPEAKER_NAME  話者名（例 「玄野武宏」「ずんだもん」）。
                      ID は VOICEVOX のバージョンで変わりうるので、
                      名前で引いて解決する。見つからなければ VOICEVOX_SPEAKER を使う
  VOICEVOX_SPEAKER    話者ID。既定 11（玄野武宏 ノーマル）
  VOICEVOX_STYLE      スタイル名。既定「ノーマル」
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
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script  # noqa: E402

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


def resolve_speaker(base: str, name: str, style: str) -> int | None:
    """話者名とスタイル名から ID を引く。

    VOICEVOX の話者IDはバージョンによって変わる。名前の方が安定しているので、
    起動しているエンジンに問い合わせて解決する。
    """
    try:
        req = urllib.request.Request(f"{base.rstrip('/')}/speakers",
                                     headers={"User-Agent": "locoreach-reels/1.0"})
        with urllib.request.urlopen(req, timeout=30) as res:
            speakers = json.loads(res.read().decode())
    except Exception as e:
        print(f"  話者一覧を取得できませんでした（{e}）。IDの指定にフォールバックします")
        return None

    for sp in speakers:
        if sp.get("name") != name:
            continue
        styles = sp.get("styles") or []
        for st in styles:
            if st.get("name") == style:
                return int(st["id"])
        if styles:  # 指定スタイルが無ければ先頭
            print(f"  「{name}」に「{style}」が無いため「{styles[0].get('name')}」を使います")
            return int(styles[0]["id"])

    available = "、".join(sorted({sp.get("name", "") for sp in speakers})[:12])
    print(f"  話者「{name}」が見つかりません。使えるのは: {available} ...")
    return None


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


def wav_seconds(path: Path) -> float:
    """WAV の再生時間。ffprobe を使わず、ヘッダから直接読む。"""
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def synth(text: str, out: Path) -> bool:
    """1行を合成する。合成できなければ False。"""
    gkey = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
    vurl = os.environ.get("VOICEVOX_URL", "").strip()
    if gkey:
        synth_google(text, gkey, out)
        return True
    if vurl:
        name = os.environ.get("VOICEVOX_SPEAKER_NAME", "玄野武宏").strip()
        style = os.environ.get("VOICEVOX_STYLE", "ノーマル").strip()
        speaker = _SPEAKER_CACHE.get((name, style))
        if speaker is None:
            speaker = resolve_speaker(vurl, name, style) if name else None
            if speaker is None:
                speaker = int(os.environ.get("VOICEVOX_SPEAKER", "11"))
            _SPEAKER_CACHE[(name, style)] = speaker
        synth_voicevox(text, vurl, speaker, out)
        return True
    return False


_SPEAKER_CACHE: dict[tuple[str, str], int] = {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--outdir", required=True, help="スライドごとの音声を書き出す先")
    ap.add_argument("--print-only", action="store_true", help="原稿だけ出して合成しない")
    args = ap.parse_args()

    if args.day:
        key = args.day
    else:
        import datetime

        jst = datetime.timezone(datetime.timedelta(hours=9))
        key = WEEKDAYS[datetime.datetime.now(jst).weekday()]

    lines = script.lines_for(key)
    print(f"[{key}] スライド {len(lines)} 枚ぶんの原稿")
    for i, line in enumerate(lines, 1):
        print(f"  {i:2}枚目 {line}")
    if args.print_only:
        return 0

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, line in enumerate(lines, 1):
        wav = outdir / f"slide_{i:02d}.wav"
        if not synth(line, wav):
            print("⚠ GOOGLE_TTS_API_KEY / VOICEVOX_URL が未設定のためナレーションをスキップします")
            return 0
        sec = wav_seconds(wav)
        manifest.append({"index": i, "text": line, "seconds": round(sec, 3)})
        print(f"  ✓ {wav.name}  {sec:5.2f}秒")

    (outdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(m["seconds"] for m in manifest)
    print(f"\n合計 {total:.1f}秒 / {len(manifest)}枚 → {outdir}/manifest.json")
    if os.environ.get("VOICEVOX_URL", "").strip() and not os.environ.get("GOOGLE_TTS_API_KEY", "").strip():
        print("※ VOICEVOX は商用利用可だがクレジット表記が必要です")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
