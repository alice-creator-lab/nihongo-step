#!/usr/bin/env python3
"""驗證第18課的「普通形 ⇄ ます形 對照表」（#/plain）：

入口在第18課頁頂（其他課不可以有）、7 組表格、4 條轉換規律、4 條例外、
390／375／360px 不爆版、返回鍵回第18課文法頁。

用法： python3 tools/test_plainforms.py [http://127.0.0.1:8899/]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899/"
PORT = int(os.environ.get("CDP_PORT", "9336"))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-pl-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
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

    async def viewport(w):
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def wait_until(expr, secs=25):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await asyncio.sleep(0.4)
        return None

    out = {}
    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/l/L18/patterns"}, sid)
    await wait_until("document.querySelector('#seg') && document.querySelector('#seg').children.length")

    # 1. 入口卡只出現在第18課
    out["版本"] = await js("document.getElementById('verTag').textContent")
    out["L18 入口"] = await js("(function(){var a=document.querySelector('#app > a.afentry'); return a ? [a.getAttribute('href'), a.querySelector('b').textContent] : null;})()")
    out["L18 入口在分頁之上"] = await js("!!(document.querySelector('#app > a.afentry') && document.querySelector('#app > a.afentry').nextElementSibling.id === 'tabs')")
    await js("location.hash='#/l/L17/grammar'; 1")
    await asyncio.sleep(1.2)
    out["L17 無入口"] = await js("document.querySelectorAll('#app > a.afentry').length")

    # 2. 點入口 → 對照表頁
    await js("location.hash='#/l/L18/patterns'; 1")
    await asyncio.sleep(1.2)
    await js("document.querySelector('#app > a.afentry').click(); 1")
    await wait_until("document.querySelectorAll('.aftbl.pl').length")
    out["hash"] = await js("location.hash")
    out["標題"] = await js("document.querySelector('.lhead h1').textContent")
    out["返回鍵"] = await js("document.querySelector('.lhead a.back').getAttribute('href')")
    out["_表數"] = await js("document.querySelectorAll('table.aftbl.pl').length")
    out["_資料格"] = await js("document.querySelectorAll('table.aftbl.pl tbody td').length")
    out["_說法"] = await js("document.querySelectorAll('table.aftbl.pl .f').length")
    out["組標題"] = await js("Array.prototype.map.call(document.querySelectorAll('.gsec h3'), function(h){return h.textContent;})")
    out["表頭"] = await js("Array.prototype.map.call(document.querySelectorAll('table.aftbl.pl thead th'), function(t){return t.textContent;}).filter(function(s){return s.length;})")
    out["列標籤"] = await js("Array.prototype.map.call(document.querySelectorAll('table.aftbl.pl tbody th'), function(t){return t.textContent;})")
    out["tense rowspan"] = await js("Array.prototype.map.call(document.querySelectorAll('table.aftbl.pl .tense'), function(t){return t.getAttribute('rowspan');})")
    out["轉換規律條數"] = await js("document.querySelectorAll('.prule')[0].children.length")
    out["例外條數"] = await js("document.querySelectorAll('.prule')[1].children.length")
    out["例外文本"] = await js("document.querySelectorAll('.prule')[1].textContent")
    out["藍色例外字"] = await js("Array.prototype.map.call(document.querySelectorAll('.prule b.exw'), function(b){return b.textContent;})")

    # 3. 窄螢幕不爆版
    for w in (390, 375, 360):
        await viewport(w)
        await asyncio.sleep(0.5)
        out["寬 %d" % w] = await js("""(function(){
          var bad=[];
          Array.prototype.forEach.call(document.querySelectorAll('table.aftbl.pl td'), function(td){
            var room = td.clientWidth - 8;
            Array.prototype.forEach.call(td.querySelectorAll('.f'), function(f){
              if (f.scrollWidth > room + 1){ bad.push([f.textContent, f.scrollWidth, room]); }
            });
          });
          var over=[];
          Array.prototype.forEach.call(document.querySelectorAll('.aftblwrap'), function(wr){
            if (wr.scrollWidth > wr.clientWidth + 1) over.push([wr.scrollWidth, wr.clientWidth]);
          });
          return { 溢出文字: bad, 表格橫向捲動: over,
                   body: [document.body.scrollWidth, window.innerWidth] };
        })()""")

    # 4. 返回鍵回第18課文法頁
    await viewport(390)
    await asyncio.sleep(0.3)
    await js("document.querySelector('.lhead a.back').click(); 1")
    await asyncio.sleep(1.4)
    out["返回後"] = await js("location.hash")
    out["返回後有分頁"] = await js("!!document.querySelector('#tabs')")

    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()

asyncio.run(main())
