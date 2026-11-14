#!/usr/bin/env python3
"""用 Vosk 小模型核對 audio/advconj 的音檔：把辨識結果跟資料檔假名比對。

用法：python3 tools/check_advconj_asr.py [id ...]
只印出「聽落同預期有明顯差異」的行，方便人手覆核。
"""
import json
import os
import re
import subprocess
import sys
import glob
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASR = os.path.join(os.path.expanduser("~"), ".hermes/profiles/friend/cache/asr/vosk-model-small-ja-0.22")
FFMPEG = glob.glob(os.path.expanduser("~/.hermes/tools/ffmpeg-*/bin/ffmpeg"))[0]


def kana_only(s):
    s = str(s or "")
    out = []
    for ch in s:
        c = ord(ch)
        if 0x30A1 <= c <= 0x30F6:      # 片假名 → 平假名
            ch = chr(c - 0x60)
        if 0x3041 <= ord(ch) <= 0x3096 or ch in "ーっゃゅょ":
            out.append(ch)
    return "".join(out)


def main():
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    with open(os.path.join(ROOT, "data/advconj.json"), encoding="utf-8") as f:
        d = json.load(f)
    items = []
    for key in ("adverbs", "conjunctions"):
        items += d[key]["items"]
    only = set(a for a in sys.argv[1:] if not a.startswith("-"))
    model = Model(ASR)
    bad = 0
    for it in items:
        if only and it["a"] not in only:
            continue
        mp3 = os.path.join(ROOT, "audio/advconj", it["a"] + ".mp3")
        wav = "/tmp/asr-adv.wav"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", mp3,
                        "-ar", "16000", "-ac", "1", wav], check=True)
        wf = wave.open(wav, "rb")
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(False)
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)
        got = json.loads(rec.FinalResult()).get("text", "")
        wf.close()
        want = kana_only("".join(x.get("kana") or x["ja"] for x in it["ex"]))
        g = kana_only(got)
        # 逐字比對，容許插入助詞差異：只標出字數差太多或相似度低
        import difflib
        ratio = difflib.SequenceMatcher(None, want, g).ratio()
        flag = "" if ratio >= 0.72 else "  ← 覆核"
        if flag:
            bad += 1
        print(f'{it["a"]} {it["w"]:8} ratio={ratio:.2f}  ASR: {got}{flag}', flush=True)
    print("需要覆核:", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
