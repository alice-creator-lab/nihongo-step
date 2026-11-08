#!/usr/bin/env python3
"""驗證錯題簿：同一題（不同來源 key）只出現一次、不顯示 ×N。

用法： python3 tools/test_mistakes_dedupe.py [http://127.0.0.1:8934/]
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
PORT = int(os.environ.get("CDP_PORT", "9344"))

SEED = {
    "v": 1,
    "items": [
        {"key": "L04:w:シャツ", "kind": "word", "prompt": "シャツ", "answer": "襯衫", "sub": "シャツ", "at": 1, "n": 3},
        {"key": "ex1:12", "kind": "exam", "prompt": "シャツ", "answer": "襯衫", "at": 2, "n": 2},
        {"key": "L04:l:1", "kind": "listen", "prompt": "シャツ", "answer": "襯衫", "at": 3, "n": 1},
        {"key": "L04:w:くつ", "kind": "word", "prompt": "くつ", "answer": "鞋子", "sub": "くつ", "at": 4, "n": 1},
    ],
}


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=430,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-mk-" + str(os.getpid()), "about:blank"],
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
    pending = {}

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

    URL = BASE + "index.html#/"
    await call("Page.navigate", {"url": URL}, sid)
    await asyncio.sleep(5)
    print("seed:", await js("(function(){localStorage.setItem('ngs-mistakes-v1', %s); return localStorage.getItem('ngs-mistakes-v1').length;})()" % json.dumps(json.dumps(SEED))))
    await call("Page.reload", {"ignoreCache": True}, sid)
    await asyncio.sleep(6)
    print("loaded:", await js("(localStorage.getItem('ngs-mistakes-v1')||'').length"))
    for _ in range(20):
        if await js("!!document.querySelector('#mkBtn')"):
            break
        await asyncio.sleep(1)
    print("pill text:", await js("(document.querySelector('#mkBtn')||{}).innerText||''"))
    got = await js("(function(){var b=document.querySelector('#mkBtn'); if(!b) return 'no-pill'; b.click(); return 'clicked';})()")
    print("pill click:", got)
    await asyncio.sleep(1)
    text = await js("(document.querySelector('#sheetbox')||{}).innerText||''")
    rows = await js("document.querySelectorAll('#sheetbox .mk').length")
    pill = await js("(document.querySelector('#mkBtn b')||{}).innerText||''")
    print("pill:", pill, "| rows:", rows)
    print(text)
    print("RESULT", "PASS" if (rows == 2 and "×" not in (text or "")) else "FAIL")
    await ws.close()
    proc.terminate()


asyncio.run(main())
