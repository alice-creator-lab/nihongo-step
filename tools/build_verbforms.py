#!/usr/bin/env python3
"""由 data/wordtables.json 生成「動詞詳細表」資料（data/verbforms.json）。

- 只取唯一動詞（同一組、同一假名的重複課次合併，課號全部保留）。
- 欄位次序：辞書形 → ます形 → て形 → た形 → ない形。
- 五段按語尾分わ・か・さ・た・な・ば・ま・ら行；が行併入か行（跟課本）。
- 一段按「〜える／〜いる」分組；不規則分「する系／来る」。
- て形／た形／ない形由辞書形＋類型用規則生成，例外寫死在 SPECIAL。

用法：python3 tools/build_verbforms.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT = os.path.join(ROOT, "data/wordtables.json")
OUT = os.path.join(ROOT, "data/verbforms.json")
AUDIO_DIR = os.path.join(ROOT, "audio/verbform")

ROW_OF = {"う": "わ行", "く": "か行", "ぐ": "か行", "す": "さ行", "つ": "た行",
          "ぬ": "な行", "ぶ": "ば行", "む": "ま行", "る": "ら行"}
TE_OF = {"う": "って", "つ": "って", "る": "って", "む": "んで", "ぶ": "んで",
         "ぬ": "んで", "く": "いて", "ぐ": "いで", "す": "して"}
NAI_OF = {"う": "わ", "く": "か", "ぐ": "が", "す": "さ", "つ": "た", "ぬ": "な",
          "ぶ": "ば", "む": "ま", "る": "ら"}
E_ROW = "えけげせぜてでねへべぺめれ"
KANA = re.compile(r"^[ぁ-ゖァ-ヺー]+$")
# (辞書形, て形, た形, ない形)；ます形仍用 wordtables 的值
SPECIAL = {
    "いく": ("いって", "いった", "いかない"),
    "ある": ("あって", "あった", "ない"),
    "くる": ("きて", "きた", "こない"),
    "する": ("して", "した", "しない"),
}


def forms(jisho, group, masu):
    if jisho in SPECIAL:
        te, ta, nai = SPECIAL[jisho]
    elif group == "irregular" and jisho.endswith("する"):
        stem = jisho[:-2]
        te, ta, nai = stem + "して", stem + "した", stem + "しない"
    elif group == "ichidan":
        stem = jisho[:-1]
        te, ta, nai = stem + "て", stem + "た", stem + "ない"
    else:
        last = jisho[-1]
        if last not in TE_OF:
            raise SystemExit("不支援的語尾：%s（%s）" % (last, jisho))
        stem = jisho[:-1]
        te = stem + TE_OF[last]
        ta = te[:-1] + ("だ" if te.endswith("で") else "た")
        nai = stem + NAI_OF[last] + "ない"
    return {"masu": masu, "te": te, "ta": ta, "nai": nai}


def norm_kanji(kanji, kana):
    kanji = kanji or ""
    return "" if kanji == kana else kanji


def audio_for(x, f):
    """回傳該行可用的音檔：辞書形用現有 audio/verb/，其餘看 audio/verbform/。"""
    got = {}
    if x.get("audio") and os.path.exists(os.path.join(ROOT, x["audio"])):
        got["dict"] = x["audio"]
    for name in ("masu", "te", "ta", "nai"):
        rel = "audio/verbform/%s-%d-%s.mp3" % (x["id"], x["vi"], name)
        if os.path.exists(os.path.join(ROOT, rel)):
            got[name] = rel
    return got


def main():
    data = json.load(open(WT, encoding="utf-8"))["verbs"]
    rows = []
    for g in data["groups"]:
        # 按 (假名, 漢字) 收攏：ひく＝引く／弾く、つく＝着く／点く、とる＝取る／撮る
        # 各自成行；同一字的重複課次合併，課號全列。
        bucket = {}
        for x in g["items"]:
            bucket.setdefault((x["kana"], norm_kanji(x.get("kanji"), x["kana"])), []).append(x)
        for (kana, kanji), xs in bucket.items():
            head = xs[0]
            lessons = sorted({x["id"] for x in xs})
            f = forms(kana, g["id"], head["masu"])
            rows.append({
                "group": g["id"],
                "src": "%s-%d" % (head["id"], head["vi"]),
                "kanji": kanji,
                "kana": kana,
                "zh": next((x["zh"] for x in xs if x.get("zh")), ""),
                "lessons": lessons,
                "masu": f["masu"], "te": f["te"], "ta": f["ta"], "nai": f["nai"],
                "audio": audio_for(head, f),
                "_order": (head["id"], head["vi"]),
            })

    for r in rows:
        for name in ("kana", "masu", "te", "ta", "nai"):
            if not KANA.match(r[name]):
                raise SystemExit("非假名：%s %s=%r" % (r["src"], name, r[name]))
        if r["kanji"] == r["kana"]:
            r["kanji"] = ""
        del r["_order"]

    def block(title, items):
        return {"title": title, "rows": items}

    sets = []
    godan = [r for r in rows if r["group"] == "godan"]
    order = ["わ行", "か行", "さ行", "た行", "な行", "ば行", "ま行", "ら行"]
    blocks = []
    for name in order:
        xs = [r for r in godan if ROW_OF[r["kana"][-1]] == name]
        if xs:
            blocks.append(block(name, xs))
    sets.append({"id": "godan", "title": "五段動詞", "kana": "ごだんどうし",
                 "total": len(godan), "blocks": blocks})

    ichidan = [r for r in rows if r["group"] == "ichidan"]
    e = [r for r in ichidan if r["kana"][-2] in E_ROW]
    i = [r for r in ichidan if r["kana"][-2] not in E_ROW]
    sets.append({"id": "ichidan", "title": "一段動詞", "kana": "いちだんどうし",
                 "total": len(ichidan),
                 "blocks": [block("〜える", e), block("〜いる", i)]})

    irr = [r for r in rows if r["group"] == "irregular"]
    suru = [r for r in irr if r["kana"].endswith("する")]
    kuru = [r for r in irr if not r["kana"].endswith("する")]
    sets.append({"id": "irregular", "title": "不規則動詞", "kana": "ふきそくどうし",
                 "total": len(irr),
                 "blocks": [block("する系", suru), block("来る", kuru)]})

    out = {"v": 1, "note": "辞書形由來：data/wordtables.json；て形・た形・ない形由規則生成。",
           "sets": sets}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("已寫 %s" % os.path.relpath(OUT, ROOT))
    for s in sets:
        print("  %s %d：%s" % (s["id"], s["total"],
              "、".join("%s %d" % (b["title"], len(b["rows"])) for b in s["blocks"])))
    withaudio = sum(1 for r in rows if r["audio"].get("te"))
    print("  有て形示範音檔：%d 行" % withaudio)


if __name__ == "__main__":
    sys.exit(main())
