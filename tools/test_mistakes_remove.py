#!/usr/bin/env python3
"""驗證錯題簿：勾選後可逐項移除（單行勾選、按鈕計數、移除後 localStorage 同步）。

用法： python3 tools/test_mistakes_remove.py [http://127.0.0.1:8934/]
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8934/"
PORT = int(os.environ.get("CDP_PORT", "9345"))

SEED = {
    "v": 1,
    "items": [
        {"key": "L04:w:シャツ", "kind": "word", "prompt": "シャツ", "answer": "襯衫", "sub": "シャツ", "at": 3, "n": 1},
        {"key": "ex1:12", "kind": "exam", "prompt": "くつ", "answer": "鞋子", "at": 2, "n": 1},
        {"key": "L04:l:1", "kind": "listen", "prompt": "あめ", "answer": "雨", "at": 1, "n": 1},
    ],
}


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=430,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-mkrm-" + str(os.getpid()), "about:blank"],
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

    async def js(expr):
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, sid)
        if not r or "result" not in r:
            return None
        return r["result"].get("result", {}).get("value")

    fails = []

    def check(name, got, want):
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got) + (" (want " + repr(want) + ")" if not ok else ""))
        if not ok:
            fails.append(name)

    URL = BASE + "index.html#/"
    await call("Page.navigate", {"url": URL}, sid)
    await asyncio.sleep(5)
    await js("localStorage.setItem('ngs-mistakes-v1', %s)" % json.dumps(json.dumps(SEED)))
    await call("Page.reload", {"ignoreCache": True}, sid)
    await asyncio.sleep(6)
    for _ in range(25):
        if await js("!!document.querySelector('#mkBtn')"):
            break
        await asyncio.sleep(1)

    check("pill 初始", await js("((document.querySelector('#mkBtn')||{}).innerText||'').replace(/\\s+/g,' ')"), "錯題簿 3")
    await js("document.querySelector('#mkBtn').click()")
    await asyncio.sleep(0.8)
    check("開啟後行數", await js("document.querySelectorAll('#sheetbox .mk').length"), 3)
    check("每行都有勾選框", await js("document.querySelectorAll('#sheetbox .mk .tick').length"), 3)
    check("按鈕初始 disabled", await js("document.querySelector('#sheetDel').disabled"), True)

    await js("document.querySelectorAll('#sheetbox .mk')[0].click()")
    await js("document.querySelectorAll('#sheetbox .mk')[2].click()")
    await asyncio.sleep(0.3)
    check("勾選 2 行", await js("document.querySelectorAll('#sheetbox .mk.sel').length"), 2)
    check("按鈕文字", await js("document.querySelector('#sheetDel').innerText"), "移除已選 2 項")
    check("按鈕已啟用", await js("document.querySelector('#sheetDel').disabled"), False)

    if os.environ.get("SHOT"):
        import base64
        r = await call("Page.captureScreenshot", {"format": "png"}, sid)
        with open(os.environ["SHOT"], "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    await js("document.querySelector('#sheetDel').click()")
    await asyncio.sleep(0.8)
    check("移除後行數", await js("document.querySelectorAll('#sheetbox .mk').length"), 1)
    check("剩下的是未勾選那題", await js("(document.querySelector('#sheetbox .mk b')||{}).innerText||''"), "くつ")
    check("localStorage 剩 1 條", await js("JSON.parse(localStorage.getItem('ngs-mistakes-v1')).items.length"), 1)
    check("重繪後無殘留勾選", await js("document.querySelectorAll('#sheetbox .mk.sel').length"), 0)
    check("sheet 仍開著", await js("document.querySelector('#sheet').classList.contains('on')"), True)

    await js("document.querySelector('#sheetbox .mk').click()")
    await asyncio.sleep(0.2)
    await js("document.querySelector('#sheetDel').click()")
    await asyncio.sleep(0.8)
    check("全部移除後 items 為 0", await js("JSON.parse(localStorage.getItem('ngs-mistakes-v1')).items.length"), 0)
    check("sheet 已關閉", await js("document.querySelector('#sheet').classList.contains('on')"), False)
    check("首頁徽章消失", await js("!!document.querySelector('#mkBtn')"), False)

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
