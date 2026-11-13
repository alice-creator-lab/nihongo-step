#!/usr/bin/env python3
"""驗證桌面網頁版整體放大 150%（v224）。

檢查：
1. 1440px 桌面：html 的 zoom 是 1.5、內容欄約 1140px（760×1.5）、字高確實放大、無橫向溢出。
2. 899px（未達門檻）：不放大。
3. 390px 手機：不放大（zoom 不變），內容欄仍貼滿 390px。
4. 觸控平板條件：模擬 pointer:coarse 時不放大（iPad 用原本字級）。

用法： python3 tools/test_desktop_zoom.py [http://127.0.0.1:8912/]
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8912/"
PORT = int(os.environ.get("CDP_PORT", "9352"))
SHOT = os.environ.get("SHOT", "")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--blink-settings=primaryHoverType=2,availableHoverTypes=2,"
         "primaryPointerType=4,availablePointerTypes=4",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-zoom-" + str(os.getpid()), "about:blank"],
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

    async def call(method, params=None, sid=None, timeout=10):
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

    async def desktop(w, h=900):
        # mobile:false＋不模擬觸控＋明確模擬 hover／pointer（桌面）
        await call("Emulation.setTouchEmulationEnabled", {"enabled": False}, sid)
        await call("Emulation.setEmulatedMedia", {"features": [
            {"name": "hover", "value": "hover"}, {"name": "pointer", "value": "fine"}]}, sid)
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": False}, sid)

    async def phone(w, h=844):
        await call("Emulation.setEmulatedMedia", {"features": [
            {"name": "hover", "value": "none"}, {"name": "pointer", "value": "coarse"}]}, sid)
        await call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}, sid)
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": h, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def wait_until(expr, secs=30):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await asyncio.sleep(0.4)
        return None

    async def shot(name):
        r = await call("Page.captureScreenshot", {"format": "png"}, sid, timeout=25)
        if r and "result" in r:
            open(name, "wb").write(base64.b64decode(r["result"]["data"]))

    fails = []

    def check(ok, label, detail=""):
        if not ok:
            fails.append(f"{label}：{detail}")

    # 1440 桌面
    await desktop(1440)
    await call("Page.navigate", {"url": BASE + "#/all/particles"}, sid)
    await wait_until("document.querySelector('#pglist section.pgc') ? 1 : 0")
    out = await js("""(function(){
      var w=document.querySelector('.wrap'), h1=document.querySelector('.pgh b');
      var cs=getComputedStyle(document.documentElement);
      return { zoom: cs.zoom, hover: matchMedia('(hover:hover)').matches,
               pointer: matchMedia('(pointer:fine)').matches,
               wrap: w? Math.round(w.getBoundingClientRect().width):0,
               iw: window.innerWidth, sw: document.documentElement.scrollWidth,
               h1h: h1? Math.round(h1.getBoundingClientRect().height):0,
               fs: h1? getComputedStyle(h1).fontSize : null };
    })()""") or {}
    check(out.get("hover") and out.get("pointer"), "headless 應報桌面指標（hover／pointer）", str(out))
    check(out.get("zoom") == "1.5", "1440px 應 zoom 1.5", str(out.get("zoom")))
    check(abs(out.get("wrap", 0) - 1140) <= 3, "內容欄應約 1140px（760×1.5）", str(out.get("wrap")))
    check(out.get("sw", 9e9) <= out.get("iw", 0) + 1, "1440px 無橫向溢出", str(out))
    try:
        fs = float(str(out.get("fs", "0")).replace("px", ""))
    except ValueError:
        fs = 0
    check(fs and out.get("h1h", 0) >= fs * 1.3, "字高應按比例放大", f"h1 {out.get('h1h')} vs font-size {out.get('fs')}")
    if SHOT:
        await shot(SHOT)

    # 899 桌面（未達門檻）
    await desktop(899)
    await call("Page.navigate", {"url": BASE + "#/"}, sid)
    await wait_until("document.querySelector('.wrap') ? 1 : 0")
    z2 = await js("getComputedStyle(document.documentElement).zoom")
    check(z2 in (None, "", "1", "normal"), "899px 不應放大", str(z2))

    # 手機 390
    await phone(390)
    await call("Page.navigate", {"url": BASE + "#/"}, sid)
    await wait_until("document.querySelector('.wrap') ? 1 : 0")
    out3 = await js("""(function(){var w=document.querySelector('.wrap');
      return { zoom:getComputedStyle(document.documentElement).zoom,
               wrap:w?Math.round(w.getBoundingClientRect().width):0,
               iw:window.innerWidth, sw:document.documentElement.scrollWidth};})()""") or {}
    check(out3.get("zoom") in (None, "", "1", "normal"), "390px 不應放大", str(out3.get("zoom")))
    check(out3.get("wrap", 0) >= out3.get("iw", 0) - 2, "390px 內容欄應貼滿", str(out3))
    check(out3.get("sw", 9e9) <= out3.get("iw", 0) + 1, "390px 無橫向溢出", str(out3))

    await ws.close()
    proc.terminate()
    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print(f"全部通過：1440px zoom 1.5（內容欄 {out.get('wrap')}px、無溢出）、899px 不放大、"
          f"390px 不放大且貼滿（{out3.get('wrap')}px）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
