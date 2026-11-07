#!/usr/bin/env python3
"""把課程資料的詞性收斂成固定 8 類，避免同義標籤並存。

原本 20 種寫法（い形容詞／い形、な形容詞／な形／形容動詞、動詞（他動詞）…），
同一個概念多種標籤，搜尋與閱讀都不一致。這裡一次過對照成：

  名詞／動詞／い形容詞／な形容詞／副詞／代名詞／連體詞／其他

「其他」包含寒暄、感嘆、接尾、疑問詞等無法歸入以上七類的少數詞。
詞性的細分（他動詞／自動詞、五段／一段）不再顯示在列表，句型說明內仍會提到。

用法：
  python3 tools/normalize_pos.py          # 顯示統計，不寫檔
  python3 tools/normalize_pos.py --write  # 實際改寫 data/lesson-L*.json
"""
import glob
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALLOWED = ['名詞', '動詞', 'い形容詞', 'な形容詞', '副詞', '代名詞', '連體詞', '其他']

MAP = {
    '名詞': '名詞',
    '名詞・な形': 'な形容詞',        # 心配：可作名詞也可作な形容詞，初級以な形容詞教
    '動詞': '動詞',
    '動詞（他動詞）': '動詞',
    '動詞（自動詞）': '動詞',
    '動詞（一段・他動詞）': '動詞',
    '動詞（五段）': '動詞',
    'い形容詞': 'い形容詞',
    'い形': 'い形容詞',
    '形容詞': 'い形容詞',            # 資料內 7 個「形容詞」全是 い形容詞（さむい、ねむい…）
    'な形容詞': 'な形容詞',
    'な形': 'な形容詞',
    '形容動詞': 'な形容詞',
    '副詞': '副詞',
    '代名詞': '代名詞',
    '連體': '連體詞',
    '接尾': '其他',
    '寒暄': '其他',
    '感嘆': '其他',
    '疑問詞': '其他',
}


def main():
    write = '--write' in sys.argv
    before, after, unknown = Counter(), Counter(), Counter()
    files = 0
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', 'lesson-L*.json'))):
        raw = open(path, encoding='utf-8').read()
        les = json.loads(raw)
        changed = False
        for v in les.get('vocab', []):
            p = (v.get('pos') or '').strip()
            before[p] += 1
            if p not in MAP:
                unknown[p] += 1
                continue
            if v.get('pos') != MAP[p]:
                v['pos'] = MAP[p]
                changed = True
            after[MAP[p]] += 1
        if changed:
            files += 1
            if write:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(les, f, ensure_ascii=False, indent=2)
                    f.write('\n')
    print('原本標籤：', len(before), '種')
    for k, n in before.most_common():
        print(f'  {k:<16}{n:>5}  →  {MAP.get(k, "（未對照，保持原樣）")}')
    print('收斂後：', len(after), '類', dict(after))
    if unknown:
        print('未在對照表內：', dict(unknown))
    print(('已改寫 ' + str(files) + ' 個檔案') if write else '（未寫檔；加 --write 才會改）')


if __name__ == '__main__':
    main()
