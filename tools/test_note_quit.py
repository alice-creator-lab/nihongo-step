#!/usr/bin/env python3
"""驗證練習本：練習中途有「離開練習」，按下即回到練習本列表（可重新開始）。

用法： python3 tools/test_note_quit.py [http://127.0.0.1:8934/]
環境變數：SHOT=/path/x.png 截圖；CDP_PORT 換 port。
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
PORT = int(os.environ.get("CDP_PORT", "9347"))

SEED = {"v": 1, "items": [
    {"id": "L01", "vi": 0, "kanji": "学生", "kana": "がくせい", "zh": "學生", "pos": "名詞", "audio": "", "src": "L01", "at": 3},
    {"id": "L04", "vi": 1, "kanji": "", "kana": "シャツ", "zh": "襯衫", "pos": "名詞", "audio": "", "src": "L04", "at": 2},
    {"id": "L02", "vi": 0, "kanji": "先生", "kana": "せんせい", "zh": "老師", "pos": "名詞", "audio": "", "src": "L02", "at": 1},
]}


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=390,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-notequit-" + str(os.getpid()), "about:blank"],
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
    # --window-size 唔會改頁面 viewport，要 override 才量到 iPhone 闊度
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

    await call("Page.navigate", {"url": BASE + "index.html#/note"}, sid)
    await asyncio.sleep(5)
    await js("localStorage.setItem('ngs-notebook-v1', %s)" % json.dumps(json.dumps(SEED)))
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(25):
        if await js("!!document.querySelector('#nbStart')"):
            break
        await asyncio.sleep(1)

    await js("document.querySelector('#nbStart').click()")
    await asyncio.sleep(0.8)

    check("練習中出現離開練習", await js("!!document.querySelector('#nbQuit')"), True)
    check("離開鈕文字", await js("(document.querySelector('#nbQuit')||{}).innerText||''"), "✕ 離開練習")
    check("仍在第 1 題", await js("((document.querySelector('.cardmeta')||{}).innerText||'').indexOf('第 1 ／ 3 題')>=0"), True)
    # 390px 闊時頁面不應橫向溢出，meta 一行放得落
    check("viewport 390", await js("innerWidth"), 390)
    check("不橫向溢出", await js("document.documentElement.scrollWidth <= innerWidth"), True)
    check("meta 一行", await js("(function(){var e=document.querySelector('.cardmeta');return e?e.getBoundingClientRect().height:0})()"),
          lambda h: 0 < h < 40)
    check("卡片仍在", await js("!!document.querySelector('#fcard')"), True)

    # 上一題 -> 離開，確認回到列表而不是總結頁
    await js("document.querySelector('#fcard').click()")
    await asyncio.sleep(0.2)
    check("看答案後有記得鈕", await js("getComputedStyle(document.querySelector('#know')).display"), "block")
    await js("document.querySelector('#know').click()")
    await asyncio.sleep(0.3)
    check("第 2 題", await js("((document.querySelector('.cardmeta')||{}).innerText||'').indexOf('第 2 ／ 3 題')>=0"), True)

    await js("document.querySelector('#nbQuit').click()")
    await asyncio.sleep(0.6)
    check("離開後回列表", await js("document.querySelectorAll('#notebody .nrow').length"), 3)
    check("列表冇卡面", await js("!!document.querySelector('#fcard')"), False)
    check("開始練習鈕仍在", await js("!!document.querySelector('#nbStart')"), True)
    check("離開後冇除收藏", await js("JSON.parse(localStorage['ngs-notebook-v1']).items.length"), 3)

    # 可再次開始
    await js("document.querySelector('#nbStart').click()")
    await asyncio.sleep(0.6)
    check("可重新開始", await js("!!document.querySelector('#nbQuit')"), True)

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
