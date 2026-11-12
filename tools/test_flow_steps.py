import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = next((c for c in [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
] if os.path.exists(c)), None)
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
PORT = int(os.environ.get("CDP_PORT", "9931"))

async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             f"--remote-debugging-port={PORT}",
                             "--user-data-dir=/tmp/cdp-flow-" + str(os.getpid()), "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version")); break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]
    async def call(method, params=None, sid=None, timeout=30):
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
            if m.get("id") == seq[0]: return m
        return None
    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Runtime.enable", {}, sid)
    await call("Emulation.setDeviceMetricsOverride",
               {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)
    async def js(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True}, sid)
        return r["result"].get("result", {}).get("value") if r else None
    async def wait(expr, secs=30):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v: return v
            await asyncio.sleep(0.25)
        return None

    await call("Page.navigate", {"url": BASE + "#/l/L11/grammar"}, sid)
    if not await wait("!!document.querySelector('.fstep')"):
        sys.exit("L11 文法頁沒有 flow")
    await asyncio.sleep(1.0)
    m = await js("""(function(){
      var st=[].map.call(document.querySelectorAll('.fstep'),function(e){
        return {n:(e.querySelector('.nb')||{}).innerText, q:(e.querySelector('.fq')||{}).innerText,
                out:[].map.call(e.querySelectorAll('.fo,.fres,.fout'),function(o){return o.innerText.slice(0,40);})};
      });
      return {count:st.length, steps:st, iw:innerWidth, sw:document.documentElement.scrollWidth};
    })()""")
    print(json.dumps(m, ensure_ascii=False, indent=1))
    ok = m["count"] == 4 and m["sw"] <= m["iw"]
    print("結果：", "PASS" if ok else "FAIL")
    try: proc.terminate()
    except Exception: pass
    sys.exit(0 if ok else 1)

asyncio.run(main())
