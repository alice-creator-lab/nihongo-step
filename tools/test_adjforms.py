#!/usr/bin/env python3
"""驗證「形容詞的變化」頁（#/all/adjs/forms）：結構＝課本表格、每格音檔、窄螢幕不爆版。

用法： python3 tools/test_adjforms.py [http://127.0.0.1:8899/]
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
PORT = int(os.environ.get("CDP_PORT", "9334"))

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-af-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    await call("Page.navigate", {"url": BASE + "#/all/adjs/forms"}, sid)
    await wait_until("document.querySelectorAll('.aftbl .f').length")

    out["標題"] = await js("document.querySelector('.lhead h1').textContent")
    out["表頭"] = await js("Array.prototype.map.call(document.querySelectorAll('.aftbl thead th'), function(t){return t.textContent;})")
    out["列標籤"] = await js("Array.prototype.map.call(document.querySelectorAll('.aftbl tbody th'), function(t){return t.textContent;})")
    out["現在/過去 rowspan"] = await js("Array.prototype.map.call(document.querySelectorAll('.aftbl .tense'), function(t){return t.getAttribute('rowspan');})")
    out["資料格數"] = await js("document.querySelectorAll('.aftbl tbody td').length")
    out["說法總數"] = await js("document.querySelectorAll('.aftbl .f').length")
    out["喇叭數"] = await js("document.querySelectorAll('.aftbl .afspk').length")
    out["每格說法數"] = await js("Array.prototype.map.call(document.querySelectorAll('.aftbl tbody td'), function(d){return d.querySelectorAll('.f').length;})")
    out["ruby 數"] = await js("document.querySelectorAll('.aftbl ruby').length")

    # 窄螢幕不爆版：每個 .f 的 scrollWidth 不可超過所在格可視寬度
    for w in (390, 375, 360):
        await viewport(w)
        await asyncio.sleep(0.4)
        over = await js("""(function(){
          var bad=[];
          Array.prototype.forEach.call(document.querySelectorAll('.aftbl td'), function(td){
            var room = td.clientWidth - 6;   /* 左右 padding 各 3px */
            Array.prototype.forEach.call(td.querySelectorAll('.f'), function(f){
              if (f.scrollWidth > room + 1){ bad.push([f.textContent, f.scrollWidth, room, %d]); }
            });
          });
          return bad;
        })()""" % w)
        out["溢出 %dpx" % w] = over
        out["表寬 %dpx" % w] = await js("[document.querySelector('.aftbl').getBoundingClientRect().width, document.querySelector('.aftblwrap').clientWidth]")

    await viewport(390)
    await asyncio.sleep(0.3)

    # 每一格喇叭要依次播完整格所有說法
    await js(INSTR)
    cells = await js("document.querySelectorAll('.aftbl tbody td').length")
    played_ok = True
    detail = []
    for k in range(cells):
        want = await js("Array.prototype.map.call(document.querySelectorAll('.aftbl tbody td')[%d].querySelectorAll('.f'), function(f){return f.getAttribute('data-audio').split('/').pop();})" % k)
        await js("document.querySelectorAll('.aftbl tbody td')[%d].querySelector('.afspk').click(); 1" % k)
        got = []
        for _ in range(len(want) * 4):
            await asyncio.sleep(0.4)
            cur = await js("window.__played && window.__played.slice(-1)[0]")
            if cur:
                cur = cur.split("?")[0]          # 先去掉 ?v=f1 再比，否則每次都當新一段
                if not got or got[-1] != cur:
                    got.append(cur)
            if len(got) >= len(want):
                break
        detail.append([want, got])
        if [g.split("/")[-1] for g in got][:len(want)] != want:
            played_ok = False
        await js("document.querySelectorAll('.aftbl tbody td')[%d].querySelector('.afspk').click(); 1" % k)
        await asyncio.sleep(0.3)
    out["每格依次播完"] = played_ok
    out["播錯的格"] = [d for d in detail if [g.split("/")[-1] for g in d[1]][:len(d[0])] != d[0]]

    # 停止：再按一次要收掉高亮與播放
    await js("document.querySelector('.aftbl .afspk').click(); 1")
    await asyncio.sleep(0.5)
    out["播放中"] = await js("[document.querySelectorAll('.aftbl .f.on').length, document.querySelectorAll('.aftbl .afspk.on').length]")
    await js("document.querySelector('.aftbl .afspk').click(); 1")
    await asyncio.sleep(0.5)
    out["再按停止"] = await js("[document.querySelectorAll('.aftbl .f.on').length, document.querySelectorAll('.aftbl .afspk.on').length, !!(window.__cur && !window.__cur.paused)]")

    # 入口與返回
    await js("location.hash='#/all/adjs'; 1")
    await asyncio.sleep(1.2)
    out["形容詞表入口"] = await js("(function(){var a=document.querySelector('a.afentry'); return a? a.getAttribute('href') : null;})()")

    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()

asyncio.run(main())
