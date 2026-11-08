#!/usr/bin/env python3
"""生成「動詞詳細表」的示範音檔（第一版只做兩行）。

  L06-0 行く（五段，て形例外：いって）
  L07-0 食べる（一段）

每行生成 ます形／て形／た形／ない形 四段，檔名 <課>-<單字索引>-<形>.mp3，
放在 audio/verbform/。辞書形沿用 audio/verb/ 的現成人聲。
生成後跑 python3 tools/trim_seq_audio.py audio/verbform。

用法：
  python3 tools/make_verbform_audio.py          # 只補缺檔
  python3 tools/make_verbform_audio.py --force  # 全部重生
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_verbforms import forms  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio/verbform")
VOICE = "ja-JP-NanamiNeural"      # 與單字表同一個女聲
EXAMPLES = [
    ("L06", 0, "いく", "godan", "いきます"),
    ("L07", 0, "たべる", "ichidan", "たべます"),
]


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ok = fail = skip = 0
    for lesson, vi, jisho, group, masu in EXAMPLES:
        f = forms(jisho, group, masu)
        for name in ("masu", "te", "ta", "nai"):
            path = os.path.join(OUT, "%s-%d-%s.mp3" % (lesson, vi, name))
            if os.path.exists(path) and os.path.getsize(path) > 2000 and not force:
                skip += 1
                continue
            for _ in range(3):
                r = subprocess.run(["edge-tts", "--voice", VOICE, "--text", f[name],
                                    "--write-media", path], capture_output=True, text=True, timeout=120)
                if r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 2000:
                    ok += 1
                    print("ok  ", os.path.basename(path), f[name], flush=True)
                    break
            else:
                fail += 1
                print("FAIL", os.path.basename(path), f[name], flush=True)
    print(f"共 {len(EXAMPLES) * 4} 段：生成 {ok}，略過 {skip}，失敗 {fail}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
