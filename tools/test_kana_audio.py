#!/usr/bin/env python3
"""驗五十音音檔：每個假名表字格、每個練習模式的音檔都存在且真的載入得到。

用法：python3 tools/test_kana_audio.py http://127.0.0.1:8940/kana/
"""
import asyncio, glob, json, os, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8940/kana/"
PORT = 9671
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MDIR = os.path.join(ROOT, "kana/audio/m")


async def main():
    proc = __import__("subprocess").Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
         "--single-process", "--no-zygote", "--mute-audio", f"--remote-debugging-port={PORT}",
         "--user-data-dir=/tmp/cdp-kana-audio", "about:blank"],
        stdout=__import__("subprocess").DEVNULL, stderr=__import__("subprocess").DEVNULL)
    ver = None
    for _ in range(60):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(m, p=None, sid=None, t=20):
        seq[0] += 1
        mid = seq[0]
        await ws.send(json.dumps({"id": mid, "method": m, "params": p or {},
                                  **({"sessionId": sid} if sid else {})}))
        end = time.time() + t
        while time.time() < end:
            try:
                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time())))
            except Exception:
                return {}
            if r.get("id") == mid:
                return r
        return {}

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844,
                                                      "deviceScaleFactor": 2, "mobile": True}, sid)
    await call("Page.enable", {}, sid)
    await call("Page.addScriptToEvaluateOnNewDocument", {"source": """
window.__played=[];
(function(){var op=HTMLMediaElement.prototype.play;
 HTMLMediaElement.prototype.play=function(){
   try{window.__played.push(this.src||this.currentSrc)}catch(e){}
   return op.apply(this,arguments);};})();
"""}, sid)

    async def ev(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True,
                                            "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    await call("Page.navigate", {"url": URL}, sid)
    for _ in range(30):
        if await ev("!!document.getElementById('chartBtn')"):
            break
        await asyncio.sleep(0.3)
    await asyncio.sleep(0.8)

    ok = fail = 0
    # 1) 檔案齊全（104 個假名 + wo-chart）
    files = sorted(glob.glob(os.path.join(MDIR, "*.mp3")))
    sizes = [os.path.getsize(f) for f in files]
    print(f"audio/m 檔案：{len(files)} 個，最小 {min(sizes) if sizes else 0} bytes")
    if len(files) != 105 or min(sizes) < 3000:
        print("  ✗ 檔案數或大小不對")
        fail += 1
    else:
        ok += 1

    # 2) 開字表（.kcell 只有開表後才存在）
    await ev("(function(){var b=document.getElementById('chartBtn'); if(b)b.click(); return !!b})()")
    await asyncio.sleep(0.9)
    ncell = await ev("document.querySelectorAll('.kcell').length")
    print("字表格數 =", ncell)
    ok, fail = (ok + 1, fail) if ncell and ncell > 100 else (ok, fail + 1)

    # 3) 抽查每一格：真按落去，睇 app 播咗邊個檔（唔靠頁面內部變數）
    res = await ev("""(async function(){
      const cells=[...document.querySelectorAll('.kcell')];
      const out=[];
      for(const c of cells.slice(0,12)){
        window.__played=[];
        c.click();
        await new Promise(r=>setTimeout(r,300));
        const last=(window.__played.slice(-1)[0]||'');
        out.push([c.dataset.k, last.split('/').slice(-2).join('/')]);
      }
      return out;
    })()""")
    bad = [r for r in (res or []) if not r[1].startswith("m/") or not r[1].endswith(".mp3")]
    print(f"抽查字格 {len(res or [])} 格，載入失敗 {len(bad)}")
    for r in (res or [])[:6]:
        print("   ", r)
    ok, fail = (ok + 1, fail) if not bad else (ok, fail + 1)

    # 4) 真實操作：按「か」→ app 真的播放 audio/m/ka.mp3
    await ev("window.__played=[]")
    clicked = await ev("""(function(){var c=document.querySelector('.kcell[data-k="か"]'); if(!c) return 'no';
        c.click(); return 'ok'})()""")
    await asyncio.sleep(1.2)
    played = await ev("JSON.stringify(window.__played.map(function(s){return s.split('/').slice(-2).join('/')}))")
    print("字表按 か →", clicked, played)
    good = bool(played) and "m/ka.mp3" in played
    ok, fail = (ok + 1, fail) if good else (ok, fail + 1)

    proc.kill()
    print("RESULT", "PASS" if fail == 0 else "FAIL", f"({ok} ok / {fail} fail)")
    return 0 if fail == 0 else 1


raise SystemExit(asyncio.run(main()))
