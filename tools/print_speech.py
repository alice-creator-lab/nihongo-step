#!/usr/bin/env python3
"""句型／文法例句的「朗讀文字」一覽：確認音檔實際會讀成甚麼。

朗讀文字一律由 tools/speech.py 產生（以資料檔的 kana 為準），
這支腳本只負責印出來方便核對，不另寫一套對齊邏輯，免得兩邊結果不同。

用法：
  python3 tools/print_speech.py L08     # 印某一課的全部句子
  python3 tools/print_speech.py         # 全部課，只印對齊失敗的句子
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from speech import speech   # noqa: E402


def items(les):
    for pi, pat in enumerate(les.get("patterns", [])):
        for ei, ex in enumerate(pat.get("ex", [])):
            yield "p%d-e%d" % (pi, ei), ex
    for gi, sec in enumerate(les.get("grammar", [])):
        for ei, ex in enumerate(sec.get("ex", [])):
            yield "g%d-e%d" % (gi, ei), ex
    for di, dg in enumerate(les.get("dialogues", [])):
        for li, x in enumerate(dg.get("lines", [])):
            yield "d%d-l%d" % (di, li), x
    for li, x in enumerate(les.get("listening", [])):
        yield "l%d" % li, x


def main():
    want = [a for a in sys.argv[1:] if a.startswith("L")]
    files = ([os.path.join(ROOT, "data", "lesson-%s.json" % w) for w in want]
             if want else sorted(glob.glob(os.path.join(ROOT, "data/lesson-L*.json"))))
    n = fallback = 0
    for f in files:
        lid = os.path.basename(f)[7:10]
        les = json.load(open(f, encoding="utf-8"))
        for key, x in items(les):
            sp, ok = speech(x.get("ja", ""), x.get("kana", ""))
            n += 1
            if not ok:
                fallback += 1
            if want or not ok:
                print(f"{lid} {key} {x.get('ja','')}")
                print(f"   kana  : {x.get('kana','')}")
                print(f"   speech: {sp}{'' if ok else '   ← 對齊不完整，退回漢字原句'}")
    print(f"共 {n} 句，其中 {fallback} 句退回漢字原句", flush=True)


if __name__ == "__main__":
    main()
