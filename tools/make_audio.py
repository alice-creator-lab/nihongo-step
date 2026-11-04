#!/usr/bin/env python3
"""用 edge-tts 為所有課堂的會話與句型例句生成 mp3，並更新 data/audio.json。

用法：
  python3 tools/make_audio.py            # 只補缺檔
  python3 tools/make_audio.py --force    # 全部重生
  python3 tools/make_audio.py L03 L04    # 只做指定課
"""
import json, os, subprocess, sys, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = [("田中", "たなか"), ("鈴木", "すずき"), ("佐藤", "さとう"), ("山田", "やまだ"),
         ("林", "りん"), ("李", "り"), ("王", "おう")]
FEMALE = {"李", "林", "妻", "仲居", "店員"}
MALE = {"王", "田中", "佐藤", "山田", "鈴木", "係員", "店長", "部長"}


def tts_text(t):
    for k, v in NAMES:
        t = t.replace(k, v)
    return t


def voice_for(who):
    return "ja-JP-KeitaNeural" if who in MALE else "ja-JP-NanamiNeural"


def synth(voice, text, out):
    for _ in range(3):
        r = subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", out],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 2000:
            return True
    return False


def main():
    force = "--force" in sys.argv
    only = [a for a in sys.argv[1:] if a.startswith("L")]
    course = json.load(open(os.path.join(ROOT, "data/course.json"), encoding="utf-8"))
    ids = [l["id"] for b in course["books"] for l in b["lessons"] if l.get("available")]
    if only:
        ids = [i for i in ids if i in only]

    os.makedirs(os.path.join(ROOT, "audio"), exist_ok=True)
    manifest_path = os.path.join(ROOT, "data/audio.json")
    manifest = {}
    if os.path.exists(manifest_path) and not force:
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:
            manifest = {}

    jobs = []
    for lid in ids:
        les = json.load(open(os.path.join(ROOT, f"data/lesson-{lid}.json"), encoding="utf-8"))
        m = manifest.setdefault(lid, {})
        for di, dg in enumerate(les.get("dialogues", [])):
            for li, line in enumerate(dg.get("lines", [])):
                key = f"d{di}-l{li}"
                rel = f"audio/{lid}-{key}.mp3"
                m[key] = rel
                jobs.append((voice_for(line.get("who")), tts_text(line["ja"]), os.path.join(ROOT, rel)))
        for vi, v in enumerate(les.get("vocab", [])):
            key = f"v{vi}"
            rel = f"audio/{lid}-{key}.mp3"
            m[key] = rel
            # 單字用假名合成，避免漢字多讀音（例如 一日 ついたち／いちにち）
            jobs.append(("ja-JP-NanamiNeural", v["kana"], os.path.join(ROOT, rel)))
        for pi, pat in enumerate(les.get("patterns", [])):
            for ei, ex in enumerate(pat.get("ex", [])):
                key = f"p{pi}-e{ei}"
                rel = f"audio/{lid}-{key}.mp3"
                m[key] = rel
                jobs.append(("ja-JP-NanamiNeural", tts_text(ex["ja"]), os.path.join(ROOT, rel)))

    todo = [j for j in jobs if force or not (os.path.exists(j[2]) and os.path.getsize(j[2]) > 2000)]
    print(f"共 {len(jobs)} 段，待生成 {len(todo)} 段", flush=True)

    done = 0
    fail = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(synth, v, t, o): o for v, t, o in todo}
        for f in concurrent.futures.as_completed(futs):
            done += 1
            if not f.result():
                fail.append(futs[f])
            if done % 25 == 0:
                print(f"  {done}/{len(todo)}", flush=True)

    manifest["v"] = int(manifest.get("v", 1)) + (1 if force else 0)
    json.dump(manifest, open(manifest_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：成功 {len(todo) - len(fail)}，失敗 {len(fail)}", flush=True)
    for p in fail[:10]:
        print("  失敗:", os.path.basename(p), flush=True)


if __name__ == "__main__":
    main()
