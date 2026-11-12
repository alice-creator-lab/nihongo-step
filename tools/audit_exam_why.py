#!/usr/bin/env python3
"""核對考試題「漢字読み」的解釋：把 why 裡逐字讀音串起來，必須等於正確答案的假名。

針對這種寫法：
  「誕生日＝たんじょうび。「誕」は たん、「生」は しょう が 濁って じょう、…」
串起來＝たん＋じょう＋び，與答案比對。讀音寫錯（例如把 じょう 寫成 しょう）
就會對不上，這正是學生會回報的那類錯誤。

用法： python3 tools/audit_exam_why.py
退出碼 0 ＝ 全部一致；1 ＝ 有對不上的題目。
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIR = re.compile(r"「(.+?)」は\s*([ぁ-ゖァ-ヺー]+)(?:\s*が\s*濁って\s*([ぁ-ゖァ-ヺー]+))?")
KANA = re.compile(r"^[ぁ-ゖァ-ヺー]+$")


def kana(s):
    return re.sub(r"\s", "", s)


def main():
    bad, checked = [], 0
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "exam-*.json"))):
        items = json.load(open(path, encoding="utf-8")).get("items", [])
        for it in items:
            if it.get("part") != "moji":
                continue
            ans = it.get("options", [None] * 9)[it.get("answer", -1)] if it.get("answer") is not None else None
            if not ans or not KANA.match(kana(ans)):
                continue
            why = it.get("why", "")
            head = why.split("＝")[0]
            kanji = re.findall(r"[\u4e00-\u9fff]", head)
            pairs = PAIR.findall(why)
            # 只在「每個漢字都講到」且沒有否定句（「ざい ではなく さい」）時自動核對，
            # 其餘留給人手看，避免把省略寫法的題目誤報成錯
            if not pairs or len(pairs) != len(kanji) or "ではなく" in why:
                continue
            rebuilt = "".join(kana(p[2] or p[1]) for p in pairs)
            checked += 1
            if rebuilt != kana(ans):
                bad.append((os.path.basename(path), it.get("id"), it.get("q"), ans, rebuilt,
                            it.get("why")))
    print("已核對 %d 題（why 有逐字讀音的漢字読み題）" % checked)
    if not bad:
        print("全部一致")
        return 0
    print("對不上 %d 題：" % len(bad))
    for f, i, q, ans, rebuilt, why in bad:
        print("\n[%s %s] %s" % (f, i, q))
        print("  答案：%s   解釋串起來：%s" % (ans, rebuilt))
        print("  why：%s" % why)
    return 1


sys.exit(main())
