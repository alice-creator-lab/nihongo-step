#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由課程自己的 ja／kana 對照，建立「漢字 → 假名讀音」對照表。

用途：自動辨識（Whisper）有時交出漢字（例：始まって），而評分是用假名比對，
所以要在背景把兩邊都轉成同一個形式。這裡用課程內的 ja／kana 對照推讀音，
不依賴外部字典。

輸出：data/kanji-readings.json  {"v":1,"dict":{"初":"はじ", ...}}
"""
import json
import glob
import re
import unicodedata
from collections import Counter, defaultdict

KANJI = re.compile(r'[\u4e00-\u9fff\u3005]')
PUNCT = re.compile(r'[\s\u3000、。，．,.！!？?「」『』（）()・…~～ー―\-]')


def to_hira(s):
    return ''.join(chr(ord(c) - 0x60) if '\u30a1' <= c <= '\u30f6' else c for c in s)


def clean(s):
    s = unicodedata.normalize('NFKC', to_hira(str(s or '')))
    return PUNCT.sub('', s)


def is_kanji(ch):
    return bool(KANJI.match(ch))


def align(ja, kana):
    """回傳 {漢字連續段: 讀音}，用 ja 與 kana 對齊推出。"""
    out = {}
    ja = unicodedata.normalize('NFKC', to_hira(str(ja or '')))
    kl = list(clean(kana))
    i, j = 0, 0
    n = len(ja)
    while i < n:
        ch = ja[i]
        if not is_kanji(ch):
            k = to_hira(ch)
            if j < len(kl) and kl[j] == k:
                j += 1
            i += 1
            continue
        # 收集連續漢字
        start = i
        while i < n and is_kanji(ja[i]):
            i += 1
        run = ja[start:i]
        # 之後的非漢字（假名）段，作為定位錨
        k2 = i
        while k2 < n and not is_kanji(ja[k2]):
            k2 += 1
        look = clean(ja[i:k2])
        if not look:
            out[run] = ''.join(kl[j:])
            j = len(kl)
            continue
        look_list = list(look)
        pos = None
        for p in range(j, len(kl) - len(look_list) + 1):
            if kl[p:p + len(look_list)] == look_list:
                pos = p
                break
        if pos is not None:
            reading = ''.join(kl[j:pos])
            if reading:
                out[run] = reading
            j = pos
        # 對不上就跳過，不記錯誤讀音
    return out


def collect_pairs():
    pairs = []
    for path in sorted(glob.glob('data/lesson-L*.json')):
        d = json.load(open(path, encoding='utf-8'))
        for pat in d.get('patterns', []):
            for ex in pat.get('ex', []):
                if ex.get('ja') and ex.get('kana'):
                    pairs.append((ex['ja'], ex['kana']))
        for v in d.get('vocab', []):
            if v.get('kanji') and v.get('kana'):
                pairs.append((v['kanji'], v['kana']))
        for dia in d.get('dialogues', []):
            for ln in dia.get('lines', []):
                if ln.get('ja') and ln.get('kana'):
                    pairs.append((ln['ja'], ln['kana']))
        for it in d.get('listening', []):
            if isinstance(it, dict) and it.get('ja') and it.get('kana'):
                pairs.append((it['ja'], it['kana']))
    wt = json.load(open('data/wordtables.json', encoding='utf-8'))
    for g in wt.get('verbs', {}).get('groups', []):
        for it in g.get('items', []):
            if it.get('kanji') and it.get('kana'):
                pairs.append((it['kanji'], it['kana']))
    return pairs


def main():
    pairs = collect_pairs()
    votes = defaultdict(Counter)
    total = 0
    for ja, kana in pairs:
        for k, v in align(ja, kana).items():
            votes[k][v] += 1
            total += 1

    d = {}
    for k, c in votes.items():
        d[k] = c.most_common(1)[0][0]

    # 只保留真的有漢字的鍵，並按長度排序（長詞優先）
    d = {k: v for k, v in d.items() if KANJI.search(k) and v and not KANJI.search(v)}
    out = {'v': 1, 'dict': dict(sorted(d.items(), key=lambda kv: (-len(kv[0]), kv[0])))}
    with open('data/kanji-readings.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print('pairs', len(pairs), 'entries seen', total, 'dict size', len(d))
    for k in ['初', '始', '学生', '会社員', '田中', '今日', '日本語']:
        print(k, '->', d.get(k))


if __name__ == '__main__':
    main()
