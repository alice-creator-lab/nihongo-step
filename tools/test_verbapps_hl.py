#!/usr/bin/env python3
"""驗證「不同形態的應用」頁的例句標色（.apmk）。

檢查：
1. 31 行每行都有至少一個 .apmk，且標出的文字等於 data/verbapps.json 的 hl。
2. .apmk 的顏色是 #0b5cad（與句型欄同一個藍）。
3. 390px 與 360px 都無橫向溢出。
4. 截圖（可選，SHOT=/path/x.png）。

用法： python3 tools/test_verbapps_hl.py http://127.0.0.1:8911
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
BASE = sys.argv[1]
SHOT = os.environ.get("SHOT", "")
PORT = 9355
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = json.load(open(os.path.join(ROOT, "data/verbapps.json"), encoding="utf-8"))
EXPECT = []
for g in DATA["groups"]:
    for r in g["rows"]:
        EXPECT.append((r["a"], r["hl"]))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={PORT}",
         "--user-data-dir=/tmp/cdp-apmk-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    n = [0]

    async def send(method, params=None, sid=None):
        n[0] += 1
        msg = {"id": n[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        while True:
            raw = json.loads(await ws.recv())
            if raw.get("id") == n[0]:
                return raw

    t = await send("Target.createTarget", {"url": "about:blank"})
    s = await send("Target.attachToTarget", {"targetId": t["result"]["targetId"], "flatten": True})
    sid = s["result"]["sessionId"]
    await send("Page.enable", {}, sid)
    await send("Runtime.enable", {}, sid)

    async def ev(js):
        r = await send("Runtime.evaluate",
                       {"expression": js, "returnByValue": True, "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    async def width(w):
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)
        await send("Page.navigate", {"url": BASE + "#/all/verbs/apps"}, sid)
        for _ in range(40):
            await asyncio.sleep(0.25)
            if await ev("document.querySelectorAll('.aptbl tr.apr').length"):
                break

    fails = []

    await width(390)
    got = await ev("""
      (function(){
        return JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.aptbl tr.apr'), function(tr){
          var mk = Array.prototype.map.call(tr.querySelectorAll('.apmk'), function(e){ return e.innerText; });
          var cs = tr.querySelector('.apmk') ? getComputedStyle(tr.querySelector('.apmk')) : null;
          return {pat: tr.querySelector('.appat').innerText, mk: mk,
                  color: cs ? cs.color : null, weight: cs ? cs.fontWeight : null,
                  ex: tr.querySelector('.apex').innerText};
        }));
      })()
    """)
    rows = json.loads(got)
    if len(rows) != len(EXPECT):
        fails.append(f"行數 {len(rows)} ≠ {len(EXPECT)}")
    for (a, hl), row in zip(EXPECT, rows):
        if row["mk"] != hl:
            fails.append(f"第 {a} 行標色 {row['mk']} ≠ 資料 {hl}（{row['ex']}）")
        if row["color"] not in ("rgb(11, 92, 173)",):
            fails.append(f"第 {a} 行標色顏色 {row['color']} 不是 #0b5cad")

    for w in (390, 360):
        if w != 390:
            await width(w)
        over = await ev("document.documentElement.scrollWidth + '/' + window.innerWidth")
        sw = int(over.split("/")[0])
        if sw > w + 1:
            fails.append(f"{w}px 橫向溢出：{over}")
        if SHOT:
            await ev("window.scrollTo(0,0)")
            await asyncio.sleep(0.3)
            r = await send("Page.captureScreenshot", {"format": "png"}, sid)
            p = SHOT if w == 390 else SHOT.replace(".png", f"-{w}.png")
            open(p, "wb").write(base64.b64decode(r["result"]["data"]))

    print("例句標色：%d 行，顏色 %s，字重 %s" % (len(rows), rows[0]["color"], rows[0]["weight"]))
    print("示範：", rows[0]["pat"], "→", "".join("【%s】" % m for m in rows[0]["mk"]), "|", rows[0]["ex"])
    print("多段示範：", rows[14]["pat"], "→", rows[14]["mk"], "|", rows[14]["ex"])
    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
    else:
        print("全部通過")
    await ws.close()
    proc.terminate()
    sys.exit(1 if fails else 0)


asyncio.run(main())
