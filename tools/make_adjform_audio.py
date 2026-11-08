#!/usr/bin/env python3
"""生成「形容詞的變化」頁（#/all/adjs/forms）的示範音檔。

檔案對應 index.html 的 AFFORMS：
  F1 高いです／F2 有名です／F3 高くないです／F4 有名じゃありません
  F5 高かったです／F6 有名でした／F7 高くなかったです／F8 有名じゃありませんでした
  F9–F16 同一組的另一說法（高くありません、有名ではありません…）

一律用假名合成（頁面顯示的 kana），同單字表一致，避免漢字多讀音被讀錯。
生成後跑 python3 tools/trim_seq_audio.py audio/adjform 剪掉前後靜音。

用法：
  python3 tools/make_adjform_audio.py          # 只補缺檔
  python3 tools/make_adjform_audio.py --force  # 全部重生
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio/adjform")
VOICE = "ja-JP-NanamiNeural"      # 與單字／例句同一個女聲
FORMS = {
    "F1": "たかいです",
    "F2": "ゆうめいです",
    "F3": "たかくないです",
    "F4": "ゆうめいじゃありません",
    "F5": "たかかったです",
    "F6": "ゆうめいでした",
    "F7": "たかくなかったです",
    "F8": "ゆうめいじゃありませんでした",
    # 另一說法（頁面用「〃」列顯示）
    "F9": "たかくありません",
    "F10": "ゆうめいではありません",
    "F11": "ゆうめいじゃないです",
    "F12": "ゆうめいではないです",
    "F13": "たかくありませんでした",
    "F14": "ゆうめいではありませんでした",
    "F15": "ゆうめいじゃなかったです",
    "F16": "ゆうめいではなかったです",
}


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ok = fail = skip = 0
    for key, text in FORMS.items():
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
    print(f"共 {len(FORMS)} 段：生成 {ok}，略過 {skip}，失敗 {fail}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
