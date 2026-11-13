#!/usr/bin/env python3
"""生成「助詞一覧」頁（#/all/particles）新增例句的音檔。

只有資料裡沒有現成例句（沒有 l／g／p／d 參照、直接寫 ja 的那批）才需要音檔；
其餘用法直接播放原本課堂的 mp3，不另存一份。

  data/particles.json 的 new 例句：{ja, kana, zh, a} → audio/particles/<a>.mp3
  朗讀文字走 speech(ja, kana)，助詞 は／へ／を 會寫成 わ／え／お。

生成後跑 python3 tools/trim_seq_audio.py audio/particles 剪掉前後靜音。

用法：
  python3 tools/make_particles_audio.py          # 只補缺檔
  python3 tools/make_particles_audio.py --force  # 全部重生
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from speech import speech          # noqa: E402
from make_audio import synth       # noqa: E402  同一個 edge-tts 呼叫

DATA = os.path.join(ROOT, "data/particles.json")
OUT = os.path.join(ROOT, "audio/particles")
VOICE = "ja-JP-NanamiNeural"


def rows():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    for g in d["groups"]:
        for u in g["uses"]:
            for x in u["ex"]:
                if "ja" in x and x.get("a"):
                    yield x


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ok = fail = skip = 0
    items = list(rows())
    for x in items:
        path = os.path.join(OUT, x["a"] + ".mp3")
        if os.path.exists(path) and os.path.getsize(path) > 2000 and not force:
            skip += 1
            continue
        text = speech(x["ja"], x.get("kana") or "")[0]
        if synth(VOICE, text, path):
            ok += 1
            print("ok  ", x["a"], x["ja"], "→", text, flush=True)
        else:
            fail += 1
            print("FAIL", x["a"], x["ja"], flush=True)
    print(f"共 {len(items)} 段：生成 {ok}，略過 {skip}，失敗 {fail}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
