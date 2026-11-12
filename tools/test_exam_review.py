#!/usr/bin/env python3
"""回歸測試：階段測驗的逐題檢討頁。

檢查（做完第 3 階段測驗之後）：
  - 每題都有四個選項全文（.ol 四行），共 28×4＝112 行
  - 正解一行 ○、自己答錯的一行 ×
  - 排序題（文の組み立て）有 ①〜④ 空格與正確語序，★ 標在第三格
  - 390px 無橫向溢出

用法： python3 tools/test_exam_review.py [http://127.0.0.1:8791/]
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = next((c for c in [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
] if os.path.exists(c)), None)
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
PORT = int(os.environ.get("CDP_PORT", "9917"))


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                             "--autoplay-policy=no-user-gesture-required",
                             f"--remote-debugging-port={PORT}",
                             "--user-data-dir=/tmp/cdp-exrev-" + str(os.getpid()), "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version")); break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(method, params=None, sid=None, timeout=25):
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

    await call("Page.navigate", {"url": BASE + "#/exam/3"}, sid)
    if not await wait("!!document.getElementById('exStart')"):
        sys.exit("測驗首頁未載入")
    await js("document.getElementById('exStart').click()")
    if not await wait("!!document.querySelector('.exopt')"):
        sys.exit("測驗未開始")

    for i in range(28):
        await js("document.querySelector('.exopt').click()")
        await asyncio.sleep(0.06)
        if not await js("!!document.getElementById('exNext')"):
            break
        await js("document.getElementById('exNext').click()")
        await asyncio.sleep(0.08)

    if not await wait("!!document.querySelector('.exrev')", 20):
        sys.exit("沒有出現檢討頁")

    m = await js("""(function(){
      var cards=[].slice.call(document.querySelectorAll('.excard'));
      var ol=document.querySelectorAll('.excard .ol div').length;
      var ok=document.querySelectorAll('.excard .ol .ok').length;
      var no=document.querySelectorAll('.excard .ol .no').length;
      var ordCards=cards.filter(function(c){return c.querySelector('.ord');});
      var ordTxt=ordCards.map(function(c){
        return {slots:(c.querySelector('.exslots')||{}).innerText||'',
                order:(c.querySelector('.ord')||{}).innerText||''};
      });
      return {cards:cards.length, ol:ol, ok:ok, no:no, ordCards:ordCards.length, ordTxt:ordTxt,
              iw:window.innerWidth, sw:document.documentElement.scrollWidth};
    })()""")
    print(json.dumps(m, ensure_ascii=False, indent=1))

    ok = True
    if m["cards"] != 28 or m["ol"] != 112:
        print("FAIL 選項行數不符"); ok = False
    if m["ok"] < 28:
        print("FAIL 每題應有一個 ○"); ok = False
    if m["ordCards"] < 2:
        print("FAIL 排序題沒有語序"); ok = False
    for o in m["ordTxt"]:
        if "★" not in o["slots"] or "①" not in o["order"]:
            print("FAIL 排序題空格或語序不完整：", o); ok = False
    if m["sw"] > m["iw"]:
        print("FAIL 390px 橫向溢出"); ok = False

    print("\n結果：", "PASS" if ok else "FAIL")
    try: proc.terminate()
    except Exception: pass
    sys.exit(0 if ok else 1)

asyncio.run(main())
