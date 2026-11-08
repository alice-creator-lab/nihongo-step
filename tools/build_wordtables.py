#!/usr/bin/env python3
"""由各課單字建立「動詞表」與「形容詞表」的資料檔，並補上動詞的原形人聲。

分類：
  動詞  -> 五段 / 一段 / 不規則（する・来る）
  形容詞 -> い形容詞 / な形容詞

單字表的假名有些寫「ます形」（いきます），有些寫原形（あらう），
本工具一律換算成原形＋ます形，並依原形判斷動詞種類。

用法：
  python3 tools/build_wordtables.py            # 只補缺的音檔
  python3 tools/build_wordtables.py --force-audio
"""
import glob, json, os, subprocess, sys, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE = "ja-JP-NanamiNeural"

I_ROW = "いきぎしじちぢにひびぴみり"
E_ROW = "えけげせぜてでねへべぺめれ"
TO_U = {"い": "う", "き": "く", "ぎ": "ぐ", "し": "す", "ち": "つ", "に": "ぬ",
        "ひ": "ふ", "び": "ぶ", "ぴ": "ぷ", "み": "む", "り": "る"}
TO_I = {"う": "い", "く": "き", "ぐ": "ぎ", "す": "し", "つ": "ち", "ぬ": "に",
        "ぶ": "び", "む": "み", "る": "り", "ふ": "ひ", "ぷ": "ぴ"}

# ます形・字幹在い段但其實是一段動詞（其餘い段字幹一律五段）
ICHIDAN_I_STEM = {"みます", "おきます", "います", "できます", "かります", "しんじます",
                  "ぞんじます", "おちます", "みえます", "きこえます", "おぼえます",
                  "かんがえます", "つたえます", "こたえます"}
# ます形機械轉換會得出錯原形的（尊敬語）：いらっしゃいます→いらっしゃう 是錯的
MASU_FIX = {"いらっしゃいます": "いらっしゃる", "おっしゃいます": "おっしゃる"}

# 原形看起來像一段、其實是五段的（漢字讀音陷阱）
GODAN_RU = {"しる", "かえる", "はしる", "はいる", "きる", "いる", "へる", "すべる",
            "にぎる", "まいる", "しゃべる", "あせる", "かぎる", "けずる", "ちる",
            "よみがえる", "かみきる"}


def classify(kana, kanji, suru_nouns):
    """回傳 (類型, 原形假名, ます形假名)；判斷不到就回傳 None。"""
    k = kana.strip()
    if not k:
        return None
    if k in MASU_FIX:
        return ("godan", MASU_FIX[k], k)

    # 不規則：来る
    if k == "きます" and (kanji or "").startswith("来"):
        return ("irregular", "くる", "きます")
    if k == "くる" or (k == "きます" and not kanji):
        return ("irregular", "くる", "きます")

    if k.endswith("ます"):
        stem = k[:-2]
        if not stem:
            return None
        # する（含名詞＋する）：勉強します / べんきょうします
        if stem.endswith("し") and stem[:-1] in suru_nouns:
            return ("irregular", stem[:-1] + "する", k)
        if k == "します":
            return ("irregular", "する", "します")
        if k in ICHIDAN_I_STEM or stem[-1] in E_ROW:
            return ("ichidan", stem + "る", k)
        if stem[-1] in I_ROW:
            return ("godan", stem[:-1] + TO_U[stem[-1]], k)
        return None

    # 已是原形
    def to_masu(j):
        if j.endswith("する"):
            return j[:-2] + "します"
        if j == "くる":
            return "きます"
        if j.endswith("る"):
            prev = j[-2:-1]
            if prev in I_ROW or prev in E_ROW:
                if j not in GODAN_RU:
                    return j[:-1] + "ます"
            return j[:-1] + "ります"
        last = j[-1:]
        if last in TO_I:
            return j[:-1] + TO_I[last] + "ます"
        return None

    if k.endswith("する"):
        return ("irregular", k, k[:-2] + "します")
    if k == "くる":
        return ("irregular", "くる", "きます")
    if k.endswith("る"):
        prev = k[-2:-1]
        grp = "godan" if (k in GODAN_RU or prev not in (I_ROW + E_ROW)) else "ichidan"
        return (grp, k, to_masu(k))
    if k[-1:] in TO_I:
        return ("godan", k, to_masu(k))
    return None


def adj_type(pos, kana):
    p = pos or ""
    if "な形" in p or "形容動詞" in p or "な形容詞" in p:
        return "na"
    if "い形" in p or "い形容詞" in p:
        return "i"
    if "形容詞" in p:
        return "i" if kana.endswith("い") else "na"
    return None


def synth(text, out):
    for _ in range(3):
        r = subprocess.run(["edge-tts", "--voice", VOICE, "--text", text,
                            "--write-media", out], capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 900:
            return True
    return False


def main():
    force_audio = "--force-audio" in sys.argv
    files = sorted(glob.glob(os.path.join(ROOT, "data/lesson-L*.json")))
    lessons = [json.load(open(f, encoding="utf-8")) for f in files]

    # 先收集「名詞＋する」的名詞部分（漢字以する結尾的項目）
    suru_nouns = set()
    for les in lessons:
        for v in les.get("vocab", []):
            kanji = v.get("kanji") or ""
            kana = v.get("kana") or ""
            if kanji.endswith("する") and kana.endswith("します"):
                suru_nouns.add(kana[:-3])
    suru_nouns |= {"べんきょう", "そうじ", "せんたく", "よやく", "さんぽ", "コピー",
                   "うんてん", "かくにん", "せつめい", "しょうかい", "れんしゅう",
                   "しんぱい", "はいけん", "でんわ", "りょうり", "けいかく", "あんない"}

    verbs, adjs, skipped = [], [], []
    for les in lessons:
        for vi, v in enumerate(les.get("vocab", [])):
            pos = v.get("pos") or ""
            kana = v.get("kana") or ""
            kanji = v.get("kanji") or ""
            zh = v.get("zh") or ""
            if "動詞" in pos and "形容動詞" not in pos:
                got = classify(kana, kanji, suru_nouns)
                if not got:
                    skipped.append((les["id"], kanji, kana, zh))
                    continue
                grp, jisho, masu = got
                verbs.append({"id": les["id"], "vi": vi, "group": grp,
                              "kanji": kanji, "kana": jisho, "jisho": jisho,
                              "masu": masu or "", "zh": zh,
                              "audio": "audio/verb/%s-%d.mp3" % (les["id"], vi)})
            elif "形容" in pos:
                t = adj_type(pos, kana)
                if not t:
                    skipped.append((les["id"], kanji, kana, zh))
                    continue
                adjs.append({"id": les["id"], "vi": vi, "group": t,
                             "kanji": kanji, "kana": kana, "zh": zh,
                             "audio": "audio/adj/%s-%d.mp3" % (les["id"], vi)})

    # 去重（同一課同一個字只留一次；不同課重複的照留，方便對照）
    def uniq(items):
        seen, out = set(), []
        for x in items:
            sig = x["id"] + "|" + x["kanji"] + "|" + x["kana"] + "|" + x["zh"]
            if sig in seen:
                continue
            seen.add(sig)
            out.append(x)
        return out

    verbs, adjs = uniq(verbs), uniq(adjs)

    vgroups = [("godan", "五段動詞"), ("ichidan", "一段動詞"), ("irregular", "不規則（する・来る）")]
    agroups = [("i", "い形容詞"), ("na", "な形容詞")]
    data = {
        "verbs": {
            "total": len(verbs),
            "groups": [{"id": g, "title": t, "items": [x for x in verbs if x["group"] == g]}
                       for g, t in vgroups],
        },
        "adjs": {
            "total": len(adjs),
            "groups": [{"id": g, "title": t, "items": [x for x in adjs if x["group"] == g]}
                       for g, t in agroups],
        },
    }

    out_path = os.path.join(ROOT, "data/wordtables.json")
    json.dump(data, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("動詞 %d（五段 %d、一段 %d、不規則 %d）" % (
        len(verbs),
        len(data["verbs"]["groups"][0]["items"]),
        len(data["verbs"]["groups"][1]["items"]),
        len(data["verbs"]["groups"][2]["items"])))
    print("形容詞 %d（い %d、な %d）" % (
        len(adjs),
        len(data["adjs"]["groups"][0]["items"]),
        len(data["adjs"]["groups"][1]["items"])))
    if skipped:
        print("未分類：", len(skipped), skipped[:6])

    # 動詞原形人聲、形容詞人聲（各自一套，方便剪靜音做「播放全部」）
    jobs = []
    for x in verbs:
        jobs.append((x["kana"], os.path.join(ROOT, x["audio"])))
    for x in adjs:
        jobs.append((x["kana"], os.path.join(ROOT, x["audio"])))
    print("音檔：共 %d 段（動詞 %d、形容詞 %d）" % (len(jobs), len(verbs), len(adjs)), flush=True)
    todo = [(txt, out) for txt, out in jobs
            if force_audio or not (os.path.exists(out) and os.path.getsize(out) > 900)]
    for txt, out in todo:
        os.makedirs(os.path.dirname(out), exist_ok=True)
    print("待生成 %d 段" % len(todo), flush=True)
    fail = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for ok in ex.map(lambda j: synth(j[0], j[1]), todo):
            if not ok:
                fail += 1
    if todo:
        print("完成：成功 %d，失敗 %d" % (len(todo) - fail, fail))
        print("記得剪靜音：python3 tools/trim_seq_audio.py audio/verb && python3 tools/trim_seq_audio.py audio/adj")


if __name__ == "__main__":
    main()
