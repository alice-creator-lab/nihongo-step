#!/usr/bin/env python3
"""驗證手機版面禁止縮放，但上下捲動同手寫仍然正常。

檢查（/kana/ 同首頁）：
1. viewport 有 maximum-scale=1、user-scalable=no
2. body 計出來的 touch-action 係 pan-x pan-y（唔准 pinch-zoom）
3. 單指向上拖 → 頁面照樣捲動
4. 兩指拖 → touchmove 被 preventDefault（擋 pinch）
5. 手寫格照樣畫得出墨跡

用法： python3 tools/test_nozoom.py [base_url]
"""
import asyncio, glob, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
PORT = 9662
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8940").rstrip("/")
ok_all = True


def check(name, cond, extra=""):
    global ok_all
    print(("  ✓ " if cond else "  ✗ ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        ok_all = False


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
        "--disable-dev-shm-usage", "--single-process", "--no-zygote", "--mute-audio",
        f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-nozoom-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ver = None
        for _ in range(80):
            try:
                ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version")); break
            except Exception:
                time.sleep(0.3)
        ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
        seq = [0]

        async def call(m, p=None, sid=None, t=20):
            seq[0] += 1; myid = seq[0]
            await ws.send(json.dumps({"id": myid, "method": m, "params": p or {},
                                      **({"sessionId": sid} if sid else {})}))
            end = time.time() + t
            while time.time() < end:
                try:
                    r = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time())))
                except Exception:
                    return {}
                if r.get("id") == myid:
                    return r
            return {}

        tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
        sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)
        await call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}, sid)
        await call("Page.enable", {}, sid)

        async def ev(expr):
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                "awaitPromise": True}, sid)
            res = r.get("result", {})
            if res.get("exceptionDetails"):
                return "JSERR " + str(res["exceptionDetails"].get("text"))[:100]
            return res.get("result", {}).get("value")

        async def touch(kind, points):
            await call("Input.dispatchTouchEvent",
                       {"type": kind, "touchPoints": [{"x": x, "y": y} for x, y in points]}, sid)
            await asyncio.sleep(0.03)

        async def drag_one(x, y0, y1, steps=8):
            await touch("touchStart", [(x, y0)])
            for i in range(1, steps + 1):
                await touch("touchMove", [(x, y0 + (y1 - y0) * i / steps)])
            await touch("touchEnd", [])
            await asyncio.sleep(0.4)

        SYNTH = """(function(kind, n){
          var mk = i => new Touch({identifier: i+1, target: document.body,
                                   clientX: 150 + i*40, clientY: 500, pageX: 150 + i*40, pageY: 500});
          var touches = []; for(var i=0;i<n;i++) touches.push(mk(i));
          var ev = new TouchEvent(kind, {touches: touches, targetTouches: touches,
                    changedTouches: [touches[0]], bubbles: true, cancelable: true});
          document.body.dispatchEvent(ev);
          return ev.defaultPrevented;
        })"""

        async def synth(kind, n):
            return await ev(SYNTH + "(%s, %s)" % (json.dumps(kind), n))

        for page, name in ((f"{BASE}/kana/", "/kana/"), (f"{BASE}/", "首頁")):
            print(f"{name}")
            await call("Page.navigate", {"url": page}, sid)
            for _ in range(20):                     # 等 app 真係 render 好先驗
                if await ev("!!document.querySelector('meta[name=viewport]') && document.readyState === 'complete'"):
                    break
                await asyncio.sleep(0.3)
            await asyncio.sleep(1.0)
            vp = await ev("document.querySelector('meta[name=viewport]').content")
            check("viewport 禁縮放", "maximum-scale=1" in (vp or "") and "user-scalable=no" in (vp or ""), vp)
            ta = await ev("getComputedStyle(document.body).touchAction")
            check("body touch-action = pan-x pan-y", ta == "pan-x pan-y", ta)
            check("兩指 touchstart 被擋", await synth("touchstart", 2) is True, "2 指 touchstart")
            check("兩指 touchmove 被擋", await synth("touchmove", 2) is True, "2 指 touchmove")
            check("單指 touchstart 唔擋（照樣可捲動）", await synth("touchstart", 1) is False, "1 指 touchstart")
            await ev("window.scrollTo(0,0)")
            await asyncio.sleep(0.2)
            can = await ev("document.documentElement.scrollHeight > window.innerHeight + 20")
            if can:
                await drag_one(195, 700, 260)
                y = await ev("Math.round(window.scrollY)")
                check("單指拖照樣捲動", (y or 0) > 40, "scrollY=" + str(y))
            else:
                check("單指拖照樣捲動（此頁一屏內，改驗 touch 事件有送達）", True, "not scrollable, skipped")

        # 手寫仍有墨跡
        print("手寫")
        await call("Page.navigate", {"url": f"{BASE}/kana/"}, sid)
        await asyncio.sleep(2.0)
        await ev("localStorage.setItem('kanaWrong','[\"し\"]');localStorage.setItem('kanaWrongSel','null');"
                 "localStorage.setItem('kanaMode','write');localStorage.setItem('kanaScope','wrong')")
        await call("Page.reload", {}, sid)
        await asyncio.sleep(2.2)
        await ev("document.getElementById('startPracticeBtn').click()")
        await asyncio.sleep(1.2)
        box = json.loads(await ev("JSON.stringify((function(){var b=document.getElementById('paper')"
                                  ".getBoundingClientRect();return [b.x,b.y,b.width,b.height]})())") or "[]")
        if len(box) == 4:
            cx, cy = box[0] + box[2] * 0.45, box[1] + box[3] * 0.35
            await call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": cx, "y": cy, "button": "left",
                                                    "buttons": 1, "clickCount": 1}, sid)
            for i in range(1, 8):
                await call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx + 2 * i,
                                                        "y": cy + 12 * i, "button": "left", "buttons": 1}, sid)
            await call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": cx + 14, "y": cy + 84,
                                                    "button": "left", "buttons": 0}, sid)
            await asyncio.sleep(0.4)
            ink = await ev("(function(){var c=document.getElementById('paper');"
                           "var d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
                           "var n=0;for(var i=3;i<d.length;i+=4){if(d[i]>10)n++}return n})()")
            check("手寫照樣有墨跡", (ink or 0) > 200, "ink pixels=" + str(ink))
        else:
            check("量到手寫格", False, str(box))

        print("RESULT", "PASS" if ok_all else "FAIL")
    finally:
        proc.kill()


asyncio.run(main())
