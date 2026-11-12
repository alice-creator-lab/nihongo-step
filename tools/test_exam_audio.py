#!/usr/bin/env python3
"""回歸測試：測驗聽解的拼接音檔真的會被播放。

走完整個第 2、3 階段測驗，逐題按「▶ 播放」（有音檔的題目），
用 CDP 的 Network domain 記錄實際請求過的 URL，確認：
  - audio/exam/S2-c2.mp3、S2-c4.mp3、S3-c1.mp3、S3-c3.mp3、S3-c4.mp3 都被請求過
  - 舊的單句音檔（L19-d1-l0、L20-d0-l5、L26-d0-l2、L28-d0-l5、L29-d1-l3）不再被請求

用法： python3 tools/test_exam_audio.py [http://127.0.0.1:8791/]
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = next((c for c in [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
] if os.path.exists(c)), None)
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
PORT = int(os.environ.get("CDP_PORT", "9877"))

WANT = ["audio/exam/S2-c2.mp3", "audio/exam/S2-c4.mp3", "audio/exam/S3-c1.mp3",
        "audio/exam/S3-c3.mp3", "audio/exam/S3-c4.mp3"]
GONE = ["audio/L19-d1-l0.mp3", "audio/L20-d0-l5.mp3", "audio/L26-d0-l2.mp3",
        "audio/L28-d0-l5.mp3", "audio/L29-d1-l3.mp3"]

URLS = []


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             "--autoplay-policy=no-user-gesture-required",
                             f"--remote-debugging-port={PORT}",
                             "--user-data-dir=/tmp/cdp-exaudio-" + str(os.getpid()), "about:blank"],
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
            if m.get("id") == seq[0]:
                return m
            if m.get("method") == "Network.requestWillBeSent":
                URLS.append(m["params"]["request"]["url"])
        return None

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Runtime.enable", {}, sid)
    await call("Network.enable", {}, sid)

    async def js(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True}, sid)
        return r["result"].get("result", {}).get("value") if r else None

    async def wait(expr, secs=25):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v: return v
            await asyncio.sleep(0.25)
        return None

    ok = True
    for stage in (2, 3):
        await call("Page.navigate", {"url": "about:blank"}, sid)
        await asyncio.sleep(0.2)
        await call("Page.navigate", {"url": BASE + "#/exam/%d" % stage}, sid)
        if not await wait("!!document.getElementById('exStart')"):
            print("stage", stage, "未載入"); ok = False; continue
        await js("document.getElementById('exStart').click()")
        if not await wait("!!document.getElementById('exNext')"):
            print("stage", stage, "測驗未開始"); ok = False; continue
        for i in range(28):
            if await js("!!document.getElementById('exPlay')"):
                await js("document.getElementById('exPlay').click()")
                await asyncio.sleep(0.25)
            label = await js("!!document.getElementById('exNext')")
            if not label: break
            await js("document.getElementById('exNext').click()")
            await asyncio.sleep(0.12)

    hit = [w for w in WANT if any(w in u for u in URLS)]
    old = [g for g in GONE if any(g in u for u in URLS)]
    print("請求到的測驗音檔：", hit)
    if old:
        print("仍然請求舊單句：", old); ok = False
    missing = [w for w in WANT if w not in hit]
    if missing:
        print("未請求：", missing); ok = False
    print("\n結果：", "PASS" if ok else "FAIL")
    try: proc.terminate()
    except Exception: pass
    sys.exit(0 if ok else 1)

asyncio.run(main())
