#!/usr/bin/env python3
"""核對例句（句型／文法／會話／聽力）的假名讀音，確認與單字表教過的讀法一致。

做法：
  1. 由 40 課單字表建立「漢字 → 假名」詞庫。
  2. 把每句 ja 與 kana 對齊。對齊有歧義時（例如「母は」可以切成 はは＋は 或 は＋はは），
     以單字表出現過的讀音為優先，令切分盡量落在學過的詞上。
  3. 回報：讀音跟單字表不一致的漢字詞、無法對齊的句子、以及不在單字表的漢字。

朗讀音檔由 kana 直接合成，所以這支腳本同時就是「音檔讀音」的檢查。

用法：
  python3 tools/audit_readings.py              # 全部 40 課
  python3 tools/audit_readings.py L08          # 只查一課
  python3 tools/audit_readings.py --tts L08    # 印出建議的朗讀文字
  python3 tools/audit_readings.py --strict     # 有任何問題即回傳非 0
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KANJI = re.compile(r"[\u3400-\u9fff々〆ヶ]")
DIGITS = re.compile(r"[0-9０-９]+")
NORM = str.maketrans({"，": "、", "．": "。", "！": "。", "？": "。", "～": "", "~": "",
                      ",": "、", "!": "。", "?": "。", "・": "", "「": "", "」": "",
                      "『": "", "』": "", "（": "", "）": "", "(": "", ")": "",
                      " ": "", "\u3000": "", "…": "", "：": "", ":": ""})


NORM_CHAR = {chr(k): v for k, v in NORM.items()}
SKIP = '\u0000'          # 原文有、假名沒有的符號（引號、空格等）在比對時用這個佔位


def to_hira(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:  # 片假名 → 平假名（比對用）
            out.append(chr(o - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def load_lessons(only=None):
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data/lesson-L*.json"))):
        lid = os.path.basename(p)[7:10]
        if only and lid not in only:
            continue
        out.append((lid, json.load(open(p, encoding="utf-8"))))
    return out


def build_gloss(lessons):
    """漢字詞 → {讀音: {課號}}。同一個詞在不同課有不同讀音時，兩種都會保留。"""
    gloss = {}
    for lid, les in lessons:
        for v in les.get("vocab", []):
            k = v.get("kanji")
            if not k:
                continue
            gloss.setdefault(k, {}).setdefault(to_hira(v["kana"]), set()).add(lid)
    return gloss


def build_readings(gloss):
    """單字表出現過的所有讀音，以及每個讀音的前綴，用來判斷對齊是否落在學過的詞上。"""
    whole, prefix = set(), set()
    for k, readings in gloss.items():
        for r in readings:
            whole.add(r)
            for i in range(1, len(r) + 1):
                prefix.add(r[:i])
    return whole, prefix


def kanji_run(s, i):
    k = i
    while k < len(s) and KANJI.match(s[k]):
        k += 1
    return k


def is_opaque(ch):
    return bool(KANJI.match(ch) or DIGITS.match(ch))


def opaque_run(s, i):
    """漢字與數字連在一起時當成一個單位（10分 → じゅっぷん），避免切開比對。"""
    k = i
    while k < len(s) and is_opaque(s[k]):
        k += 1
    return k


def _norm_chars(s):
    out = []
    for c in s:
        c = NORM_CHAR.get(c, c)
        if not c:
            out.append(SKIP)
            continue
        o = ord(c)
        if 0x30A1 <= o <= 0x30F6:      # 片假名 → 平假名（只影響比對，不影響輸出）
            c = chr(o - 0x60)
        out.append(c)
    return out


def tokenize(ja, kana, whole):
    """把句子切成 token：('k', 漢字串, 讀音)、('x', 數字串, 讀音)、('j', 假名字元, 原字)。

    以單字表讀音為先驗做最佳切分（命中單字表讀音的切法優先，同分時取較短讀音），
    令「母は先生です」這種情況不會把「は」當成「母」的讀音。
    無法完整對齊時回傳 (None, False)。
    """
    jn, kn = _norm_chars(ja), _norm_chars(kana)
    memo = {}

    def rec(i, j):
        key = (i, j)
        if key in memo:
            return memo[key]
        if i == len(jn):
            memo[key] = (0, 0, []) if j == len(kn) else None
            return memo[key]
        if jn[i] == SKIP:             # 引號、空格、省略號：不讀，但要吃掉假名句對應的寫法
            jj = j
            while jj < len(kn) and kn[jj] == SKIP:
                jj += 1
            rest = rec(i + 1, jj)
            if rest is not None:
                memo[key] = (rest[0], rest[1], [('s', ja[i], '')] + rest[2])
            else:
                memo[key] = None
            return memo[key]
        if is_opaque(jn[i]):
            k = opaque_run(jn, i)
            best = None
            for L in range(1, len(kn) - j + 1):
                rest = rec(k, j + L)
                if rest is None:
                    continue
                hit, cost, toks = rest
                reading = kana[j:j + L]
                cand = (hit + (1 if ''.join(kn[j:j + L]) in whole else 0), cost + L * L,
                        [(('x' if DIGITS.match(jn[i]) else 'k'), ja[i:k], reading)] + toks)
                if best is None or (cand[0], -cand[1]) > (best[0], -best[1]):
                    best = cand
            memo[key] = best
            return best
        if j < len(kn) and jn[i] == kn[j]:
            rest = rec(i + 1, j + 1)
            if rest is not None:
                memo[key] = (rest[0], rest[1], [('j', ja[i], kn[j])] + rest[2])
            else:
                memo[key] = None
            return memo[key]
        memo[key] = None
        return None

    res = rec(0, 0)
    if res is None:
        return None, False
    return res[2], True


def align(ja, kana, whole):
    """回傳 (成功?, [(漢字串, 讀音)])。"""
    toks, ok = tokenize(ja, kana, whole)
    if not ok:
        return False, []
    return True, [(t[1], t[2]) for t in toks if t[0] in ('k', 'x')]


def tts_text(ja, pairs):
    out, i, pi = [], 0, 0
    while i < len(ja):
        if is_opaque(ja[i]):
            k = opaque_run(ja, i)
            if pi < len(pairs) and pairs[pi][0] == ja[i:k]:
                out.append(pairs[pi][1])
                pi += 1
            else:
                out.append(ja[i:k])
            i = k
        else:
            out.append(ja[i])
            i += 1
    return "".join(out)


def speak_text(ja, pairs, keys):
    """朗讀文字：只把「單字表有的漢字詞」換成讀音，其餘漢字保留。

    保留漢字是為了讓 TTS 判斷助詞（純假名時「は」會被讀成 ha）；
    換掉單字表的詞，是為了讓例句讀音跟單字表一致（町 まち，不是 TTS 猜的 ちょう）。
    """
    out, i, pi = [], 0, 0
    while i < len(ja):
        if is_opaque(ja[i]):
            k = opaque_run(ja, i)
            run = ja[i:k]
            if pi < len(pairs) and pairs[pi][0] == run:
                out.append(pairs[pi][1] if run in keys else run)
                pi += 1
            else:
                out.append(run)
            i = k
        else:
            out.append(ja[i])
            i += 1
    return "".join(out)


def examples(les):
    for pi, p in enumerate(les.get("patterns", [])):
        for ei, x in enumerate(p.get("ex", [])):
            yield f"p{pi}-e{ei}", "pattern", x
    for gi, g in enumerate(les.get("grammar", [])):
        for ei, x in enumerate(g.get("ex", [])):
            yield f"g{gi}-e{ei}", "grammar", x
    for di, d in enumerate(les.get("dialogues", [])):
        for li, x in enumerate(d.get("lines", [])):
            yield f"d{di}-l{li}", "dialogue", x
    for li, x in enumerate(les.get("listening", [])):
        yield f"l{li}", "listening", x


def main():
    show_tts = "--tts" in sys.argv
    strict = "--strict" in sys.argv
    verbose = "--verbose" in sys.argv
    only = set(a for a in sys.argv[1:] if a.startswith("L"))
    lessons = load_lessons(only or None)
    gloss = build_gloss(load_lessons(None))
    whole, prefix = build_readings(gloss)
    allow = {}
    allow_path = os.path.join(ROOT, "data/readings-allow.json")
    if os.path.exists(allow_path):
        for a in json.load(open(allow_path, encoding="utf-8")):
            allow[(a["kanji"], to_hira(a["kana"]))] = a.get("note", "")

    bad, noalign, unknown, total, skipped, allowed = [], [], [], 0, 0, []
    per = {}
    for lid, les in lessons:
        per.setdefault(lid, {"n": 0, "bad": 0, "ok": 0})
        for where, kind, x in examples(les):
            ja, kana = x.get("ja"), x.get("kana")
            if not ja:
                continue
            total += 1
            per[lid]["n"] += 1
            if not kana:
                noalign.append((lid, where, ja, "缺 kana"))
                continue
            ok, pairs = align(ja, kana, whole)
            if not ok:
                if DIGITS.search(ja):      # 數字在假名裡是讀法（090 → ぜろきゅうぜろ），不比對
                    skipped += 1
                else:
                    noalign.append((lid, where, ja, kana))
                continue
            if show_tts:
                print(f"  TTS {lid} {where}: {tts_text(ja, pairs)}")
            for run, reading in pairs:
                if DIGITS.match(run):
                    continue
                if run not in gloss:
                    unknown.append((lid, where, kind, run, reading, ja))
                    continue
                hit = to_hira(reading)
                if hit in gloss[run]:
                    continue
                # 漢字串只是詞幹（話します → 話），讀音是較長詞的開頭，屬正常
                if any(r.startswith(hit) for r in gloss[run]):
                    continue
                ref = "/".join(sorted(gloss[run]))
                if (run, to_hira(reading)) in allow:
                    allowed.append((lid, where, kind, run, reading, ref, ja))
                    continue
                bad.append((lid, where, kind, run, reading, ref, ja))

    print(f"檢查 {len(lessons)} 課、{total} 句（另有 {skipped} 句含數字，只核對假名不分項比對）")
    print(f"① 讀音與單字表不符、未核可：{len(bad)} 處")
    for lid, where, kind, run, reading, ref, ja in bad:
        print(f"  {lid} {where} [{kind}] 「{run}」讀成 {reading}，單字表為 {ref}｜{ja}")
    print(f"② 與單字表不同但已在 data/readings-allow.json 核可：{len(allowed)} 處")
    if verbose:
        for lid, where, kind, run, reading, ref, ja in allowed:
            print(f"  {lid} {where} [{kind}] 「{run}」→{reading}（單字表 {ref}）｜{ja}")
    print(f"③ 無法對齊／缺 kana：{len(noalign)} 處")
    for lid, where, ja, other in noalign:
        print(f"  {lid} {where}｜{ja}｜{other}")
    print(f"④ 不在任何單字表的漢字：{len(unknown)} 處，"
          f"{len(set(u[3] for u in unknown))} 個不同詞（朗讀一律用 kana，不再由 TTS 猜讀音）")
    if verbose:
        for lid, where, kind, run, reading, ja in unknown:
            print(f"  {lid} {where} 「{run}」→{reading}｜{ja}")
    if "--by-lesson" in sys.argv:
        for lid in sorted(per):
            p = per[lid]
            p["bad"] = (sum(1 for b in bad if b[0] == lid)
                        + sum(1 for b in noalign if b[0] == lid))
            print(f"  {lid}  句 {p['n']:3d}  讀音有問題 {p['bad']}")

    if strict:
        return 0 if not bad and not noalign else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
