#!/usr/bin/env python3
"""單句測試：在句型分頁找「この本はわたしのです。」，按它的喇叭，看實際播放哪個檔。

用法：python3 tools/test_one_row.py <base> <lesson> <text-substr>
"""
import asyncio, glob, json, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
BASE, LID, NEEDLE = sys.argv[1], sys.argv[2], sys.argv[3]
PORT = 9683


async def main():
    import subprocess
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             "--disable-dev-shm-usage", "--single-process", "--no-zygote",
                             "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                             f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-one",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    await call("Page.addScriptToEvaluateOnNewDocument", {"source": """
window.__played=[];window.__log=[];
(function(){var op=HTMLMediaElement.prototype.play;
 HTMLMediaElement.prototype.play=function(){window.__played.push(this.getAttribute('src')||this.src||'');
 return op.apply(this,arguments);};})();
window.addEventListener('error',function(e){window.__log.push('ERR '+e.message);},true);
"""}, sid)

    async def ev(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    await call("Page.navigate", {"url": f"{BASE}#/l/{LID}"}, sid)
    for _ in range(30):
        if (await ev("document.querySelectorAll('.exrow').length")) > 0:
            break
        await asyncio.sleep(0.5)
    await asyncio.sleep(1.0)
    info = await ev("""(function(){var rows=Array.from(document.querySelectorAll('.exrow'));
      var r=rows.find(function(x){var j=x.querySelector('.ja');return j&&j.textContent.indexOf(%s)>=0;});
      if(!r)return null;var b=r.querySelector('[data-audio]');
      r.scrollIntoView({block:'center'});var rc=b.getBoundingClientRect();
      return {audio:b.getAttribute('data-audio'),x:rc.x+rc.width/2,y:rc.y+rc.height/2};})()""" % json.dumps(NEEDLE))
    print("row:", info)
    if info:
        await asyncio.sleep(0.5)
        for ty in ("mousePressed", "mouseReleased"):
            await call("Input.dispatchMouseEvent", {"type": ty, "x": info["x"], "y": info["y"],
                                                    "button": "left", "clickCount": 1}, sid)
        await asyncio.sleep(1.5)
        print("played:", await ev("window.__played"))
        print("err:", await ev("window.__log"))
        print("media state:", await ev("""(function(){var a=document.querySelector('audio');
            if(!a)return 'no-audio-el';return {src:a.getAttribute('src'),paused:a.paused,ct:a.currentTime,dur:a.duration,err:a.error&&a.error.code};})()"""))
    proc.kill()


asyncio.run(main())
