#!/usr/bin/env python3
"""把 12 個單獨的數詞表合成「三個一行」的疑問詞矩陣（跟教科書版面）。

- 每個 band 3 個量詞，欄頭顯示疑問詞（何人／なんにん）＋喇叭
- items 保持扁平、按量詞次序排列，renderSeq / playGroup 的 srow-<gid>-<i> 照舊
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from make_seq_audio import synth  # noqa: E402

BANDS = [
    ("cnt1", "數詞（一）：人・枚・台",
     "人＝人數｜枚＝薄片物件｜台＝機器、車輛", ["people", "mai", "dai"]),
    ("cnt2", "數詞（二）：冊・個・本",
     "冊＝書本｜個＝小物件｜本＝細長物件", ["satsu", "ko", "hon"]),
    ("cnt3", "數詞（三）：匹・杯・歲",
     "匹＝小動物｜杯＝飲料｜歲＝年齡", ["hiki", "hai", "sai"]),
    ("cnt4", "數詞（四）：回・番・円",
     "回＝次數｜番＝編號｜円＝金額", ["kai", "ban", "en"]),
]
QWORDS = {
    "people": ("何人", "なんにん"), "mai": ("何枚", "なんまい"), "dai": ("何台", "なんだい"),
    "satsu": ("何冊", "なんさつ"), "ko": ("何個", "なんこ"), "hon": ("何本", "なんぼん"),
    "hiki": ("何匹", "なんびき"), "hai": ("何杯", "なんばい"), "sai": ("何歳", "なんさい"),
    "kai": ("何回", "なんかい"), "ban": ("何番", "なんばん"), "en": ("何円", "なんえん"),
}

path = os.path.join(ROOT, "data/sequences.json")
data = json.load(open(path, encoding="utf-8"))
by_id = {g["id"]: g for g in data["groups"]}

# 1) 疑問詞音檔（新檔名，毋須 bump auVer）
os.makedirs(os.path.join(ROOT, "audio/seq"), exist_ok=True)
for key, (kanji, kana) in QWORDS.items():
    out = os.path.join(ROOT, f"audio/seq/q-{key}.mp3")
    if not (os.path.exists(out) and os.path.getsize(out) > 1200):
        if not synth(kana, out):
            sys.exit(f"合成失敗：{kana}")
        print("合成", kanji, kana)

# 2) 組 band，重建 groups 次序
new_groups, used = [], set()
for gid, title, note, members in BANDS:
    counters, items = [], []
    for m in members:
        g = by_id[m]
        counters.append({"kanji": QWORDS[m][0], "kana": QWORDS[m][1], "n": len(g["items"]),
                         "audio": f"audio/seq/q-{m}.mp3"})
        items.extend(g["items"])
        used.add(m)
    new_groups.append({"id": gid, "title": title, "note": note, "kind": "matrix",
                       "counters": counters, "items": items})

out = []
inserted = False
for g in data["groups"]:
    if g["id"] in used:
        if not inserted:
            out.extend(new_groups)
            inserted = True
        continue
    out.append(g)
data["groups"] = out

json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("groups:", [g["id"] for g in data["groups"]])
print("items:", sum(len(g["items"]) for g in data["groups"]))
for g in data["groups"]:
    if g.get("kind") == "matrix":
        print(g["id"], g["title"], [c["kanji"] + "/" + str(c["n"]) for c in g["counters"]])
