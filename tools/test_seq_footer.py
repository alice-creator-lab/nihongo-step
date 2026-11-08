#!/usr/bin/env python3
"""驗證順序表頁尾的「回課程地圖」：位於最後一張表之後、可點回地圖、390px 下不擠。

用法： python3 tools/test_seq_footer.py [http://127.0.0.1:8923/]
環境變數：SHOT=/path/x.png 截圖（頁尾附近）；CDP_PORT 換 port。
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不到 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8923/"
PORT = int(os.environ.get("CDP_PORT", "9431"))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=390,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-foot-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def send(method, params, sid=None):
        seq[0] += 1
        mid = seq[0]
        msg = {"id": mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        return mid

    async def wait(mid, timeout=25):
        end = time.time() + timeout
        while time.time() < end:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.time()))
            m = json.loads(raw)
            if m.get("id") == mid:
                return m
        return None

    async def call(method, params=None, sid=None, timeout=25):
        return await wait(await send(method, params, sid), timeout)

    tgt = await call("Target.getTargets")
    tid = [t["targetId"] for t in tgt["result"]["targetInfos"] if t["type"] == "page"][0]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Page.enable", {}, sid)
    await call("Runtime.enable", {}, sid)
    await call("Emulation.setDeviceMetricsOverride",
               {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def js(expr):
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, sid)
        if not r or "result" not in r:
            return None
        res = r["result"]
        if res.get("exceptionDetails"):
            return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description"))[:200]
        return res.get("result", {}).get("value")

    fails = []

    def check(name, got, want):
        ok = want(got) if callable(want) else got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got))
        if not ok:
            fails.append(name)

    await call("Page.navigate", {"url": BASE + "index.html#/seq"}, sid)
    for _ in range(30):
        if await js("!!document.querySelector('#seqhost .seqfoot')"):
            break
        await asyncio.sleep(1)

    check("頁尾存在", await js("!!document.querySelector('#seqhost .seqfoot')"), True)
    check("頁尾是 #seqhost 最後一個元素", await js(
        "document.querySelector('#seqhost').lastElementChild.classList.contains('seqfoot')"), True)
    check("連結文字", await js("document.querySelector('#seqhost .seqfoot a').innerText"), "← 回課程地圖")
    check("連結指向地圖", await js("document.querySelector('#seqhost .seqfoot a').getAttribute('href')"), "#/")
    check("在最後一張表之後", await js(
        "(function(){var f=document.querySelector('#seqhost .seqfoot').getBoundingClientRect();"
        "var last=document.querySelector('#sgrp-cnt5').getBoundingClientRect();"
        "return f.top>=last.bottom})()"), True)
    check("有細線分隔", await js(
        "getComputedStyle(document.querySelector('#seqhost .seqfoot')).borderTopWidth"), "1px")
    check("不橫向溢出", await js("document.documentElement.scrollWidth <= innerWidth"), True)

    # 點擊後回到課程地圖
    await js("document.querySelector('#seqhost .seqfoot a').click()")
    await asyncio.sleep(1.2)
    check("點擊後在地圖", await js("location.hash"), "#/")
    check("地圖有課堂列表", await js("document.querySelectorAll('.book').length > 0"), True)

    if os.environ.get("SHOT"):
        await call("Page.navigate", {"url": BASE + "index.html#/seq"}, sid)
        for _ in range(30):
            if await js("!!document.querySelector('#seqhost .seqfoot')"):
                break
            await asyncio.sleep(1)
        box = json.loads(await js(
            "JSON.stringify((function(){var f=document.querySelector('#seqhost .seqfoot').getBoundingClientRect();"
            "var y=Math.max(0,f.top+scrollY-400);"
            "return {x:0,y:y,width:innerWidth,height:Math.min(560, document.documentElement.scrollHeight-y)}})())"))
        r = await call("Page.captureScreenshot", {"format": "png", "clip": dict(box, scale=2),
                                                 "captureBeyondViewport": True}, sid)
        with open(os.environ["SHOT"], "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
