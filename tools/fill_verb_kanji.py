#!/usr/bin/env python3
"""補動詞漢字（以《日本語GoGoGo 2 文法整理・動詞整理》校對）。

- BOOK：書上明確印了漢字的動詞（書上寫假名的話不補）。
- STD：書未收錄（多為後半課程）但常用漢字寫法明確的動詞。
- KANA_ONLY：書上用假名或慣例寫假名的（ある、いる、する、なる、やかる 等），不補。
- 特別個案：
    きる：五段＝切る、一段＝着る
    つく：L26-8＝点く（燈亮）、L35-22＝着く（抵達）
    とる：L12-1＝取る（拿）、L20-11＝撮る（拍照）
- 同時寫回 data/lesson-L*.json 與 data/wordtables.json；之後重跑
  tools/build_verbforms.py 生成 data/verbforms.json。

用法：python3 tools/fill_verb_kanji.py [--check]
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 書上直接抄下（保留書上漢字；書上寫假名的不在此表）
BOOK = {
    "あう": "会う", "あらう": "洗う", "いう": "言う", "うたう": "歌う", "おもう": "思う",
    "すう": "吸う", "つかう": "使う", "てつだう": "手伝う", "ならう": "習う",
    "あるく": "歩く", "おく": "置く", "いそぐ": "急ぐ", "およぐ": "泳ぐ", "みがく": "磨く",
    "おとす": "落とす", "おろす": "下ろす", "かす": "貸す", "けす": "消す", "だす": "出す",
    "なおす": "直す", "なくす": "無くす", "ひっこす": "引っ越す", "やくす": "訳す",
    "うつ": "打つ", "まつ": "待つ", "もつ": "持つ", "あそぶ": "遊ぶ", "よぶ": "呼ぶ",
    "こむ": "込む", "すむ": "住む", "やすむ": "休む",
    "おどる": "踊る", "おわる": "終わる", "がんばる": "頑張る", "しる": "知る",
    "つくる": "作る", "とおる": "通る", "とまる": "止まる", "のぼる": "登る", "のる": "乗る",
    "ふる": "降る", "でる": "出る", "あける": "開ける", "あつめる": "集める",
    "いれる": "入れる", "おきる": "起きる", "おくれる": "遅れる", "おしえる": "教える",
    "おぼえる": "覚える", "おりる": "降りる", "かりる": "借りる", "かんがえる": "考える",
    "しめる": "閉める", "すてる": "捨てる", "たべすぎる": "食べすぎる",
    "つかれる": "疲れる", "つとめる": "勤める", "とめる": "止める", "なれる": "慣れる",
    "ねる": "寝る", "のみすぎる": "飲みすぎる", "まちがえる": "間違える",
    "みせる": "見せる", "わすれる": "忘れる",
    "うんてんする": "運転する", "そうじする": "掃除する", "よやくする": "予約する",
    "せつめいする": "説明する", "しょうかいする": "紹介する", "れんしゅうする": "練習する",
}

# 書未收錄、但常用漢字寫法明確（後半課程的動詞）
STD = {
    "まにあう": "間に合う", "ちがう": "違う", "そう": "沿う", "わらう": "笑う",
    "うかがう": "伺う", "はたらく": "働く", "はく": "履く", "あく": "開く",
    "ふく": "吹く", "なく": "泣く", "おどろく": "驚く", "こわす": "壊す",
    "よごす": "汚す", "おす": "押す", "ゆるす": "許す", "かえす": "返す",
    "よろこぶ": "喜ぶ", "すすむ": "進む", "やむ": "止む", "ぬすむ": "盗む",
    "はじまる": "始まる", "ほしがる": "欲しがる", "しまる": "閉まる",
    "みつかる": "見つかる", "かざる": "飾る", "くもる": "曇る", "あがる": "上がる",
    "さがる": "下がる", "ひろがる": "広がる", "のこる": "残る", "はる": "貼る",
    "しかる": "叱る", "こまる": "困る", "おくる": "送る", "めしあがる": "召し上がる",
    "ごらんになる": "ご覧になる", "はじめる": "始める", "きこえる": "聞こえる",
    "みえる": "見える", "きえる": "消える", "こわれる": "壊れる", "よごれる": "汚れる",
    "ならべる": "並べる", "つづける": "続ける", "あきらめる": "諦める", "きめる": "決める",
    "われる": "割れる", "ほめる": "褒める", "たてる": "建てる", "つかまえる": "捕まえる",
    "しらべる": "調べる", "かたづける": "片付ける", "あびる": "浴びる", "おちる": "落ちる",
    "しんじる": "信じる", "ぞんじる": "存じる", "はれる": "晴れる",
    "まがる": "曲がる", "わたる": "渡る", "せんたくする": "洗濯する",
    "さんぽする": "散歩する", "かくにんする": "確認する", "しんぱいする": "心配する",
    "はいけんする": "拝見する",
}

# 書上用假名／慣例假名，不補
KANA_ONLY = {"ある", "いる", "する", "なる", "やる", "わかる", "かかる", "もらう",
             "あげる", "くれる", "つける", "かける", "たがる", "できる", "いらっしゃる",
             "おっしゃる", "おる", "いたす", "もうす", "かぶる", "すく", "むく"}

# 同音但不同字／不同意思
GROUP_OVERRIDE = {("godan", "きる"): "切る", ("ichidan", "きる"): "着る"}
ITEM_OVERRIDE = {
    ("L26", 8): "点く",     # つく＝燈亮
    ("L35", 22): "着く",    # つく＝抵達
    ("L12", 1): "取る",     # とる＝拿
    ("L20", 11): "撮る",    # とる＝拍照
}


def want(group, kana):
    if (group, kana) in GROUP_OVERRIDE:
        return GROUP_OVERRIDE[(group, kana)]
    return BOOK.get(kana) or STD.get(kana)


def main():
    check = "--check" in sys.argv
    wt_path = os.path.join(ROOT, "data/wordtables.json")
    data = json.load(open(wt_path, encoding="utf-8"))
    wt = data["verbs"]
    lessons = {os.path.basename(p)[7:10]: json.load(open(p, encoding="utf-8"))
               for p in sorted(glob.glob(os.path.join(ROOT, "data/lesson-L*.json")))}

    changed_wt = changed_les = 0
    unmapped = []
    touched = set()
    # 同一組同一假名已有漢字的，空格沿用（例如 よむ 有 読む、另有空白重複項）
    existing = {}
    for g in wt["groups"]:
        for x in g["items"]:
            if x["kanji"]:
                existing.setdefault((g["id"], x["kana"]), x["kanji"])
    for g in wt["groups"]:
        for x in g["items"]:
            if x["kanji"]:
                continue
            kanji = (ITEM_OVERRIDE.get((x["id"], x["vi"]))
                     or want(g["id"], x["kana"])
                     or existing.get((g["id"], x["kana"])))
            if not kanji:
                if x["kana"] not in KANA_ONLY:
                    unmapped.append((g["id"], x["kana"], x["zh"]))
                continue
            if check:
                print("would set", x["id"], x["vi"], x["kana"], "→", kanji)
                continue
            x["kanji"] = kanji
            v = lessons[x["id"]]["vocab"][x["vi"]]
            if not v.get("kanji"):
                v["kanji"] = kanji
                touched.add(x["id"])
                changed_les += 1
            changed_wt += 1

    if check:
        print("未對應：", len(unmapped))
        for u in unmapped:
            print("  ", u)
        return

    json.dump(data, open(wt_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for lid in sorted(touched):
        p = os.path.join(ROOT, "data/lesson-%s.json" % lid)
        json.dump(lessons[lid], open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(p, "a", encoding="utf-8").write("\n")

    left = [x["kana"] for g in wt["groups"] for x in g["items"] if not x["kanji"]]
    print("補了 %d 個動詞（單字表 %d 處）；仍無漢字 %d 個：%s"
          % (changed_wt, changed_les, len(left), "、".join(sorted(set(left))) or "無"))
    if unmapped:
        print("未對應：")
        for u in unmapped:
            print("  ", u)


if __name__ == "__main__":
    main()
