#!/usr/bin/env python3
"""
その日のカルーセル画像から 9:16 のリール動画を作る。

    python3 video/build.py --day fri --out /tmp/reel.mp4

content.json の image_urls（WordPress上の公開URL）をそのまま素材にする。
brand.py やフォントに依存しないので、投稿されている絵と必ず一致する。

出力: 1080x1920 / H.264 / AAC / faststart
      Instagram Reels・YouTube Shorts・TikTok がいずれも受け付ける形式。

設計メモ
  Ken Burns と クロスフェードは ffmpeg の zoompan / xfade で作る。
  フレームを1枚ずつ書き出す方式より速く、中間ファイルも作らない。
  BGM は video/gen_bgm.py で自前合成する（第三者音源を使わない）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VW, VH = 1080, 1920
FPS = 30
HOLD = 2.4          # 1枚あたりの表示秒
XFADE = 0.5         # クロスフェードの秒数
ZOOM = 1.08         # Ken Burns の最終倍率
BITRATE = "3M"
BGM_GAIN_WITH_NARRATION = 0.28   # ナレーションを載せるときのBGM音量
BG = "#14171A"      # ブランドの Primary。旧ネイビーは使わない

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def ffmpeg_bin() -> str:
    """CI では apt の ffmpeg、手元では imageio-ffmpeg を使う。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg が見つかりません。apt install ffmpeg か pip install imageio-ffmpeg を実行してください。")


def audio_duration(path: Path) -> float:
    """ffmpeg で音声ファイルの長さを秒で得る（ffprobe が無い環境でも動くようにする）。"""
    r = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True,
    )
    import re as _re

    m = None
    for m in _re.finditer(r"time=(\d+):(\d+):(\d+\.\d+)", r.stderr):
        pass
    if not m:
        return 0.0
    h, mi, sec = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(sec)


def fetch(urls: list[str], dest: Path) -> list[Path]:
    paths = []
    for i, u in enumerate(urls):
        p = dest / f"s{i:02d}.png"
        req = urllib.request.Request(u, headers={"User-Agent": "locoreach-reels/1.0"})
        with urllib.request.urlopen(req, timeout=60) as res, open(p, "wb") as f:
            f.write(res.read())
        paths.append(p)
    return paths


def filtergraph(n: int, hold: float) -> str:
    """
    各画像を 1080x1920 の背景に載せ、ゆっくり寄せながら次へ溶かす。

    xfade を数珠つなぎにするときのオフセットは (k+1)*(HOLD-XFADE)。
    全体の尺は n*HOLD - (n-1)*XFADE になる。
    """
    parts = []
    for i in range(n):
        parts.append(
            # 元は 1080x1350。上下に余白を作って 9:16 に収め、拡大しながら見せる
            f"[{i}:v]scale={VW}:-1,"
            f"pad={VW}:{VH}:(ow-iw)/2:(oh-ih)/2:color={BG},"
            f"zoompan=z='min(zoom+{(ZOOM - 1) / (hold * FPS):.6f},{ZOOM})':"
            f"d={int(hold * FPS)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={VW}x{VH}:fps={FPS},"
            f"setsar=1[v{i}]"
        )
    chain = "[v0]"
    for k in range(n - 1):
        offset = (k + 1) * (hold - XFADE)
        out = f"[x{k}]" if k < n - 2 else "[vout]"
        parts.append(f"{chain}[v{k + 1}]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{out}")
        chain = out
    if n == 1:
        parts.append("[v0]null[vout]")
    return ";".join(parts)


def build(urls: list[str], out: Path, narration: Path | None = None) -> tuple[Path, float]:
    n = len(urls)
    if n < 2:
        sys.exit("画像が2枚以上必要です。")

    hold = HOLD
    duration = n * hold - (n - 1) * XFADE

    # ナレーションが動画より長いと途中で切れるので、1枚あたりの表示時間を伸ばして合わせる。
    # 逆に短い場合は無音で埋まる（BGMは最後まで鳴る）。
    if narration is not None and narration.exists():
        nd = audio_duration(narration)
        need = nd + 1.2  # 読み終わりの余韻
        if need > duration:
            hold = (need + (n - 1) * XFADE) / n
            duration = n * hold - (n - 1) * XFADE
            print(f"  ナレーション {nd:.1f}秒に合わせて尺を {duration:.1f}秒に延長")

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        slides = fetch(urls, tmpd)

        bgm = tmpd / "bgm.wav"
        subprocess.run(
            [sys.executable, str(ROOT / "video" / "gen_bgm.py"), f"{duration:.2f}", str(bgm)],
            check=True, capture_output=True,
        )

        cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error"]
        for p in slides:
            cmd += ["-loop", "1", "-t", f"{hold:.2f}", "-i", str(p)]
        cmd += ["-i", str(bgm)]
        graph = filtergraph(n, hold)

        if narration is not None and narration.exists():
            # BGMを絞ってナレーションを前に出す。長い方に合わせる（切らない）。
            cmd += ["-i", str(narration)]
            graph += (
                f";[{n}:a]volume={BGM_GAIN_WITH_NARRATION}[bg]"
                f";[{n + 1}:a]volume=1.0,adelay=600|600[nr]"
                # amix は既定で入力数だけ音量を割るため normalize=0 で無効化する。
                # 有効のままだと全体が半分（約-6dB）になり、実測で -26dB まで落ちた。
                f";[bg][nr]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
                f"alimiter=limit=0.95,aresample=44100[aout]"
            )
            amap = "[aout]"
        else:
            amap = f"{n}:a"

        cmd += [
            "-filter_complex", graph,
            "-map", "[vout]", "-map", amap,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
            "-b:v", BITRATE, "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k",
            "-t", f"{duration:.2f}",
            "-movflags", "+faststart",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"ffmpeg に失敗しました:\n{r.stderr[-2000:]}")

    return out, duration


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="曜日キー（mon〜sun）。省略時は今日")
    ap.add_argument("--out", required=True, help="出力する mp4 のパス")
    ap.add_argument("--narration", help="ナレーション音声（省略時はBGMのみ）")
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
        print(f"{key} のコンテンツがありません。動画は作りません。")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[{key}] {item.get('genre')} / 画像 {len(item['image_urls'])}枚")
    nar = Path(args.narration) if args.narration else None
    path, dur = build(item["image_urls"], out, nar)
    size = os.path.getsize(path) / 1024 / 1024
    print(f"✓ {path}  {dur:.1f}秒  {size:.1f}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
