#!/usr/bin/env python3
"""用 edge-tts 為所有課堂的會話與句型例句生成 mp3，並更新 data/audio.json。

發音一律用資料裡的 kana 欄位合成，不把漢字交給 TTS 猜讀音：
「町」「一日」「間」這類字預設讀法不一定跟單字表一致（町 ちょう／まち），
用假名合成才能保證例句跟單字表教的是同一個讀音。
kana 缺失時才退回原句（ja）。

用法：
  python3 tools/make_audio.py                 # 只補缺檔
  python3 tools/make_audio.py --force         # 全部重生
  python3 tools/make_audio.py --force-ex      # 只重生句子（會話／句型／文法／聽力），單字不動
  python3 tools/make_audio.py L03 L04         # 只做指定課
"""
import glob, json, os, re, subprocess, sys, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from speech import speech  # noqa: E402  朗讀文字：以資料檔假名為準
FEMALE = {"李", "林", "妻", "仲居", "店員"}
MALE = {"王", "田中", "佐藤", "山田", "鈴木", "係員", "店長", "部長"}


def tts_text(item):
    """朗讀文字：用資料檔假名，並把助詞 は／へ／を 寫成 わ／え／お。

    純假名但保留「は」會被 edge-tts 讀成 ha（實測），所以一定要改寫。
    沒有 kana 才退回原句。

    資料項可加 "tts" 覆寫朗讀文字（畫面仍顯示 ja／kana）：
    漢字句與假名句無法對齊時（例如原句寫阿拉伯數字），speech() 會整句退回
    ja，數字與連字號就交給 edge-tts 自己猜。要指定讀法時直接寫 "tts"。
    """
    if isinstance(item, dict):
        if item.get("tts"):
            return item["tts"]
        ja = item.get("ja") or ""
        kana = item.get("kana") or ""
        if kana:
            return speech(ja, kana)[0]
        return ja
    return item or ""


def voice_for(who):
    return "ja-JP-KeitaNeural" if who in MALE else "ja-JP-NanamiNeural"


def audio_rel(manifest_lesson, lid, key):
    """回傳音檔相對路徑。

    manifest 已有記錄就沿用它：個別音檔要換讀音但檔名又不想全部改版時，
    可以直接把檔案改名（例如 L01-g6-e0-2.mp3）並更新 data/audio.json，
    之後重跑此工具也不會把新內容寫回舊檔名。
    """
    return manifest_lesson.get(key) or f"audio/{lid}-{key}.mp3"


def synth(voice, text, out):
    for _ in range(3):
        r = subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", out],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 2000:
            return True
    return False


def main():
    force = "--force" in sys.argv
    force_ex = "--force-ex" in sys.argv
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

    jobs = []          # (voice, text, out, 是否句子)
    for lid in ids:
        les = json.load(open(os.path.join(ROOT, f"data/lesson-{lid}.json"), encoding="utf-8"))
        m = manifest.setdefault(lid, {})
        for di, dg in enumerate(les.get("dialogues", [])):
            for li, line in enumerate(dg.get("lines", [])):
                key = f"d{di}-l{li}"
                rel = audio_rel(m, lid, key)
                m[key] = rel
                jobs.append((voice_for(line.get("who")), tts_text(line), os.path.join(ROOT, rel), True))
        for vi, v in enumerate(les.get("vocab", [])):
            key = f"v{vi}"
            rel = audio_rel(m, lid, key)
            m[key] = rel
            # 單字本來就用假名合成，避免漢字多讀音（例如 一日 ついたち／いちにち）
            jobs.append(("ja-JP-NanamiNeural", v["kana"], os.path.join(ROOT, rel), False))
        for pi, pat in enumerate(les.get("patterns", [])):
            for ei, ex in enumerate(pat.get("ex", [])):
                key = f"p{pi}-e{ei}"
                rel = audio_rel(m, lid, key)
                m[key] = rel
                jobs.append(("ja-JP-NanamiNeural", tts_text(ex), os.path.join(ROOT, rel), True))
        for gi, sec in enumerate(les.get("grammar", [])):
            for ei, ex in enumerate(sec.get("ex", [])):
                key = f"g{gi}-e{ei}"
                rel = audio_rel(m, lid, key)
                m[key] = rel
                jobs.append(("ja-JP-NanamiNeural", tts_text(ex), os.path.join(ROOT, rel), True))
        for li, it in enumerate(les.get("listening", [])):
            key = f"l{li}"
            rel = audio_rel(m, lid, key)
            m[key] = rel
            jobs.append(("ja-JP-NanamiNeural", tts_text(it), os.path.join(ROOT, rel), True))

    def stale(job):
        if force or (force_ex and job[3]):
            return True
        return not (os.path.exists(job[2]) and os.path.getsize(job[2]) > 2000)

    todo = [j for j in jobs if stale(j)]
    print(f"共 {len(jobs)} 段，待生成 {len(todo)} 段", flush=True)

    done = 0
    fail = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(synth, v, t, o): o for v, t, o, _ in todo}
        for f in concurrent.futures.as_completed(futs):
            done += 1
            if not f.result():
                fail.append(futs[f])
            if done % 25 == 0:
                print(f"  {done}/{len(todo)}", flush=True)

    manifest["v"] = int(manifest.get("v", 1)) + (1 if (force or force_ex) else 0)
    json.dump(manifest, open(manifest_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"完成：成功 {len(todo) - len(fail)}，失敗 {len(fail)}", flush=True)
    for p in fail[:10]:
        print("  失敗:", os.path.basename(p), flush=True)


if __name__ == "__main__":
    main()
