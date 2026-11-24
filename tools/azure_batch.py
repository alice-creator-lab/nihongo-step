#!/usr/bin/env python3
"""把指定課堂的發音批次改用 Azure，並合併入 data/audio.json。

流程：
  1. 掃該課所有句子，若假名合成會出現「わは／はわ」這類黏連（例如 母は → ははわ），
     就為該項寫入 "tts" 覆寫（直接用漢字原句），避免引擎讀錯母音。
  2. 呼叫 make_audio.py --engine azure --audio-dir audio/m --manifest data/audio-m.json
  3. 把 audio/m 的路徑合併入 data/audio.json，並把 v 加一（單字音檔版本）。
  4. 逐項核對：檔案存在、大小、時長與舊檔差距。

用法：python3 tools/azure_batch.py L06 L07 L08 L09 L10
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from speech import speech  # noqa: E402
FFPROBE = "/home/admin/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffprobe"
RISK = ("はわ", "わわ")   # 母は→ははわ 這類；「わは」屬正常（学校は八時），不當作風險


def items_of(les):
    """(section, index, sub index, item, key)"""
    out = []
    for vi, v in enumerate(les.get("vocab", [])):
        out.append(("vocab", vi, None, v, f"v{vi}"))
    for pi, p in enumerate(les.get("patterns", [])):
        for ei, ex in enumerate(p.get("ex", [])):
            out.append(("patterns", pi, ei, ex, f"p{pi}-e{ei}"))
    for gi, g in enumerate(les.get("grammar", [])):
        for ei, ex in enumerate(g.get("ex", [])):
            out.append(("grammar", gi, ei, ex, f"g{gi}-e{ei}"))
    for di, dg in enumerate(les.get("dialogues", [])):
        for li, ln in enumerate(dg.get("lines", [])):
            out.append(("dialogues", di, li, ln, f"d{di}-l{li}"))
    for li, it in enumerate(les.get("listening", [])):
        out.append(("listening", li, None, it, f"l{li}"))
    return out


def dur(p):
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def main():
    lides = [a for a in sys.argv[1:] if a.startswith("L")]
    if not lides:
        raise SystemExit("要指定課號，例如 L06 L07")
    overrides = 0
    for lid in lides:
        path = os.path.join(ROOT, f"data/lesson-{lid}.json")
        les = json.load(open(path, encoding="utf-8"))
        changed = False
        for sec, i, j, item, key in items_of(les):
            if not isinstance(item, dict) or item.get("tts"):
                continue
            ja, kana = item.get("ja") or "", item.get("kana") or ""
            if not kana:
                continue
            txt = speech(ja, kana)[0]
            if any(s in txt for s in RISK):
                item["tts"] = ja
                changed = True
                overrides += 1
        if changed:
            json.dump(les, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"漢字覆寫 {overrides} 項", flush=True)

    env = dict(os.environ)
    r = subprocess.run([sys.executable, "tools/make_audio.py", *lides, "--engine", "azure",
                        "--audio-dir", "audio/m", "--manifest", "data/audio-m.json"],
                       cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit("make_audio 失敗")

    main_m = json.load(open(os.path.join(ROOT, "data/audio.json"), encoding="utf-8"))
    stg = json.load(open(os.path.join(ROOT, "data/audio-m.json"), encoding="utf-8"))
    merged = 0
    biggest = (0.0, "")
    for lid in lides:
        for k, rel in stg[lid].items():
            old = main_m[lid].get(k)
            if old and os.path.exists(os.path.join(ROOT, old)) and os.path.exists(os.path.join(ROOT, rel)):
                d = dur(os.path.join(ROOT, rel)) - dur(os.path.join(ROOT, old))
                if abs(d) > abs(biggest[0]):
                    biggest = (d, f"{lid}-{k}")
            main_m[lid][k] = rel
            merged += 1
    main_m["v"] = int(main_m.get("v", 18)) + 1
    json.dump(main_m, open(os.path.join(ROOT, "data/audio.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    missing = [f"{lid}-{k}" for lid in lides for k, rel in stg[lid].items()
               if not os.path.exists(os.path.join(ROOT, rel))]
    print(f"合併 {merged} 段；v={main_m['v']}；缺失 {len(missing)}；最大時長差 {biggest[0]:+.2f}s {biggest[1]}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
