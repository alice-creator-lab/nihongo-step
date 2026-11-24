#!/usr/bin/env python3
"""開一個頁面，按「播放全部」，記錄實際播放的頭幾條 URL（驗版本號／音檔）。"""
import asyncio, glob, json, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
URL = sys.argv[1]
PORT = 9689


async def main():
    import subprocess
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             "--disable-dev-shm-usage", "--single-process", "--no-zygote",
                             "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                             f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-smoke",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version")); break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(m, p=None, sid=None, t=20):
        seq[0] += 1; mid = seq[0]
        await ws.send(json.dumps({"id": mid, "method": m, "params": p or {},
                                  **({"sessionId": sid} if sid else {})}))
        end = time.time() + t
        while time.time() < end:
            try:
                r = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time())))
            except Exception:
                return {}
            if r.get("id") == mid:
                return r
        return {}

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844,
                                                      "deviceScaleFactor": 2, "mobile": True}, sid)
    await call("Page.enable", {}, sid)
    await call("Page.addScriptToEvaluateOnNewDocument", {"source": """
window.__played=[];
(function(){var op=HTMLMediaElement.prototype.play;
 HTMLMediaElement.prototype.play=function(){window.__played.push(this.getAttribute('src')||'');
 return op.apply(this,arguments);};})();
"""}, sid)

    async def ev(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    await call("Page.navigate", {"url": URL}, sid)
    for _ in range(40):
        if (await ev("document.querySelectorAll('[data-audio]').length")) > 0:
            break
        await asyncio.sleep(0.5)
    await asyncio.sleep(1)
    box = await ev("""(function(){var b=document.querySelector('#allplay,#applay,#pplayall,#vplayall,.splay');
        if(!b)return null;b.scrollIntoView({block:'center'});var r=b.getBoundingClientRect();
        return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
    print("button:", box)
    if box:
        for ty in ("mousePressed", "mouseReleased"):
            await call("Input.dispatchMouseEvent", {"type": ty, "x": box["x"], "y": box["y"],
                                                    "button": "left", "clickCount": 1}, sid)
        await asyncio.sleep(6)
        print("played:", await ev("window.__played.slice(0,4)"))
    proc.kill()


asyncio.run(main())
