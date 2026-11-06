#!/usr/bin/env python3
"""把資料檔的漢字句＋假名句變成「朗讀文字」。

原則：發音一律以資料檔的假名（kana）為準，跟單字表用假名合成完全一致。
例句原本直接把漢字交給 edge-tts，遇到多讀音的字就會讀錯
（「町」讀成 ちょう），跟單字表教的 まち 不一致。

只做兩件事：
  1. 漢字詞換成假名讀音（讀音取自同一句的 kana，所以是上下文正確的讀法）。
  2. 助詞 は／へ／を 寫成 わ／え／お——整句假名時 edge-tts 會把助詞「は」
     讀成 ha（實測：漢字句讀 wa，純假名句讀 ha），所以要自己改寫。

助詞判斷（is_particle_ha）：
  - 句首、或讀音下一字是 ん／し／な／は／よ 或 じ（はじめ）→ 不是助詞
    （はい、ごはん、はし、はな、母はは、おはよう、はじめまして）
  - 其餘一律當助詞，寫成 わ（わたしは、これは、さんは、てはいけない…）

無法對齊的句子（例如原句寫阿拉伯數字、假名卻寫成讀音）整句退回漢字原句：
漢字句 edge-tts 會把「は」讀 wa，也不會把「はち」誤改成「わち」。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_readings as ar   # noqa: E402  對齊用同一套邏輯，避免兩份實作

KANJI = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff々〆ヶ]+')
NAMES = {"田中": "たなか", "鈴木": "すずき", "佐藤": "さとう", "山田": "やまだ",
         "林": "りん", "李": "り", "王": "おう"}

_WHOLE = None


def _whole():
    global _WHOLE
    if _WHOLE is None:
        gloss = ar.build_gloss(ar.load_lessons())
        _WHOLE, _ = ar.build_readings(gloss)
    return _WHOLE


def is_particle_ha(nxt, prev):
    """判斷 ja 句裡這個「は」是否助詞（是助詞就要寫成「わ」才會讀 wa）。

    nxt：下一個 token 的讀音；prev：已輸出文字的最後一個字。
    只有幾個寫成假名的詞不是助詞：はい／はじめ／おはよう／ごはん。
    其餘（わたしは、これは、こんにちは、では…）都當助詞，讀音一樣是 wa。
    """
    if prev in ('ご', 'お') and nxt.startswith('ん'):     # ごはん、昼ごはん
        return False
    if prev == 'お' and nxt.startswith('よ'):            # おはよう
        return False
    if prev in ('', '。', '、', '？', '！', '「', '『', ' ') and nxt[:1] in ('い', 'じ'):
        return False                                     # はい、はじめまして
    return True


def align(ja, kana):
    """（給 print_speech.py 用）回傳 ([(kind, surface, reading)], 已用假名字數)。"""
    toks, ok = ar.tokenize(ja, kana, _whole())
    if not ok:
        return [], 0
    return [(t[0], t[1], t[2]) for t in toks], len(kana)


def speech(ja, kana):
    """回傳 (朗讀文字, 對齊是否完整)。"""
    ja, kana = ja or '', kana or ''
    if not kana:
        return ja, False
    toks, ok = ar.tokenize(ja, kana, _whole())
    if not ok:
        return ja, False
    out = []
    i = 0
    while i < len(toks):
        kind, surf, reading = toks[i]
        if kind == 's':                      # 引號、空格：不讀；省略號保留停頓
            if surf == '…':
                out.append('…')
            i += 1
            continue
        if kind == 'k':
            out.append(NAMES.get(surf, reading))
        elif kind == 'x':
            out.append(reading)
        else:
            nxt = ''
            for t in toks[i + 1:]:
                if t[0] != 's':
                    nxt = t[2][:2] if t[0] != 'j' else t[2]
                    break
            prev = out[-1][-1] if out and out[-1] else ''
            if surf == 'は':
                out.append('わ' if is_particle_ha(nxt, prev) else 'は')
            elif surf == 'へ':
                out.append('へ' if nxt.startswith('え') else 'え')
            elif surf == 'を':
                out.append('お')
            else:
                out.append(surf)
        i += 1
    return ''.join(out), True


if __name__ == "__main__":
    import json
    les = json.load(open(sys.argv[1], encoding="utf-8"))
    for key, ex in [("p%d-e%d" % (pi, ei), ex)
                    for pi, pat in enumerate(les.get("patterns", []))
                    for ei, ex in enumerate(pat.get("ex", []))] + \
                   [("g%d-e%d" % (gi, ei), ex)
                    for gi, sec in enumerate(les.get("grammar", []))
                    for ei, ex in enumerate(sec.get("ex", []))]:
        sp, ok = speech(ex.get("ja", ""), ex.get("kana", ""))
        print(key, ex.get("ja"), "→", sp, "" if ok else "（對齊不完整）")
