#!/usr/bin/env python3
"""重現「播放全部漏句」：開 L02，逐個分頁找 ▶ 播放全部，記錄真正播放的音檔次序。

用法：python3 tools/test_playall_order.py http://127.0.0.1:8940/ L02
"""
import asyncio, glob, json, os, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8940/"
LID = sys.argv[2] if len(sys.argv) > 2 else "L02"
PORT = 9677


async def main():
    import subprocess
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
         "--single-process", "--no-zygote", "--mute-audio",
         "--autoplay-policy=no-user-gesture-required", f"--remote-debugging-port={PORT}",
         "--user-data-dir=/tmp/cdp-playall", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(60):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(m, p=None, sid=None, t=20):
        seq[0] += 1
        mid = seq[0]
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
 HTMLMediaElement.prototype.play=function(){
   try{window.__played.push(this.getAttribute('src')||this.src||'');}catch(e){}
   return op.apply(this,arguments);};})();
"""}, sid)

    async def ev(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True,
                                            "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    await call("Page.navigate", {"url": BASE + "#/l/" + LID}, sid)
    await asyncio.sleep(2.5)
    for tab in ("patterns", "grammar"):
        await ev(f"""(function(){{var b=document.querySelector('.tab[data-tab="{tab}"]');if(b)b.click();}})()""")
        await asyncio.sleep(0.8)
        has = await ev("""(function(){var b=document.getElementById('pplayall')||document.querySelector('button.btn2');return b?b.textContent.trim():'';})()""")
        print(tab, "playall button:", repr(has))
        if not has:
            continue
        await ev('window.__played=[]')
        box = await ev("""(function(){var b=document.getElementById('pplayall')||document.querySelector('button.btn2');
            if(!b)return null;var r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
        if box:
            for ty in ("mousePressed", "mouseReleased"):
                await call("Input.dispatchMouseEvent", {"type": ty, "x": box["x"], "y": box["y"],
                                                        "button": "left", "clickCount": 1}, sid)
        await asyncio.sleep(2)
        for _ in range(40):
            state = await ev("""(function(){var b=document.getElementById('pplayall');return b?b.textContent.trim():'';})()""")
            if "停止" not in state:
                break
            await asyncio.sleep(2)
        played = await ev("window.__played")
        print(tab, "played", len(played))
        for p in played:
            print("   ", p.split("/")[-1].split("?")[0])
    proc.kill()


asyncio.run(main())
