#!/usr/bin/env python3
"""驗證順序表新增的「數詞（五）：足・頭・羽」一組：390px 下三欄不換行、變音上色、☆ 可收藏。

用法： python3 tools/test_seq_cnt5.py [http://127.0.0.1:8921/]
環境變數：SHOT=/path/x.png 截圖（只截這一段）；CDP_PORT 換 port。
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8921/"
PORT = int(os.environ.get("CDP_PORT", "9351"))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=390,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-cnt5-" + str(os.getpid()), "about:blank"],
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
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.time()))
            except asyncio.TimeoutError:
                return None
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
        return r["result"].get("result", {}).get("value")

    fails = []

    def check(name, got, want):
        ok = want(got) if callable(want) else got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got))
        if not ok:
            fails.append(name)

    await call("Page.navigate", {"url": BASE + "index.html#/seq"}, sid)
    for _ in range(30):
        if await js("!!document.querySelector('#sgrp-cnt5')"):
            break
        await asyncio.sleep(1)

    S = "document.querySelector('#sgrp-cnt5')"
    check("viewport 390", await js("innerWidth"), 390)
    check("組存在", await js(f"!!{S}"), True)
    check("標題", await js(f"{S}.querySelector('.shead b').innerText"), "數詞（五）：足・頭・羽")
    check("欄頭 3 個", await js(f"{S}.querySelectorAll('.mhead').length"), 3)
    check("欄頭文字", await js(f"[...{S}.querySelectorAll('.mhead .mk')].map(function(e){{return e.innerText}}).join('/')"),
          "何足/何頭/何羽")
    check("30 行", await js(f"{S}.querySelectorAll('.srow').length"), 30)
    check("3 欄", await js(f"{S}.querySelectorAll('.scol').length"), 3)
    check("每欄 10 行", await js(f"[...{S}.querySelectorAll('.scol')].map(function(c){{return c.querySelectorAll('.srow').length}}).join('/')"),
          "10/10/10")
    check("變音上色 8 處", await js(f"{S}.querySelectorAll('.sp').length"), 8)
    check("別讀法 5 處", await js(f"{S}.querySelectorAll('.alt').length"), 5)
    check("每行有喇叭音檔", await js(
        f"[...{S}.querySelectorAll('.srow')].every(function(r){{return /audio\\/seq\\/(soku|tou|wa)-\\d+\\.mp3$/.test(r.getAttribute('data-audio'))}})"), True)
    # 假名不可斷行：用 Range 數不同 top 值（grid 子項 getClientRects 只會回一個）
    check("假名不換行", await js(
        f"[...{S}.querySelectorAll('.sn')].every(function(e){{var r=document.createRange();r.selectNodeContents(e);"
        "var t=[...r.getClientRects()].map(function(x){return Math.round(x.top)});"
        "return new Set(t).size===1})"), True)
    check("不橫向溢出", await js("document.documentElement.scrollWidth <= innerWidth"), True)
    # 喇叭不壓住假名（矩形交集為 0）
    check("喇叭不重疊假名", await js(
        f"[...{S}.querySelectorAll('.srow')].every(function(r){{var n=r.querySelector('.sn').getBoundingClientRect();"
        "var b=r.querySelector('.spk').getBoundingClientRect();"
        "var w=Math.min(n.right,b.right)-Math.max(n.left,b.left);"
        "var h=Math.min(n.bottom,b.bottom)-Math.max(n.top,b.top);return w<=1||h<=1})"), True)

    # ☆ 收藏
    await js("localStorage.removeItem('ngs-notebook-v1')")
    await js(f"{S}.querySelectorAll('.srow')[0].querySelector('.nbk').click()")
    await asyncio.sleep(0.3)
    item = await js("(function(){var d=JSON.parse(localStorage['ngs-notebook-v1']||'{}');"
                    "var it=(d.items||[])[0]||{};return [d.items.length,it.id,it.src,it.kana,it.audio].join('|')})()")
    check("收藏寫入 localStorage", item, "1|SEQ:cnt5|數詞（五）|いっそく|audio/seq/soku-0.mp3")
    check("星號變實心", await js(f"{S}.querySelectorAll('.srow')[0].querySelector('.nbk').innerText"), "★")

    if os.environ.get("SHOT"):
        box = json.loads(await js(
            f"JSON.stringify((function(){{var r={S}.getBoundingClientRect();"
            "return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height}})())"))
        r = await call("Page.captureScreenshot", {"format": "png", "clip": dict(box, scale=2),
                                                 "captureBeyondViewport": True}, sid)
        with open(os.environ["SHOT"], "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
