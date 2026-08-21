#!/usr/bin/env python3
"""
SNS画像から禁止色（橙・琥珀系とネイビー系）を抜く。

    python3 tools/strip_banned_hues.py 入力ディレクトリ 出力ディレクトリ

## なぜ必要か
CLAUDE.md の「ネイビー系と橙・琥珀系を使わない」は絶対の決まりだが、
新配色として作り直した77枚にも残っていた。

- 橙・琥珀 `#3A2C1E` / `#F5D6AA` … NGバッジの行。全7ジャンルの4〜8枚目（35枚）
- ネイビー `#14243A` … 背景の暗いグロー。hpv2 と igv2 の全11枚ずつ（22枚）

## なぜ色相を回さず彩度を抜くのか
別の色へ回すと、新しい色を配色に持ち込むことになる。
アクセントが3色なのは色覚シミュレーションの全ペア検査の結果なので、
色を足せば検査をやり直さなければならない。彩度を抜くだけなら足さずに済む。
明度は保つので、文字と背景のコントラストは変わらない。

## 残すもの
カテゴリ色の青 `#1F6FEB` は theme.json にある正規の色。
明度で切り分け、暗いネイビーだけを落として明るい青は残す。
"""
from __future__ import annotations

import colorsys
import sys
from pathlib import Path

import numpy as np
from PIL import Image

AMBER = (15, 55)          # 橙・琥珀とみなす色相の範囲（度）
BLUE = (200, 250)         # 青系の範囲
NAVY_MAX_LIGHT = 0.35     # これより暗い青だけを落とす。明るい青は正規のカテゴリ色
# しきい値は実測で決めている。橙と青で分けているのは、
# 誤爆する相手が違うため。
#   橙・琥珀   #3A2C1E 彩度32% / #F5D6AA 彩度79%   → 0.20 で足りる
#   ネイビー   #14243A 彩度49%
#              一方 #1D2126（全画像で使うカードの背景・彩度13%）は
#              青寄りだが灰色。これを巻き込むと画面全体が変わるので
#              0.30 で切り分ける
AMBER_MIN_SAT = 0.20
NAVY_MIN_SAT = 0.30
MIN_LIGHT = 0.08          # 暗すぎる画素は色相の判定が不安定なので触らない
KEEP_SAT = 0.04           # 完全な灰にはせず、ごく僅かに色味を残す


def strip(src: Path, dst: Path) -> tuple[int, int]:
    """1枚を処理して、落とした画素数（橙・琥珀, ネイビー）を返す。

    画素ごとの Python ループだと1枚146万画素で現実的な時間に収まらないので、
    numpy で一括変換している。HLS への変換も自前で書いている。
    """
    im = Image.open(src).convert("RGB")
    arr = np.asarray(im, dtype=np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    mx, mn = arr.max(axis=-1), arr.min(axis=-1)
    light = (mx + mn) / 2
    span = mx - mn
    # 彩度。HLS の定義どおり、明度が 0.5 を境に分母が変わる
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(
            span == 0, 0.0,
            np.where(light < 0.5, span / (mx + mn), span / (2.0 - mx - mn)),
        )
        # 色相（度）
        rc = (mx - r) / span
        gc = (mx - g) / span
        bc = (mx - b) / span
        hue = np.where(mx == r, bc - gc, np.where(mx == g, 2.0 + rc - bc, 4.0 + gc - rc))
    hue = np.nan_to_num((hue / 6.0) % 1.0) * 360.0
    sat = np.nan_to_num(sat)

    lit = light >= MIN_LIGHT
    amber_mask = lit & (sat >= AMBER_MIN_SAT) & (hue >= AMBER[0]) & (hue <= AMBER[1])
    navy_mask = (
        lit
        & (sat >= NAVY_MIN_SAT)
        & (hue >= BLUE[0])
        & (hue <= BLUE[1])
        & (light < NAVY_MAX_LIGHT)
    )
    mask = amber_mask | navy_mask
    if mask.any():
        # 色相は残すが彩度をほぼ抜く。明度は変えないのでコントラストは保たれる
        m = light[mask]
        q = np.where(m < 0.5, m * (1 + KEEP_SAT), m + KEEP_SAT - m * KEEP_SAT)
        p_ = 2 * m - q
        h = hue[mask] / 360.0

        def channel(t):
            t = t % 1.0
            out = np.empty_like(t)
            a = t < 1 / 6
            bb = (t >= 1 / 6) & (t < 1 / 2)
            c = (t >= 1 / 2) & (t < 2 / 3)
            d = t >= 2 / 3
            out[a] = p_[a] + (q[a] - p_[a]) * 6 * t[a]
            out[bb] = q[bb]
            out[c] = p_[c] + (q[c] - p_[c]) * (2 / 3 - t[c]) * 6
            out[d] = p_[d]
            return out

        arr[..., 0][mask] = channel(h + 1 / 3)
        arr[..., 1][mask] = channel(h)
        arr[..., 2][mask] = channel(h - 1 / 3)

    out_im = Image.fromarray(np.clip(arr * 255, 0, 255).round().astype(np.uint8), "RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    out_im.save(dst, optimize=True)
    return int(amber_mask.sum()), int(navy_mask.sum())


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <入力ディレクトリ> <出力ディレクトリ>", file=sys.stderr)
        return 2
    src_dir, dst_dir = Path(sys.argv[1]), Path(sys.argv[2])
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in (".png", ".jpg"))
    if not files:
        print(f"画像がありません: {src_dir}", file=sys.stderr)
        return 1

    ta = tn = 0
    for p in files:
        # v2 → v3。immutable キャッシュなので同じ名前で上書きできない
        out = dst_dir / p.name.replace("v2_", "v3_")
        a, n = strip(p, out)
        ta += a
        tn += n
        mark = "  " if (a or n) else "・"
        print(f"{mark}{p.name:22} → {out.name:22} 橙{a:>7}px ネイビー{n:>7}px")

    print(f"\n{len(files)} 枚 / 橙・琥珀 {ta:,}px / ネイビー {tn:,}px を中立化しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
