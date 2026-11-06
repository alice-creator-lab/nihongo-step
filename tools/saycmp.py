#!/usr/bin/env python3
"""比較兩段 mp3 的發音是否一樣（純標準庫，無 numpy）。

做法：解成 16kHz 單聲道 → 每 20ms 一格 → 每格用 Goertzel 算 8 個頻帶能量
→ 取對數並正規化 → DTW 對齊兩段 → 平均距離。距離越細代表讀音越接近。

用法：
  python3 tools/saycmp.py a.mp3 b.mp3
"""
import math, struct, subprocess, sys

RATE = 16000
WIN = 320          # 20ms
BANDS = (200, 350, 550, 800, 1200, 1800, 2600, 3800)


def samples(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le",
                          "-ac", "1", "-ar", str(RATE), "-"], capture_output=True).stdout
    n = len(raw) // 4
    return struct.unpack("<%df" % n, raw[:n * 4])


def goertzel(x, freq):
    w = 2.0 * math.pi * freq / RATE
    c = 2.0 * math.cos(w)
    s1 = s2 = 0.0
    for v in x:
        s0 = v + c * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - c * s1 * s2


def frames(path):
    x = samples(path)
    out = []
    for i in range(0, len(x) - WIN, WIN // 2):
        seg = x[i:i + WIN]
        e = [math.log1p(goertzel(seg, f)) for f in BANDS]
        m = sum(e) / len(e)
        d = math.sqrt(sum((v - m) ** 2 for v in e)) or 1.0
        out.append([(v - m) / d for v in e])
    return out


def dtw(a, b):
    n, m = len(a), len(b)
    prev = [float("inf")] * (m + 1)
    prev[0] = 0.0
    for i in range(1, n + 1):
        cur = [float("inf")] * (m + 1)
        for j in range(1, m + 1):
            d = sum((a[i - 1][k] - b[j - 1][k]) ** 2 for k in range(len(BANDS)))
            cur[j] = d + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return prev[m] / (n + m)


if __name__ == "__main__":
    fa, fb = frames(sys.argv[1]), frames(sys.argv[2])
    print("frames %d / %d 距離 %.4f" % (len(fa), len(fb), dtw(fa, fb)))
