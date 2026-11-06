#!/usr/bin/env python3
"""重出五十音頁的發音音檔（kana/audio/n/<romaji>.mp3）。

假名表在 kana/index.html 裡，羅馬拼音由 HIRA／KATA／DAKU_HIRA／HAND_HIRA／YOUON_HIRA
等陣列決定；本工具直接讀該檔，確保「表上有幾多格，就有幾多個檔」。

用法：
    python3 tools/make_kana_audio.py                 # 只補缺檔
    python3 tools/make_kana_audio.py --force         # 全部重出
    python3 tools/make_kana_audio.py --voice ja-JP-KeitaNeural --dir kana/audio/m

授權：edge-tts 只是過渡（研發用），商業版要用有授權的引擎重出整批。
--engine azure 預留給日後改接 Azure Speech，實作時把 synth() 換成 SDK 呼叫即可。
"""
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANA_HTML = os.path.join(ROOT, "kana/index.html")
HEAD = 0.06
TAIL = 0.10


def kana_pairs():
    """由 kana/index.html 抽出 (假名, 羅馬拼音)，同一拼音只留假名（平假名優先）。"""
    src = open(KANA_HTML, encoding="utf-8").read()
    start = src.index("const HIRA = [")
    end = src.index("const ALL_PACKS")
    seg = src[start:end]
    pairs = re.findall(r"\[\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?", seg)
    # 假名頁只用每格的第一個拼音（ROMAJI[k] = o.r[0]），這裡照樣只取第一個，
    # 否則會生成表上永遠用不到的檔（例如 を 的第二讀音）。
    seen = {}
    for k, r1, *_rest in pairs:
        if not r1:
            continue
        if r1 not in seen or re.match(r"^[\u30a0-\u30ff]+$", seen[r1]):
            seen[r1] = k        # 平假名優先（片假名同音，共用同一個檔）
    return seen


def voiced_seconds(path):
    """回傳實際發聲長度（秒）：低於峰值 8% 的框架視為靜音。"""
    import array as _array
    import math as _math
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le",
                          "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    a = _array.array("h")
    a.frombytes(raw)
    hop = 80
    if not a:
        return 0.0
    env = [_math.sqrt(sum(v * v for v in a[i:i + hop]) / hop) / 32768
           for i in range(0, len(a) - hop, hop)]
    peak = max(env)
    idx = [i for i, v in enumerate(env) if v > peak * 0.08]
    return (idx[-1] - idx[0]) * 0.005 if idx else 0.0


def stretch(path, target=0.34):
    """單音節被合成得太短（例如「を」會忽略長音符）就用 atempo 拉長，音高不變。"""
    cur = voiced_seconds(path)
    if cur <= 0.01 or cur >= target * 0.9:
        return cur
    factor = max(0.35, cur / target)
    chain = []
    f = factor
    while f < 0.5:
        chain.append("atempo=0.5")
        f = f / 0.5
    chain.append("atempo=%.3f" % f)
    tmp = path + ".slow.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                        "-af", ",".join(chain),
                        "-c:a", "libmp3lame", "-q:a", "0", "-ar", "24000", "-ac", "1", tmp],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.getsize(tmp) > 1500:
        os.replace(tmp, path)
    return voiced_seconds(path)


def synth(voice, text, out, rate=None):
    for _ in range(4):
        cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", out]
        if rate:
            cmd += ["--rate", rate]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1500:
            return True
    return False


def main():
    force = "--force" in sys.argv
    voice = "ja-JP-NanamiNeural"
    outdir = "kana/audio/n"
    rate = "-20%"      # 單音節用正常語速會太短（あ 只有 0.11 秒），預設慢 20%
    suffix = "ー"      # 加長音符讓母音有正常長度；「を」會忽略，靠 stretch() 補
    for i, a in enumerate(sys.argv):
        if a == "--voice" and i + 1 < len(sys.argv):
            voice = sys.argv[i + 1]
        if a == "--rate" and i + 1 < len(sys.argv):
            rate = sys.argv[i + 1]
        if a == "--suffix" and i + 1 < len(sys.argv):
            suffix = sys.argv[i + 1]
        if a == "--dir" and i + 1 < len(sys.argv):
            outdir = sys.argv[i + 1]
    target = os.path.join(ROOT, outdir)
    os.makedirs(os.path.join(target, ".trimmed"), exist_ok=True)

    pairs = kana_pairs()
    manifest_path = os.path.join(ROOT, "kana/audio/manifest.json")
    manifest = {}
    if os.path.exists(manifest_path) and not force:
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:
            manifest = {}
    manifest.setdefault(outdir, {})
    m = manifest[outdir]

    jobs = []
    for rom, kana in sorted(pairs.items()):
        rel = "%s/%s.mp3" % (outdir, rom)
        path = os.path.join(ROOT, rel)
        m[rom] = {"kana": kana, "file": rel, "voice": voice, "rate": rate or "0%",
                  "text": kana + suffix}
        if force or not os.path.exists(path) or os.path.getsize(path) < 1500:
            jobs.append((kana, rom, path))

    print("假名 %d 個，待生成 %d" % (len(pairs), len(jobs)), flush=True)
    ok = fail = 0
    failed = []
    for n, (kana, rom, path) in enumerate(jobs, 1):
        if synth(voice, kana + suffix, path, rate):
            stretch(path)
            ok += 1
        else:
            fail += 1
            failed.append(rom)
        if n % 20 == 0 or n == len(jobs):
            print("  %d/%d" % (n, len(jobs)), flush=True)
    print("完成：成功 %d，失敗 %d" % (ok, fail), flush=True)
    if failed:
        print("失敗：", " ".join(failed), flush=True)
    json.dump(manifest, open(manifest_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("已寫 %s" % os.path.relpath(manifest_path, ROOT), flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
