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

  # 商用授權引擎（Azure Speech，需要 AZURE_SPEECH_KEY／AZURE_SPEECH_REGION）
  # 分批換聲：先寫去 audio/m 同 staging manifest，試聽滿意才合併入 data/audio.json
  python3 tools/make_audio.py L01 --engine azure --audio-dir audio/m --manifest data/audio-m.json
"""
import glob, json, os, re, subprocess, sys, concurrent.futures, urllib.request, time

ENGINE = os.environ.get("TTS_ENGINE", "edge").strip().lower()   # edge｜azure
RATE = None          # Azure 專用，例如 "-5%"；edge 引擎沿用預設語速

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from speech import speech  # noqa: E402  朗讀文字：以資料檔假名為準
FEMALE = {"李", "林", "妻", "仲居", "店員"}
MALE = {"王", "田中", "佐藤", "山田", "鈴木", "係員", "店長", "部長"}

# 同場有兩個以上男角時，全部用 Keita 會分不出誰說話。依「角色同時出場」
# 的關係做三色分配，保證同一段會話不會兩個角色同聲：
#   Keita  田中・山田・係員・店長・部長
#   Daichi 王
#   Naoki  佐藤・鈴木
# 女角一律 Mayu；未列出的男角沿用 Keita。
AZURE_VOICE_BY_NAME = {
    "田中": "ja-JP-KeitaNeural",
    "山田": "ja-JP-KeitaNeural",
    "係員": "ja-JP-KeitaNeural",
    "店長": "ja-JP-KeitaNeural",
    "部長": "ja-JP-KeitaNeural",
    "王": "ja-JP-DaichiNeural",
    "佐藤": "ja-JP-NaokiNeural",
    "鈴木": "ja-JP-NaokiNeural",
}


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
    if ENGINE == "azure":
        if who in AZURE_VOICE_BY_NAME:
            return AZURE_VOICE_BY_NAME[who]
        return "ja-JP-KeitaNeural" if who in MALE else "ja-JP-MayuNeural"
    return "ja-JP-KeitaNeural" if who in MALE else "ja-JP-NanamiNeural"


ADIR = None          # --audio-dir：換聲時寫去另一個目錄，唔覆蓋原檔


def audio_rel(manifest_lesson, lid, key):
    """回傳音檔相對路徑。

    manifest 已有記錄就沿用它：個別音檔要換讀音但檔名又不想全部改版時，
    可以直接把檔案改名（例如 L01-g6-e0-2.mp3）並更新 data/audio.json，
    之後重跑此工具也不會把新內容寫回舊檔名。
    """
    if ADIR:
        return f"{ADIR}/{lid}-{key}.mp3"
    return manifest_lesson.get(key) or f"audio/{lid}-{key}.mp3"


def synth_azure(voice, text, out):
    """Azure Speech REST，輸出 24kHz／48kbps CBR，跟現有音檔同格式。"""
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "")
    if not key or not region:
        raise SystemExit("缺 AZURE_SPEECH_KEY／AZURE_SPEECH_REGION")
    open_p = close_p = ""
    if RATE:
        open_p, close_p = '<prosody rate="%s">' % RATE, "</prosody>"
    body = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP">'
            '<voice name="%s">%s%s%s</voice></speak>' % (voice, open_p, text, close_p)).encode("utf-8")
    url = "https://%s.tts.speech.microsoft.com/cognitiveservices/v1" % region
    for attempt in range(4):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "nihongo-step-lesson-audio",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if data and len(data) > 2000:
                tmp = out + ".part"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, out)
                return True
        except Exception as e:        # 429／5xx：退避重試
            print("  azure retry", attempt + 1, str(e)[:60], flush=True)
        time.sleep(1.5 * (attempt + 1))
    return False


EDGE_TO_AZURE = {"ja-JP-NanamiNeural": "ja-JP-MayuNeural",
                 "ja-JP-KeitaNeural": "ja-JP-KeitaNeural"}


def synth(voice, text, out):
    if ENGINE == "azure":
        # 舊工具寫的是 edge 聲名（Nanami），Azure 沒有這把聲，換成 Mayu
        return synth_azure(EDGE_TO_AZURE.get(voice, voice), text, out)
    for _ in range(3):
        r = subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", out],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 2000:
            return True
    return False


def main():
    global ENGINE, RATE, ADIR
    force = "--force" in sys.argv
    force_ex = "--force-ex" in sys.argv
    only = [a for a in sys.argv[1:] if a.startswith("L")]
    opts = {}
    for i, a in enumerate(sys.argv):
        if a in ("--engine", "--rate", "--audio-dir", "--manifest") and i + 1 < len(sys.argv):
            opts[a] = sys.argv[i + 1]
    ENGINE = opts.get("--engine", ENGINE)
    RATE = opts.get("--rate", RATE)
    ADIR = opts.get("--audio-dir", ADIR)
    course = json.load(open(os.path.join(ROOT, "data/course.json"), encoding="utf-8"))
    ids = [l["id"] for b in course["books"] for l in b["lessons"] if l.get("available")]
    if only:
        ids = [i for i in ids if i in only]

    os.makedirs(os.path.join(ROOT, ADIR or "audio"), exist_ok=True)
    manifest_path = os.path.join(ROOT, opts.get("--manifest", "data/audio.json"))
    # 一律先讀回舊 manifest：--force 只代表重生音檔，不代表忘記其他課的索引。
    # （曾經因為 --force 配課號過濾而把整個 manifest 覆蓋成只剩該課。）
    manifest = {}
    if os.path.exists(manifest_path):
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
            jobs.append((voice_for(None), v["kana"], os.path.join(ROOT, rel), False))
        for pi, pat in enumerate(les.get("patterns", [])):
            for ei, ex in enumerate(pat.get("ex", [])):
                key = f"p{pi}-e{ei}"
                rel = audio_rel(m, lid, key)
                m[key] = rel
                jobs.append((voice_for(None), tts_text(ex), os.path.join(ROOT, rel), True))
        for gi, sec in enumerate(les.get("grammar", [])):
            for ei, ex in enumerate(sec.get("ex", [])):
                key = f"g{gi}-e{ei}"
                rel = audio_rel(m, lid, key)
                m[key] = rel
                jobs.append((voice_for(None), tts_text(ex), os.path.join(ROOT, rel), True))
        for li, it in enumerate(les.get("listening", [])):
            key = f"l{li}"
            rel = audio_rel(m, lid, key)
            m[key] = rel
            jobs.append((voice_for(None), tts_text(it), os.path.join(ROOT, rel), True))

    def stale(job):
        if force or (force_ex and job[3]):
            return True
        return not (os.path.exists(job[2]) and os.path.getsize(job[2]) > 2000)

    todo = [j for j in jobs if stale(j)]
    print(f"共 {len(jobs)} 段，待生成 {len(todo)} 段", flush=True)

    done = 0
    fail = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4 if ENGINE == "azure" else 6) as ex:
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
