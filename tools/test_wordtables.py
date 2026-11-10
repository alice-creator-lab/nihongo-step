#!/usr/bin/env python3
"""驗證「動詞表」「形容詞表」的資料：無跨課重複項、音檔齊、與動詞變化表一致。

用法： python3 tools/test_wordtables.py
（純資料檢查，不需開瀏覽器；畫面行為見 tools/test_adj_sort.py）
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT = json.load(open(os.path.join(ROOT, "data/wordtables.json"), encoding="utf-8"))


def nk(kana, kanji):
    """漢字與假名相同時視作無漢字（與 tools/build_wordtables.py 一致）。"""
    return "" if (kanji or "") == kana else (kanji or "")


fail = []

# 1) 同一分類內不得有重複項：動詞用（讀音＋漢字），形容詞用讀音
for kind, keyf in (("verbs", lambda x: (x["kana"], nk(x["kana"], x.get("kanji")))),
                   ("adjs", lambda x: x["kana"])):
    total = 0
    for g in WT[kind]["groups"]:
        seen = {}
        for x in g["items"]:
            seen.setdefault(keyf(x), []).append(x)
            total += 1
        for k, xs in seen.items():
            if len(xs) > 1:
                fail.append("%s/%s 重複 %s：%s" % (kind, g["id"], k,
                                                   ["%s-%d" % (x["id"], x["vi"]) for x in xs]))
    if total != WT[kind]["total"]:
        fail.append("%s total %d 與實際 %d 不符" % (kind, WT[kind]["total"], total))

# 2) 每個項目都要有存在的音檔
for kind in ("verbs", "adjs"):
    for g in WT[kind]["groups"]:
        for x in g["items"]:
            p = os.path.join(ROOT, x["audio"])
            if not (os.path.exists(p) and os.path.getsize(p) > 900):
                fail.append("%s 缺音檔 %s（%s %s）" % (kind, x["audio"], x["id"], x["kana"]))

# 3) 動詞表的分類數要與「動詞的變化」（data/verbforms.json）一致
VF = json.load(open(os.path.join(ROOT, "data/verbforms.json"), encoding="utf-8"))
vt = {g["id"]: len(g["items"]) for g in WT["verbs"]["groups"]}
for s in VF["sets"]:
    n = sum(len(b["rows"]) for b in s["blocks"])
    if vt.get(s["id"]) != n:
        fail.append("動詞表 %s=%s 與動詞變化表 %d 不符" % (s["id"], vt.get(s["id"]), n))

if fail:
    print("FAIL")
    for f in fail:
        print(" -", f)
    sys.exit(1)
print("PASS 動詞 %d、形容詞 %d，無重複、音檔齊、與動詞變化表一致"
      % (WT["verbs"]["total"], WT["adjs"]["total"]))
