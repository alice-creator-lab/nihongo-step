#!/usr/bin/env python3
"""列出某課某分頁的例句列同它們的音檔，檢查有沒有缺 data-audio。

用法：python3 tools/dump_rows.py http://127.0.0.1:8940/ L02 grammar
"""
import asyncio, glob, json, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
BASE = sys.argv[1]; LID = sys.argv[2]; TAB = sys.argv[3]
PORT = 9681


async def main():
    import subprocess
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             "--disable-dev-shm-usage", "--single-process", "--no-zygote",
                             "--mute-audio", f"--remote-debugging-port={PORT}",
                             "--user-data-dir=/tmp/cdp-dump", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
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
    await call("Page.navigate", {"url": f"{BASE}#/l/{LID}"}, sid)
    await asyncio.sleep(2.5)

    async def ev(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    for _ in range(20):
        st = await ev(f"""(function(){{var b=document.querySelector('.tab[data-tab="{TAB}"]');
            if(!b)return 'no-tab';if(!b.classList.contains('on'))b.click();
            return b.classList.contains('on')?'on':'off';}})()""")
        if st == "on":
            break
        await asyncio.sleep(0.4)
    await asyncio.sleep(0.8)
    print("active tab:", await ev("(document.querySelector('.tab.on')||{}).getAttribute?document.querySelector('.tab.on').getAttribute('data-tab'):'?'"))
    rows = await ev("""Array.from(document.querySelectorAll('.exrow')).map(function(r){
        var j=r.querySelector('.ja'), s=r.querySelector('[data-audio]');
        return [j?j.textContent:'', s?s.getAttribute('data-audio'):'(none)'];});""")
    print(TAB, "rows", len(rows))
    for t, a in rows:
        print(" ", a.split("/")[-1] if a else "(none)", "|", t)
    print("playall:", await ev("""(function(){var b=document.getElementById('pplayall');return b?b.textContent.trim():'';})()"""))
    proc.kill()


asyncio.run(main())
