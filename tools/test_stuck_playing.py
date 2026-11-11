#!/usr/bin/env python3
"""回歸測試：連續按不同喇叭，舊的一顆不可以留在「播放中」黑色狀態。

重現方法：把 HTMLMediaElement.play 換成「永遠不會 ended」的假播放，
連按三個喇叭。舊版本 playFile 只 pause 上一段、沒有清掉上一顆的
.playing，於是每按一次就多一顆長著黑色。

用法： python3 tools/test_stuck_playing.py [http://127.0.0.1:8791/]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
PORT = int(os.environ.get("CDP_PORT", "9347"))

STUB = ("(function(){"
        "window.__n=0;"
        "var p=HTMLMediaElement.prototype.play;"
        "HTMLMediaElement.prototype.play=function(){window.__cur=this;window.__n++;"
        "return Promise.resolve();};"
        "return 1;})()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}",
         "--user-data-dir=/tmp/cdp-stuck-" + str(os.getpid()), "about:blank"],
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

    async def call(method, params=None, sid=None, timeout=15):
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

    async def wait_until(expr, secs=30):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await asyncio.sleep(0.3)
        return None

    await call("Emulation.setDeviceMetricsOverride",
               {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)
    await call("Page.navigate", {"url": BASE + "#/all/vocab"}, sid)
    n = await wait_until("document.querySelectorAll('#alllist .arow .spk').length")
    if not n or n < 4:
        sys.exit("詞語總表沒有足夠喇叭：%r" % n)
    await js(STUB)
    print("版本", await js("document.getElementById('verTag').textContent.trim()"), "喇叭", n)

    async def click(i):
        await js("document.querySelectorAll('#alllist .arow .spk')[%d].click()" % i)
        await asyncio.sleep(0.15)
        return await js("document.querySelectorAll('.spk.playing').length")

    c1 = await click(0)
    c2 = await click(1)
    c3 = await click(2)
    print("連按三顆後 .spk.playing 數量：", c1, c2, c3, "（應為 1, 1, 1）")

    # 離開頁面即停：全部高亮要清乾淨
    await js("location.hash='#/'")
    await asyncio.sleep(0.6)
    left = await js("document.querySelectorAll('.playing').length")
    print("離開頁面後殘留 .playing：", left, "（應為 0）")

    ok = (c1 == 1 and c2 == 1 and c3 == 1 and left == 0)
    print("結果：", "PASS" if ok else "FAIL")
    try:
        proc.terminate()
    except Exception:
        pass
    sys.exit(0 if ok else 1)


asyncio.run(main())
