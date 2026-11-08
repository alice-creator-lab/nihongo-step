#!/usr/bin/env python3
"""驗證練習本：日→中／中→日 選擇器（切換後卡片題目方向跟住變）。

用法： python3 tools/test_note_dir.py [http://127.0.0.1:8934/]
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
PORT = int(os.environ.get("CDP_PORT", "9346"))

SEED = {"v": 1, "items": [
    {"id": "L01", "vi": 0, "kanji": "学生", "kana": "がくせい", "zh": "學生", "pos": "名詞", "audio": "", "src": "L01", "at": 3},
    {"id": "L04", "vi": 1, "kanji": "", "kana": "シャツ", "zh": "襯衫", "pos": "名詞", "audio": "", "src": "L04", "at": 2},
]}


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=430,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-notedir-" + str(os.getpid()), "about:blank"],
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
        ok = want(got) if callable(want) else got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got))
        if not ok:
            fails.append(name)

    await call("Page.navigate", {"url": BASE + "index.html#/note"}, sid)
    await asyncio.sleep(5)
    await js("localStorage.setItem('ngs-notebook-v1', %s)" % json.dumps(json.dumps(SEED)))
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(25):
        if await js("!!document.querySelector('#noteDir')"):
            break
        await asyncio.sleep(1)

    check("方向鈕兩個", await js("document.querySelectorAll('#noteDir button').length"), 2)
    check("預設選中日→中", await js("(document.querySelector('#noteDir button.on')||{}).innerText||''"), "日→中")

    await js("document.querySelectorAll('#noteDir button')[1].click()")
    await asyncio.sleep(0.3)
    check("切換後選中", await js("(document.querySelector('#noteDir button.on')||{}).innerText||''"), "中→日")

    await js("document.querySelector('#nbStart').click()")
    await asyncio.sleep(0.8)
    check("卡面標示方向", await js("((document.querySelector('.cardmeta')||{}).innerText||'').indexOf('中→日')>=0"), True)
    check("題目出中文", await js("(document.querySelector('.fq')||{}).innerText||''") ,
          lambda s: s in ("學生", "襯衫"))

    # 回練習本再切回日→中，確認兩個方向都出得正確
    await js("location.hash='#/'; 1")
    await asyncio.sleep(0.5)
    await js("location.hash='#/note'; 1")
    await asyncio.sleep(1)
    check("重入後仍記住中→日", await js("(document.querySelector('#noteDir button.on')||{}).innerText||''"), "中→日")
    await js("document.querySelectorAll('#noteDir button')[0].click()")
    await js("document.querySelector('#nbStart').click()")
    await asyncio.sleep(0.8)
    check("日→中 卡面標示", await js("((document.querySelector('.cardmeta')||{}).innerText||'').indexOf('日→中')>=0"), True)
    check("題目出日文", await js("(document.querySelector('.fq')||{}).innerText||''"),
          lambda s: s in ("学生", "シャツ"))

    if os.environ.get("SHOT"):
        import base64
        r = await call("Page.captureScreenshot", {"format": "png"}, sid)
        with open(os.environ["SHOT"], "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
