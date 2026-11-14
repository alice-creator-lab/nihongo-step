#!/usr/bin/env python3
"""生成「副詞整合」與「連接詞整合」頁（#/all/adverbs、#/all/conjunctions）的音檔。

data/advconj.json 每筆一個 id（adv01…／cj01…）；同一筆有多行（A／B 對話）時，
逐行合成再串成一段，行與行之間留 0.28 秒。

  data/advconj.json → audio/advconj/<id>.mp3

朗讀文字走 speech(ja, kana)，助詞 は／へ／を 會寫成 わ／え／お。
生成後跑 python3 tools/trim_seq_audio.py audio/advconj 剪掉前後靜音。

用法：
  python3 tools/make_advconj_audio.py            # 只補缺檔
  python3 tools/make_advconj_audio.py --force    # 全部重生
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from speech import speech          # noqa: E402
from make_audio import synth       # noqa: E402

DATA = os.path.join(ROOT, "data/advconj.json")
OUT = os.path.join(ROOT, "audio/advconj")
VOICE = "ja-JP-NanamiNeural"
GAP = "0.28"


def ffmpeg():
    found = glob.glob(os.path.expanduser("~/.hermes/tools/ffmpeg-*/bin/ffmpeg"))
    return found[0] if found else "ffmpeg"


def rows():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    for key in ("adverbs", "conjunctions"):
        for it in d[key]["items"]:
            yield it


def make_item(it, ff, tmp):
    parts = []
    for i, ln in enumerate(it["ex"]):
        text = ln.get("tts") or speech(ln["ja"], ln.get("kana") or "")[0]
        path = os.path.join(tmp, f'{it["a"]}-{i}.mp3')
        if not synth(VOICE, text, path):
            return None, text
        parts.append(path)
    if len(parts) == 1:
        dst = os.path.join(OUT, it["a"] + ".mp3")
        shutil.copyfile(parts[0], dst)
        return dst, None
    # 多行：中間插靜音再串接
    sil = os.path.join(tmp, "sil.mp3")
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", GAP, "-q:a", "9", sil], capture_output=True)
    seq = []
    for i, p in enumerate(parts):
        seq.append(p)
        if i != len(parts) - 1:
            seq.append(sil)
    lst = os.path.join(tmp, f'{it["a"]}.txt')
    with open(lst, "w", encoding="utf-8") as f:
        for p in seq:
            f.write("file '%s'\n" % p.replace("'", "'\\''"))
    dst = os.path.join(OUT, it["a"] + ".mp3")
    r = subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c:a", "libmp3lame", "-q:a", "4", dst], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 2000:
        return None, r.stderr[-300:]
    return dst, None


def main():
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    ff = ffmpeg()
    ok = skip = fail = 0
    items = list(rows())
    for it in items:
        dst = os.path.join(OUT, it["a"] + ".mp3")
        if os.path.exists(dst) and os.path.getsize(dst) > 2000 and not force:
            skip += 1
            continue
        tmp = tempfile.mkdtemp(prefix="advaud-")
        try:
            path, err = make_item(it, ff, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if path:
            ok += 1
            print("ok  ", it["a"], it["w"], it["ex"][0]["ja"][:22], flush=True)
        else:
            fail += 1
            print("FAIL", it["a"], it["w"], err, flush=True)
    print(f"共 {len(items)} 段：生成 {ok}，略過 {skip}，失敗 {fail}", flush=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
