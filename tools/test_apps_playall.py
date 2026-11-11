#!/usr/bin/env python3
"""驗證「不同形態的應用」可以由中間開始「播放全部」。

檢查：
1. 頁面 67 行，未播時底部停止鍵不出現。
2. 點第 33 行的例句（不是喇叭、不是課號）→ 由第 33 行的音檔開始播，
   浮動停止鍵顯示「33／67」，頁頂按鈕變「■ 停止」，該行有 .playing。
3. 會自動續播到下一行，進度會遞增。
4. 按浮動停止鍵即停：鍵消失、行高亮清空、按鈕還原、之後不再播。
5. 喇叭仍只播單句（不會變成順播、不會亮起停止鍵）。
6. 390／360px 下停止鍵不溢出。

用法： python3 tools/test_apps_playall.py [http://127.0.0.1:8911/]
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8911/"
PORT = int(os.environ.get("CDP_PORT", "9342"))
SHOT = os.environ.get("SHOT", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = json.load(open(os.path.join(ROOT, "data/verbapps.json"), encoding="utf-8"))
TOTAL = sum(len(g["rows"]) for g in DATA["groups"])

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-apall-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    if not ver:
        sys.exit("CDP 起不來")
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(method, params=None, sid=None, timeout=10):
        seq[0] += 1
        msg = {"id": seq[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time())))
            except asyncio.TimeoutError:
                return None
            if m.get("id") == seq[0]:
                return m
        return None

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Runtime.enable", {}, sid)

    async def js(expr, tries=2):
        for _ in range(tries):
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                "awaitPromise": True}, sid, timeout=20)
            if r and "result" in r:
                return r["result"].get("result", {}).get("value")
        return None

    async def viewport(w):
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def wait_until(expr, secs=30):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await asyncio.sleep(0.4)
        return None

    async def shot(name):
        r = await call("Page.captureScreenshot", {"format": "png"}, sid, timeout=25)
        if r and "result" in r:
            open(name, "wb").write(base64.b64decode(r["result"]["data"]))

    fails = []

    def check(ok, label, detail=""):
        if not ok:
            fails.append(f"{label}：{detail}")

    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/all/verbs/apps"}, sid)
    rows = await wait_until("document.querySelectorAll('.aptbl tr.apr').length")
    check(rows == TOTAL, "行數", f"{rows} ≠ {TOTAL}")
    check(await js("!document.getElementById('allstop').classList.contains('on')"), "未播時停止鍵應隱藏")

    # 2) 點第 33 行的例句
    await js(INSTR)
    picked = await js("""(function(){
      var rows = document.querySelectorAll('.aptbl tr.apr');
      var r = rows[32];
      var sp = r.querySelector('.apspk');
      r.querySelector('.apex').click();
      return { pat: r.querySelector('.appat').innerText,
               audio: sp ? sp.getAttribute('data-audio') : null,
               lesson: r.querySelector('.apl').innerText };
    })()""")
    await asyncio.sleep(1.2)
    out = await js("""(function(){
      return { bar: document.getElementById('allstop').classList.contains('on'),
               n: document.getElementById('allstopN').textContent.trim(),
               btn: document.getElementById('applay').textContent.trim(),
               btnOn: document.getElementById('applay').classList.contains('onplay'),
               playing: document.querySelectorAll('.aptbl tr.apr.playing').length,
               first: (window.__played||[])[0] || null };
    })()""")
    out = out or {}
    check(out.get("bar") is True, "點例句後浮動停止鍵應出現", str(out))
    check(out.get("n") == f"33／{TOTAL}", "進度應為 33／共", str(out.get("n")))
    check(out.get("btn") == "■ 停止", "頁頂按鈕應變停止", str(out.get("btn")))
    check(out.get("playing") == 1, "應剛好一行高亮", str(out.get("playing")))
    first = (out.get("first") or "").split("?")[0].split("/")[-1]
    rowfile = (picked["audio"] or "").split("/")[-1]
    check(first == rowfile, "第一段應是所點那一行", f"{first} ≠ {rowfile}")
    if SHOT:
        await shot(SHOT)

    # 3) 自動續播
    n1 = out.get("n")
    await asyncio.sleep(4.5)
    n2 = await js("document.getElementById('allstopN').textContent.trim()")
    check(n2 != n1, "應自動續播下一句", f"{n1} → {n2}")

    # 4) 按浮動鍵即停
    await js("document.getElementById('allstop').click()")
    await asyncio.sleep(0.5)
    st = await js("""(function(){
      return { bar: document.getElementById('allstop').classList.contains('on'),
               rows: document.querySelectorAll('.aptbl tr.apr.playing').length,
               still: !!(window.__cur && !window.__cur.paused),
               btn: document.getElementById('applay').textContent.trim() };
    })()""") or {}
    check(not st.get("bar") and st.get("rows") == 0 and not st.get("still")
          and st.get("btn") == "▶ 播放全部", "按浮動鍵應完全停下", str(st))
    n_after = await js("window.__played.length")
    await asyncio.sleep(2.0)
    check(await js("window.__played.length") == n_after, "停後不應再播")

    # 5) 喇叭仍只播單句
    await js("window.__played = []; window.__cur = null")
    await js("document.querySelectorAll('.aptbl tr.apr')[10].querySelector('.apspk').click()")
    await asyncio.sleep(0.8)
    sp = await js("""(function(){
      return { bar: document.getElementById('allstop').classList.contains('on'),
               n: (window.__played||[]).length,
               first: (window.__played||[])[0] || null,
               want: document.querySelectorAll('.aptbl tr.apr')[10].querySelector('.apspk').getAttribute('data-audio'),
               btn: document.getElementById('applay').textContent.trim() };
    })()""") or {}
    check(not sp.get("bar"), "喇叭不應觸發順播", str(sp))
    check((sp.get("first") or "").split("?")[0].split("/")[-1] == (sp.get("want") or "").split("/")[-1],
          "喇叭應播該行音檔", str(sp))
    check(sp.get("btn") == "▶ 播放全部", "喇叭不應改頁頂按鈕", str(sp))
    await js("if (window.__cur) { window.__cur.pause(); }")

    # 6) 360px 停止鍵不溢出
    await viewport(360)
    await call("Page.navigate", {"url": BASE + "#/all/verbs/apps"}, sid)
    await wait_until("document.querySelectorAll('.aptbl tr.apr').length")
    await js(INSTR)
    await js("document.querySelectorAll('.aptbl tr.apr')[40].querySelector('.apex').click()")
    await asyncio.sleep(0.9)
    box = await js("""(function(){var b=document.getElementById('allstop').getBoundingClientRect();
      return {on: document.getElementById('allstop').classList.contains('on'),
              l: Math.round(b.left), r: Math.round(b.right),
              iw: window.innerWidth, sw: document.documentElement.scrollWidth,
              n: document.getElementById('allstopN').textContent.trim()};})()""") or {}
    check(box.get("on") and box.get("l", -1) >= 0 and box.get("r", 9e9) <= box.get("iw", 0)
          and box.get("sw", 9e9) <= box.get("iw", 0) + 1, "360px 停止鍵溢出", str(box))
    check(box.get("n") == f"41／{TOTAL}", "360px 進度應為 41／共", str(box.get("n")))
    await js("document.getElementById('allstop').click()")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
    else:
        print(f"全部通過：由第 33 行起播、進度 33／{TOTAL}、自動續播、即停、喇叭單句、360px 無溢出")
    proc.terminate()
    await ws.close()
    sys.exit(1 if fails else 0)


asyncio.run(main())
