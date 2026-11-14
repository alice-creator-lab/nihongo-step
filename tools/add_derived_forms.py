# -*- coding: utf-8 -*-
"""為「衍生形」（可能形・意志形・ば形・受身形・使役形）補上 form 標籤。

句型用 ja、文法用 h 對位；只動指定課。
用法：python3 tools/add_derived_forms.py
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# lesson: {section: [(heading, form), ...]}
MAP = {
  "L24": {
    "patterns": [
      ("五段動詞：語尾改え段＋る", "pot"),
      ("一段動詞：る→られる", "pot"),
      ("する→できる、来る→来られる", "pot"),
      ("名詞＋ができます", "pot"),
      ("可能句的「を」變成「が」", "pot"),
    ],
    "grammar": [
      ("先分動詞類別，再改可能形", "pot"),
      ("「ら抜き言葉」：可以聽，不要寫", "pot"),
      ("「できる」身兼兩職", "pot"),
      ("「ことができる」比可能形正式", "dict"),
      ("可能句的助詞：を→が", "pot"),
      ("可能形的否定與疑問", "pot"),
      ("「見える」「聞こえる」是另一組", "pot"),
    ],
  },
  "L28": {
    "patterns": [
      ("意志形（〜よう／〜おう）", "vol"),
      ("意志形＋と思っています", "vol"),
    ],
    "grammar": [
      ("意志形的造法", "vol"),
      ("意志形單用的場合", "vol"),
    ],
  },
  "L34": {
    "patterns": [
      ("～ば、～", "ba"),
      ("～ば～ほど", "ba"),
      ("～ばいい", "ba"),
      ("～ばよかった", "ba"),
    ],
    "grammar": [
      ("ば形的造法：三類動詞各一招", "ba"),
      ("い形容詞、な形容詞、名詞的ば形", "ba"),
      ("ば形的後句限制（依前件性質而定）", "ba"),
      ("「～ば～ほど」的兩種重複方式", "ba"),
      ("「～ばよかった」是對自己的後悔", "ba"),
    ],
  },
  "L37": {
    "patterns": [
      ("～に～られます", "pass"),
      ("～は～に～を～られます", "pass"),
      ("～は～に～られます（事物做主語）", "pass"),
      ("～によって～られます", "pass"),
      ("～に～られます（自動詞）", "pass"),
      ("～と言われています", "pass"),
    ],
    "grammar": [
      ("被動形的做法：三類動詞各自變化", "pass"),
      ("「に」和「によって」的差別", "pass"),
      ("受害被動：擁有者的「を」", "pass"),
      ("迷惑受身：自動詞加「に」", "pass"),
      ("事物做主語時，被動比主動自然", "pass"),
      ("被動與「てもらう」的視角差", "pass"),
      ("「と言われています」與「と考えられています」", "pass"),
    ],
  },
  "L39": {
    "patterns": [
      ("～は～に～をさせます", "caus"),
      ("～は～を～させます", "caus"),
      ("～させてください", "caus"),
      ("～させていただけませんか", "caus"),
      ("～（さ）せられます", "caus"),
      ("～させられます（情不自禁）", "caus"),
    ],
    "grammar": [
      ("使役形的做法", "caus"),
      ("「に」還是「を」：看動詞類型", "caus"),
      ("「させてください」的禮貌層級", "caus"),
      ("「させていただきます」的用法與濫用", "caus"),
      ("使役被動：被迫的無奈", "caus"),
      ("使役被動的第二義：情不自禁", "caus"),
      ("使役的使用界線", "caus"),
    ],
  },
}


def indent_of(text):
    for line in text.splitlines()[1:]:
        m = re.match(r'^(\s+)"', line)
        if m:
            return len(m.group(1))
    return 2


def main():
    changed, missing = 0, []
    for lid, kinds in MAP.items():
        path = os.path.join(ROOT, f"data/lesson-{lid}.json")
        raw = open(path, encoding="utf-8").read()
        d = json.loads(raw)
        for kind, pairs in kinds.items():
            key = "ja" if kind == "patterns" else "h"
            index = {it.get(key): it for it in d.get(kind, [])}
            for label, form in pairs:
                it = index.get(label)
                if it is None:
                    missing.append((lid, kind, label))
                    continue
                if it.get("form") == form:
                    continue
                before = {k: v for k, v in it.items() if k not in (key, "form")}
                it.clear()
                it[key] = label
                it["form"] = form
                it.update(before)
                changed += 1
        open(path, "w", encoding="utf-8").write(
            json.dumps(d, ensure_ascii=False, indent=indent_of(raw)) + "\n")
    print("更新段落：", changed)
    for m in missing:
        print("  找不到：", m)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
