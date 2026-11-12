#!/usr/bin/env python3
"""回歸測試：階段測驗的「離開測驗」要好按。

量的是可點範圍，不是文字大小：
  - 觸控高度 ≥ 44px、寬度 ≥ 88px（iPhone 手指最小建議值）
  - 不可以被 sticky header 蓋住（rect.top ≥ header 底）
  - 390 / 360 兩個寬度都要過
  - 按下去真的離開測驗（hash 回到 #/exam/N）

用法： python3 tools/test_exam_quit.py [http://127.0.0.1:8791/]
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = next((c for c in [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
] if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
PORT = int(os.environ.get("CDP_PORT", "9861"))


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             "--autoplay-policy=no-user-gesture-required",
                             f"--remote-debugging-port={PORT}",
                             "--user-data-dir=/tmp/cdp-exquit-" + str(os.getpid()), "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version")); break
        except Exception:
            time.sleep(0.3)
    if not ver:
        sys.exit("CDP 起不來")
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(method, params=None, sid=None, timeout=20):
        seq[0] += 1
        msg = {"id": seq[0], "method": method, "params": params or {}}
        if sid: msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time())))
            except asyncio.TimeoutError:
                return None
            if m.get("id") == seq[0]: return m
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

    async def wait_until(expr, secs=30):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v: return v
            await asyncio.sleep(0.3)
        return None

    ok = True
    for w in (390, 360):
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)
        await call("Page.navigate", {"url": "about:blank"}, sid)
        await asyncio.sleep(0.2)
        await call("Page.navigate", {"url": BASE + "#/exam/1"}, sid)
        if not await wait_until("!!document.getElementById('exStart')"):
            print(w, "找不到開始測驗"); ok = False; continue
        await js("document.getElementById('exStart').click()")
        if not await wait_until("!!document.getElementById('exQuit')"):
            print(w, "找不到離開測驗"); ok = False; continue
        m = await js("""(function(){
          var b=document.getElementById('exQuit'), h=document.querySelector('.hdr');
          var r=b.getBoundingClientRect(), hr=h.getBoundingClientRect();
          return {w:Math.round(r.width), h:Math.round(r.height), top:Math.round(r.top),
                  hdrBottom:Math.round(hr.bottom), left:Math.round(r.left)};
        })()""")
        print(w, m)
        if not (m and m["h"] >= 44 and m["w"] >= 88 and m["top"] >= m["hdrBottom"] - 1):
            ok = False
        # 按下去要真的離開
        await js("document.getElementById('exQuit').click()")
        await asyncio.sleep(0.5)
        h = await js("location.hash")
        back = await js("!!document.getElementById('exStart')")
        print("  按後 hash:", h, "· 回到說明頁:", back)
        if not ((h or "").startswith("#/exam/") and back):
            ok = False

    print("\n結果：", "PASS" if ok else "FAIL")
    try: proc.terminate()
    except Exception: pass
    sys.exit(0 if ok else 1)

asyncio.run(main())
