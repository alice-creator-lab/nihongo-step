#!/usr/bin/env python3
"""為 data/sequences.json 的每一項生成 mp3（audio/seq/<組>-<索引>.mp3）。

用法：python3 tools/make_seq_audio.py [--force]
"""
import json, os, subprocess, sys, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE = "ja-JP-NanamiNeural"


def synth(kana, out):
    for _ in range(3):
        r = subprocess.run(["edge-tts", "--voice", VOICE, "--text", kana, "--write-media", out],
                           capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1200:
            return True
    return False


def main():
    force = "--force" in sys.argv
    path = os.path.join(ROOT, "data/sequences.json")
    data = json.load(open(path, encoding="utf-8"))
    os.makedirs(os.path.join(ROOT, "audio/seq"), exist_ok=True)

    jobs = []
    for g in data["groups"]:
        for i, it in enumerate(g["items"]):
            rel = f"audio/seq/{g['id']}-{i}.mp3"
            it["audio"] = rel
            out = os.path.join(ROOT, rel)
            if force or not (os.path.exists(out) and os.path.getsize(out) > 1200):
                jobs.append((it["kana"], out))

    print(f"共 {sum(len(g['items']) for g in data['groups'])} 項，待生成 {len(jobs)} 段", flush=True)
    fail = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for ok in ex.map(lambda j: synth(*j), jobs):
            if not ok:
                fail += 1
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：成功 {len(jobs) - fail}，失敗 {fail}", flush=True)


if __name__ == "__main__":
    main()
