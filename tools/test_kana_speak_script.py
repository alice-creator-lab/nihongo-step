#!/usr/bin/env python3
"""驗證「鍵盤輸入」模式：聽發音→打假名，且要分平假名／片假名。

檢查：
1. 不再顯示大字假名（#speakKana 已移除），出題會自動播發音。
2. 平假名題打片假名 → 提示要打平假名，不計錯、可再打。
3. 打羅馬拼音 → 提示不接受羅馬拼音，不計錯。
4. 打對應平假名 → 答對。
5. 片假名題相反：打平假名被擋，打片假名答對。

用法： python3 tools/test_kana_speak_script.py [http://127.0.0.1:8912/]
"""
import asyncio, glob, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = sorted(glob.glob("/home/admin/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
PORT = 9651
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8940/").rstrip("/")
SITE = BASE + "/kana/?kdebug=1"

AUD = """window.__aud=[];(function(){var op=HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play=function(){try{window.__aud.push(this.src||this.currentSrc)}catch(e){}
return op.apply(this,arguments);};})();"""

ok_all = True


def check(name, cond, extra=""):
    global ok_all
    print(("  ✓ " if cond else "  ✗ ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        ok_all = False


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
        "--disable-dev-shm-usage", "--single-process", "--no-zygote", "--mute-audio",
        "--autoplay-policy=no-user-gesture-required",
        f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-speak-" + str(os.getpid()), "about:blank"],
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
        await call("Page.enable", {}, sid)
        await call("Page.addScriptToEvaluateOnNewDocument", {"source": AUD}, sid)

        async def ev(expr):
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                "awaitPromise": True}, sid)
            return r.get("result", {}).get("result", {}).get("value")

        async def load(chars):
            await call("Page.navigate", {"url": SITE}, sid)
            await asyncio.sleep(1.6)
            await ev("localStorage.setItem('kanaWrong', %s);localStorage.setItem('kanaWrongSel','null');"
                     "localStorage.setItem('kanaExtras','[]');localStorage.setItem('kanaMode','speak');"
                     "localStorage.setItem('kanaScope','wrong');localStorage.setItem('kanaMute','0');"
                     % json.dumps(json.dumps(chars, ensure_ascii=False)))
            await call("Page.reload", {}, sid)
            await asyncio.sleep(2.2)
            await ev("(function(){var b=document.getElementById('startPracticeBtn'); if(b) b.click(); return !!b})()")
            await asyncio.sleep(1.2)

        async def typ(v):
            await ev("(function(v){var i=document.getElementById('speakInput'); i.value=%s;"
                     "i.dispatchEvent(new Event('input',{bubbles:true})); return i.value})(%s)"
                     % (json.dumps(v), json.dumps(v)))
            await ev("document.getElementById('speakCheck').click()")
            await asyncio.sleep(0.3)
            return await ev("JSON.stringify({note:document.getElementById('speakNote').textContent,"
                            "fb:document.getElementById('fbSpeak').innerText.trim().slice(0,40),"
                            "answered:window.__kanaTest.answered()})")

        # ── A. 平假名題 ─────────────────────────────
        print("A. 平假名題")
        await load(["ぬ"])
        cur = json.loads(await ev("JSON.stringify(window.__kanaTest.current())") or "{}")
        check("題目是平假名", cur.get("k") == "ぬ" and cur.get("type") == "hira", cur)
        check("唔再顯示大字假名", await ev("!document.getElementById('speakKana')"))
        check("有提示要打平假名", "平假名" in (await ev("document.getElementById('speakHintScript').textContent") or ""))
        check("出題自動播發音", (await ev("(window.__aud||[]).length")) >= 1, await ev("JSON.stringify(window.__aud||[])"))
        r = json.loads(await typ("ヌ"))
        check("打片假名被擋（提示要平假名）", "平假名" in r["note"] and not r["answered"], r["note"])
        r = json.loads(await typ("nu"))
        check("打羅馬拼音被擋", "不接受羅馬拼音" in r["note"] and not r["answered"], r["note"])
        r = json.loads(await typ("ぬ"))
        check("打平假名答對", "答對" in r["fb"] and r["answered"], r["fb"])

        # ── B. 片假名題 ─────────────────────────────
        print("B. 片假名題")
        await load(["ヌ"])
        cur = json.loads(await ev("JSON.stringify(window.__kanaTest.current())") or "{}")
        check("題目是片假名", cur.get("k") == "ヌ" and cur.get("type") == "kata", cur)
        check("有提示要打片假名", "片假名" in (await ev("document.getElementById('speakHintScript').textContent") or ""))
        r = json.loads(await typ("ぬ"))
        check("打平假名被擋（提示要片假名）", "片假名" in r["note"] and not r["answered"], r["note"])
        r = json.loads(await typ("ヌ"))
        check("打片假名答對", "答對" in r["fb"] and r["answered"], r["fb"])

        print("RESULT", "PASS" if ok_all else "FAIL")
    finally:
        proc.kill()


asyncio.run(main())
