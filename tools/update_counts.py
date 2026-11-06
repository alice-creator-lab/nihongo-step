#!/usr/bin/env python3
"""重算 course.json 每一階段的單字數與句型數。

數字一律由 data/lesson-*.json 實際內容統計，不要手動填：
之前手填的數字來自外部教材的公布統計，跟本課程實際內容不一致（單字多報近一倍）。

用法：
    python3 tools/update_counts.py          # 重算並寫回 course.json
    python3 tools/update_counts.py --check  # 只檢查，不同步就 exit 1
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
COURSE = ROOT / "data" / "course.json"


def counts(lesson_id: str) -> tuple[int, int]:
    d = json.loads((ROOT / "data" / f"lesson-{lesson_id}.json").read_text(encoding="utf-8"))
    return len(d.get("vocab") or []), len(d.get("patterns") or [])


def main() -> int:
    check = "--check" in sys.argv
    course = json.loads(COURSE.read_text(encoding="utf-8"))
    changed = []
    for book in course["books"]:
        v = p = 0
        for lesson in book["lessons"]:
            lv, lp = counts(lesson["id"])
            v += lv
            p += lp
        if (book.get("vocab"), book.get("patterns")) != (v, p):
            changed.append((book["no"], book.get("vocab"), book.get("patterns"), v, p))
            book["vocab"], book["patterns"] = v, p

    for no, ov, op, nv, np_ in changed:
        print(f"第 {no} 階段：{ov} 單字／{op} 句型 → {nv}／{np_}")

    if not changed:
        print("統計已一致，無需更新。")
        return 0
    if check:
        print("統計與課文不符，請執行 python3 tools/update_counts.py")
        return 1

    COURSE.write_text(
        json.dumps(course, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已寫回 {COURSE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
