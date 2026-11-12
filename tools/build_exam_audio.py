#!/usr/bin/env python3
"""把測驗聽解的單句音檔拼成 2–3 句連續對話。

為甚麼要拼：單句音檔令答案往往就等於原句（聽到關鍵詞就選），
而需要上文才成立的題目（「返すのは何時までですか」→「五時までです」）
又缺了 referent。拼接只動測驗用的副本，課程會話本身不變。

輸出：audio/exam/<key>.mp3（24kHz 單聲道 48kbps，與課程音檔一致）
用法： python3 tools/build_exam_audio.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio", "exam")
GAP = 0.28  # 兩個角色之間的停頓

# key: [(課, 對話序, 行號), ...]；行號必須連續，代表一段完整問答
JOINS = {
    "S2-c2": [("L19", "d1", 0), ("L19", "d1", 1), ("L19", "d1", 2)],
    "S2-c4": [("L20", "d0", 4), ("L20", "d0", 5)],
    "S3-c1": [("L26", "d0", 1), ("L26", "d0", 2), ("L26", "d0", 3)],
    "S3-c3": [("L28", "d0", 4), ("L28", "d0", 5)],
    "S3-c4": [("L29", "d1", 2), ("L29", "d1", 3)],
}


def src(lid, dk, ln):
    p = os.path.join(ROOT, "audio", f"{lid}-{dk}-l{ln}.mp3")
    if not os.path.exists(p):
        raise SystemExit("缺音檔：" + p)
    return p


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp()
    silent = os.path.join(tmp, "gap.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", str(GAP),
                    "-c:a", "libmp3lame", "-b:a", "48k", silent], check=True)

    rows = []
    for key, parts in JOINS.items():
        listing = os.path.join(tmp, key + ".txt")
        with open(listing, "w") as f:
            for i, (lid, dk, ln) in enumerate(parts):
                if i:
                    f.write("file '%s'\n" % silent)
                f.write("file '%s'\n" % src(lid, dk, ln))
        out = os.path.join(OUT, key + ".mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", listing, "-ar", "24000", "-ac", "1",
                        "-c:a", "libmp3lame", "-b:a", "48k", out], check=True)
        total = sum(duration(src(lid, dk, ln)) for lid, dk, ln in parts) + GAP * (len(parts) - 1)
        rows.append((key, len(parts), round(total, 2), round(duration(out), 2)))
    shutil.rmtree(tmp, ignore_errors=True)

    print("已生成 %d 個測驗音檔：" % len(rows))
    for key, n, want, got in rows:
        flag = "" if abs(want - got) < 0.35 else "  ← 長度不符"
        print("  %-6s %d 句  預期 %.2fs  實際 %.2fs%s" % (key, n, want, got, flag))
    bad = [r for r in rows if abs(r[2] - r[3]) >= 0.35]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
