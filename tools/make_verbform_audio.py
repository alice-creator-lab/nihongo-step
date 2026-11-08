#!/usr/bin/env python3
"""生成動詞詳細表每一行的五形音檔（辞書形沿用 audio/verb/）。

每行生成 ます形／て形／た形／ない形 四段，檔名 <src>-<形>.mp3（src 例如 L06-0），
放在 audio/verbform/。一律用假名合成，避免漢字多讀音被讀錯。
生成後跑 python3 tools/trim_seq_audio.py audio/verbform。

用法：
  python3 tools/make_verbform_audio.py            # 只補缺檔
  python3 tools/make_verbform_audio.py --force    # 全部重生
  python3 tools/make_verbform_audio.py --limit 5  # 只做前 5 行（測試用）
"""
import concurrent.futures
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio/verbform")
VOICE = "ja-JP-NanamiNeural"      # 與單字表同一個女聲


def synth(text, path):
    for _ in range(3):
        r = subprocess.run(["edge-tts", "--voice", VOICE, "--text", text,
                            "--write-media", path], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 900:
            return True
    return False


def main():
    force = "--force" in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    rows = [r for s in json.load(open(os.path.join(ROOT, "data/verbforms.json"), encoding="utf-8"))["sets"]
            for b in s["blocks"] for r in b["rows"]]
    if limit:
        rows = rows[:limit]
    os.makedirs(OUT, exist_ok=True)

    jobs = []
    for r in rows:
        for name in ("masu", "te", "ta", "nai"):
            path = os.path.join(OUT, "%s-%s.mp3" % (r["src"], name))
            if force or not (os.path.exists(path) and os.path.getsize(path) > 900):
                jobs.append((r[name], path))

    print("待生成 %d 段（共 %d 行）" % (len(jobs), len(rows)), flush=True)
    ok = fail = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for good in ex.map(lambda j: synth(*j), jobs):
            if good:
                ok += 1
            else:
                fail += 1
            if (ok + fail) % 100 == 0:
                print("  %d/%d" % (ok + fail, len(jobs)), flush=True)
    print("完成：成功 %d，失敗 %d" % (ok, fail), flush=True)
    if ok:
        print("記得剪靜音：python3 tools/trim_seq_audio.py audio/verbform", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
