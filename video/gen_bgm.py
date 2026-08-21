#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自前合成の環境音BGMを WAV で出力する。
第三者の音源を使わないため著作権リスクが無い。
locoreach-daily-autopost スキルの gen_bgm.py をそのまま持ち込んだもの
（出力先の既定値だけサンドボックス絶対パスから相対に変更）。"""
import numpy as np, wave, sys

SR = 44100

def note(freq, dur, sr=SR):
    t = np.linspace(0, dur, int(sr*dur), endpoint=False)
    # warm pad: fundamental + soft harmonics
    w = (np.sin(2*np.pi*freq*t)
         + 0.5*np.sin(2*np.pi*2*freq*t)
         + 0.25*np.sin(2*np.pi*3*freq*t)
         + 0.12*np.sin(2*np.pi*4*freq*t))
    # gentle vibrato
    w *= 1 + 0.004*np.sin(2*np.pi*5*t)
    return w

def env(n, a=0.18, r=0.35, sr=SR):
    e = np.ones(n)
    ai = int(a*sr); ri = int(r*sr)
    if ai>0: e[:ai] = np.linspace(0,1,ai)
    if ri>0: e[-ri:] = np.linspace(1,0,ri)
    return e

def chord(freqs, dur):
    n = int(SR*dur)
    out = np.zeros(n)
    for f in freqs:
        w = note(f, dur)[:n]
        out += w
    out /= max(1, len(freqs))
    out *= env(n)
    return out

# note freqs
F = {"C3":130.81,"E3":164.81,"G3":196.00,"A3":220.00,"D3":146.83,"F3":174.61,
     "C4":261.63,"E4":329.63,"G4":392.00,"A4":440.00,"D4":293.66,"F4":349.23}

def build(duration):
    # slow progression Am - F - C - G, 2.6s each
    prog = [["A3","C4","E4"], ["F3","A3","C4"], ["C3","E3","G3"], ["G3","D4","F4" if False else "B3" if False else "D4"]]
    prog = [["A3","C4","E4"], ["F3","A3","C4"], ["C3","E3","G3"], ["G3","G3","D4"]]
    seg = 2.6
    track = np.zeros(0)
    while len(track)/SR < duration:
        for ch in prog:
            fr = [F.get(x, 220.0) for x in ch]
            track = np.concatenate([track, chord(fr, seg)])
            if len(track)/SR >= duration: break
    track = track[:int(SR*duration)]
    # soft sub pulse (very quiet) on beat
    t = np.linspace(0, duration, len(track), endpoint=False)
    sub = 0.06*np.sin(2*np.pi*55*t) * (0.5+0.5*np.sin(2*np.pi*(1/1.3)*t))
    mix = 0.9*track + sub
    # normalize gentle
    mix = mix/np.max(np.abs(mix)+1e-9) * 0.5
    # soft fade in/out overall
    fi = int(SR*1.2); fo=int(SR*1.5)
    mix[:fi]*=np.linspace(0,1,fi); mix[-fo:]*=np.linspace(1,0,fo)
    return (mix*32767).astype(np.int16)

if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv)>1 else 22.0
    out = sys.argv[2] if len(sys.argv)>2 else "bgm.wav"
    data = build(dur)
    with wave.open(out,"w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())
    print("wrote", out, dur, "s")
