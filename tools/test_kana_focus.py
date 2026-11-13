#!/usr/bin/env python3
"""驗證「羅馬拼音」模式的鍵盤流程（桌機游標要自動在輸入框）。

檢查：
1. 電腦版（hover:hover / pointer:fine）：進入 五十音 頁焦點在 #answer。
2. 輸入答案按 Enter → 核對；再按 Enter → 下一題，焦點重回 #answer、輸入框清空。
3. 切去「聽音選字」再切回「羅馬拼音」，焦點仍在 #answer。
4. 手機（粗指標＋觸控）：不自動聚焦（避免鍵盤自己彈出）。

用法： python3 tools/test_kana_focus.py [http://127.0.0.1:8912/]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8912/"
DESKTOP_FLAGS = ("--blink-settings=primaryHoverType=2,availableHoverTypes=2,"
                 "primaryPointerType=4,availablePointerTypes=4")


class Browser:
    def __init__(self, port, extra=()):
        self.port = port
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", *extra,
             f"--remote-debugging-port={port}",
             f"--user-data-dir=/tmp/cdp-kfocus-{port}-{os.getpid()}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.seq = 0

    async def connect(self):
        ver = None
        for _ in range(100):
            try:
                ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version"))
                break
            except Exception:
                time.sleep(0.3)
        if not ver:
            sys.exit("CDP 起不來")
        self.ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
        self.sid = (await self.call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
        self.sid = (await self.call("Target.attachToTarget",
                                    {"targetId": self.sid, "flatten": True}))["result"]["sessionId"]
        await self.call("Runtime.enable", {}, self.sid)
        await self.call("Page.enable", {}, self.sid)

    async def call(self, method, params=None, sid=None, timeout=12):
        self.seq += 1
        myid = self.seq
        msg = {"id": myid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await self.ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=max(0.02, end - time.time())))
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                return None
            if m.get("id") == myid:
                return m
        return None

    async def js(self, expr):
        r = await self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, self.sid)
        if r and "result" in r:
            return r["result"].get("result", {}).get("value")
        return None

    async def key(self, k, code, vk):
        for t in ("keyDown", "keyUp"):
            await self.call("Input.dispatchKeyEvent", {"type": t, "key": k, "code": code,
                                                       "windowsVirtualKeyCode": vk,
                                                       "nativeVirtualKeyCode": vk}, self.sid)

    async def go(self, url, wait_expr="document.getElementById('answer') ? 1 : 0", secs=25):
        await self.call("Page.navigate", {"url": url}, self.sid)
        end = time.time() + secs
        while time.time() < end:
            if await self.js(wait_expr):
                await asyncio.sleep(3.0)      # 等 kana-templates.json 載入後的第二次 render（會重設輸入框）
                return True
            await asyncio.sleep(0.3)
        return False

    def close(self):
        self.proc.terminate()


STATE = ("(function(){var a=document.getElementById('answer'),"
         "b=document.getElementById('checkBtn');"
         "return {act: document.activeElement ? (document.activeElement.id||document.activeElement.tagName):'',"
         " dis: a?a.disabled:null, val: a?a.value:null, btn: b?b.textContent:null};})()")


async def main():
    fails = []

    def check(ok, label, detail=""):
        if not ok:
            fails.append(f"{label}：{detail}")

    # ── 電腦版
    b = Browser(9362, (DESKTOP_FLAGS,))
    await b.connect()
    await b.call("Emulation.setTouchEmulationEnabled", {"enabled": False}, b.sid)
    await b.call("Emulation.setDeviceMetricsOverride",
                 {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False}, b.sid)
    ok = await b.go(BASE + "kana/")
    check(ok, "桌機載入 kana 頁失敗")
    s0 = await b.js(STATE) or {}
    check(s0.get("act") == "answer", "桌機進入頁面焦點應在 #answer", str(s0))

    await b.call("Page.bringToFront", {}, b.sid)
    # 輸入錯答案 → 按 Enter 核對（用 DOM 事件，避免 headless Input domain 不穩）
    await b.js("(function(){var a=document.getElementById('answer');a.value='zzz';"
               "a.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));})()")
    await asyncio.sleep(0.6)
    s1 = await b.js(STATE) or {}
    check(s1.get("dis") is True, "核對後輸入框應停用", str(s1))
    check((s1.get("btn") or "").startswith("下一題"), "核對後按鈕應變「下一題 →」", str(s1.get("btn")))

    # 按「下一題」→ 新一題、游標要回去
    await b.js("document.getElementById('checkBtn').click()")
    await asyncio.sleep(0.8)
    s2 = await b.js(STATE) or {}
    check(s2.get("act") == "answer", "下一題後焦點應重回 #answer", str(s2))
    check(s2.get("dis") is False, "下一題輸入框應可再輸入", str(s2))
    check(s2.get("val") == "", "下一題輸入框應清空", str(s2))

    # 鍵盤輸入模式的提示字（桌機用全文）
    await b.js("document.querySelector('[data-mode=\"speak\"]').click()")
    await asyncio.sleep(0.5)
    ph = await b.js("document.getElementById('speakInput').placeholder")
    check(ph == "用日文鍵盤手寫／輸入平假名／片假名", "桌機鍵盤輸入提示字不對", str(ph))
    await b.js("document.querySelector('[data-mode=\"read\"]').click()")
    await asyncio.sleep(0.6)

    await b.js("document.querySelector('[data-mode=\"listen\"]').click()")
    await asyncio.sleep(0.5)
    await b.js("document.querySelector('[data-mode=\"read\"]').click()")
    await asyncio.sleep(0.8)
    s3 = await b.js(STATE) or {}
    check(s3.get("act") == "answer", "切回羅馬拼音焦點應在 #answer", str(s3))
    b.close()

    # ── 手機（不加快捷 flag：headless 預設 hover:none / pointer:coarse）
    m = Browser(9363, ())
    await m.connect()
    await m.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}, m.sid)
    await m.call("Emulation.setDeviceMetricsOverride",
                 {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, m.sid)
    await m.go(BASE + "kana/")
    s4 = await m.js(STATE) or {}
    s4["fine"] = await m.js("matchMedia('(hover:hover) and (pointer:fine)').matches")
    await m.js("document.querySelector('[data-mode=\"speak\"]').click()")
    await asyncio.sleep(0.5)
    ph2 = await m.js("document.getElementById('speakInput').placeholder")
    check(ph2 == "手寫或鍵盤輸入假名", "手機鍵盤輸入提示字應為短版", str(ph2))
    check(s4.get("act") != "answer", "手機不應自動聚焦（鍵盤會自己彈出）", str(s4))
    m.close()

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("全部通過：桌機進入／核對後下一題／切換模式焦點都在 #answer，提示字（桌機全文、手機短版）正確，手機不自動聚焦")
    return 0


sys.exit(asyncio.run(main()))
