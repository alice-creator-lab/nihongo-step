#!/usr/bin/env python3
"""生成「不同形態的應用」頁（#/all/verbs/apps）的示範音檔。

句子與音檔編號都來自 data/verbapps.json，不另外抄一份：
  rows[].a   → audio/apps/<a>.mp3
  rows[].tts → 送去 edge-tts 的假名讀法（畫面顯示的是 ex，避免漢字多讀音讀錯）

生成後跑 python3 tools/trim_seq_audio.py audio/apps 剪掉前後靜音。

用法：
  python3 tools/make_apps_audio.py          # 只補缺檔
  python3 tools/make_apps_audio.py --force  # 全部重生
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data/verbapps.json")
OUT = os.path.join(ROOT, "audio/apps")
VOICE = "ja-JP-NanamiNeural"      # 與單字／例句同一個女聲


def rows():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    for g in d["groups"]:
        for r in g["rows"]:
            if r.get("a"):
                yield r["a"], r.get("tts") or r["ex"]


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ok = fail = skip = 0
    total = 0
    for key, text in rows():
        total += 1
        path = os.path.join(OUT, key + ".mp3")
        if os.path.exists(path) and os.path.getsize(path) > 2000 and not force:
            skip += 1
            continue
        for _ in range(3):
            r = subprocess.run(["edge-tts", "--voice", VOICE, "--text", text,
                                "--write-media", path], capture_output=True, text=True, timeout=120)
            if r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 2000:
                ok += 1
                print("ok  ", key, text, flush=True)
                break
        else:
            fail += 1
            print("FAIL", key, text, flush=True)
    print(f"共 {total} 段：生成 {ok}，略過 {skip}，失敗 {fail}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
