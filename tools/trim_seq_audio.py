#!/usr/bin/env python3
"""剪掉 audio/seq/*.mp3 前後的靜音，令「播放全部」緊湊一點（洗腦式跟讀）。

edge-tts 出來的檔案每段前後各有約 0.2 秒／1.1 秒空白，逐段播放時會拖得很慢。
本工具找出真正發聲的區間，保留少量前後留白後重新編碼。只用標準庫。

用法：
  python3 tools/trim_seq_audio.py            # 只處理未修剪的檔案
  python3 tools/trim_seq_audio.py --force    # 全部重剪（重剪前先用 make_seq_audio.py --force 重生）
"""
import glob, math, os, struct, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEQ = os.path.join(ROOT, "audio/seq")
MARKS = os.path.join(SEQ, ".trimmed")
HEAD = 0.08     # 發聲起點前保留
TAIL = 0.22     # 發聲結束後保留（留一點尾巴，太短會像被切斷）
QSCALE = "4"    # libmp3lame VBR 品質：4＝預設，0＝最高
COPY = False    # True＝不重新編碼，只複製音框（-c copy）；五十音用，確保輸出同 edge-tts 原檔格式
MIN_GAP = 0.02  # 少於這個長度就當已在範圍內
RATE = 16000
WIN = 160       # 10ms


def samples(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le",
                          "-ac", "1", "-ar", str(RATE), "-"], capture_output=True).stdout
    n = len(raw) // 4
    return struct.unpack("<%df" % n, raw[:n * 4])


def speech_bounds(path):
    x = samples(path)
    if not x:
        return None
    frames = len(x) // WIN
    if not frames:
        return None
    energy = []
    for i in range(frames):
        s = 0.0
        base = i * WIN
        for k in range(base, base + WIN):
            s += x[k] * x[k]
        energy.append(math.sqrt(s / WIN))
    peak = max(energy)
    thr = max(peak * 0.02, 0.003)
    first = next((i for i, e in enumerate(energy) if e > thr), None)
    if first is None:
        return None
    last = next(i for i in range(frames - 1, -1, -1) if energy[i] > thr)
    return first * WIN / RATE, (last + 1) * WIN / RATE, len(x) / RATE


def trim(path, force=False, marks=None):
    mark = os.path.join(marks or MARKS, os.path.basename(path))
    if os.path.exists(mark) and not force:
        return "skip"
    b = speech_bounds(path)
    if not b:
        return "fail"
    start, end, total = b
    s = max(0.0, start - HEAD)
    e = min(total, end + TAIL)
    if total - (e - s) < MIN_GAP:
        open(mark, "w").close()
        return "skip"
    tmp = path + ".tmp.mp3"
    if COPY:
        # 無損剪接：直接複製音框，不重新編碼（輸出格式與 edge-tts 原檔完全相同，48kbps CBR）
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", path,
               "-ss", "%.3f" % s, "-to", "%.3f" % e, "-c", "copy", tmp]
    else:
        # 結尾加 30ms 淡出：直接切在母音上會有「啪」一聲，聽起來就是機械聲
        dur = max(0.05, e - s)
        fade = "afade=t=in:st=0:d=0.005,afade=t=out:st=%.3f:d=0.030" % max(0.0, dur - 0.030)
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", path,
               "-ss", "%.3f" % s, "-to", "%.3f" % e, "-af", fade,
               "-c:a", "libmp3lame", "-q:a", QSCALE, "-ar", "24000", "-ac", "1", tmp]
    r = subprocess.run(cmd,
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
        if os.path.exists(tmp):
            os.remove(tmp)
        print("ffmpeg 失敗:", os.path.basename(path), r.stderr.strip()[:200], flush=True)
        return "fail"
    os.replace(tmp, path)
    open(mark, "w").close()
    return "%.2f→%.2f" % (total, e - s)


def main():
    global HEAD, TAIL, QSCALE, COPY
    # 位置參數只收「不是選項、也不是選項數值」的項目（--head 0.08 的 0.08 不是目錄）
    args, skip_next = [], False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a in ("--head", "--tail", "--q"):
            skip_next = True
            continue
        if a.startswith("--"):
            continue
        args.append(a)
    force = "--force" in sys.argv
    COPY = "--copy" in sys.argv
    # 可調整前後留白：五十音只有一個音節，尾巴留長一點才不會聽起來被切斷
    for i, a in enumerate(sys.argv):
        if a == "--head" and i + 1 < len(sys.argv):
            HEAD = float(sys.argv[i + 1])
        if a == "--tail" and i + 1 < len(sys.argv):
            TAIL = float(sys.argv[i + 1])
        if a == "--q" and i + 1 < len(sys.argv):   # 0＝最高品質（VBR），4＝預設
            QSCALE = sys.argv[i + 1]
    # 可指定其他目錄（例如 audio/verb）；預設 audio/seq
    target = os.path.join(ROOT, args[0]) if args else SEQ
    marks = os.path.join(target, ".trimmed")
    os.makedirs(marks, exist_ok=True)
    files = sorted(glob.glob(os.path.join(target, "*.mp3")))
    ok = skip = fail = 0
    for f in files:
        res = trim(f, force, marks)
        if res == "skip":
            skip += 1
        elif res == "fail":
            fail += 1
        else:
            ok += 1
    print(f"共 {len(files)} 段：修剪 {ok}，略過 {skip}，失敗 {fail}", flush=True)


if __name__ == "__main__":
    main()
