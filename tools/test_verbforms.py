#!/usr/bin/env python3
"""驗證「動詞詳細表」（#/all/verbs/forms/<set>）：
入口在動詞表三個分類標題、五欄次序、行分組、手機闊度不爆版、示範音檔可播。

用法： python3 tools/test_verbforms.py [http://127.0.0.1:8791/]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/"
PORT = int(os.environ.get("CDP_PORT", "9336"))

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-vf-" + str(os.getpid()), "about:blank"],
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

    async def shot(name):
        r = await call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}, sid, timeout=20)
        if r and "result" in r:
            open("/tmp/" + name, "wb").write(base64.b64decode(r["result"]["data"]))

    out = {}
    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/all/verbs"}, sid)
    await wait_until("document.querySelectorAll('.vfentry').length")
    out["動詞表入口"] = await js("Array.prototype.map.call(document.querySelectorAll('.wth'),function(h){var a=h.querySelector('.vfentry'); return [h.querySelector('.wtn').textContent, a?a.textContent.trim():null, a?a.getAttribute('href'):null];})")

    pages = {}
    for setid, blocks, total in (("godan", 8, 115), ("ichidan", 2, 51), ("irregular", 2, 15)):
        await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/" + setid}, sid)
        await wait_until("document.querySelectorAll('.vftbl tbody tr').length")
        pages[setid] = {
            "標題": await js("document.querySelector('.lhead h1').textContent"),
            "表頭": await js("Array.prototype.map.call(document.querySelectorAll('.vftbl thead th'),function(t){return t.textContent;})"),
            "行組": await js("Array.prototype.map.call(document.querySelectorAll('.vftbl .vgrp th'),function(t){return t.textContent;})"),
            "行數": await js("document.querySelectorAll('.vftbl tbody tr:not(.vgrp)').length"),
            "喇叭數": await js("document.querySelectorAll('.vftbl .vspk').length"),
            "跳轉鍵": await js("document.querySelectorAll('.jumpbar .jump').length"),
            "預期行組": blocks, "預期行數": total,
        }
        if setid == "godan":
            await shot("vf-godan-390.png")
    out["頁面"] = pages
    out["行數正確"] = all(p["行數"] == p["預期行數"] for p in pages.values())
    out["行組數正確"] = all(len(p["行組"]) == p["預期行組"] for p in pages.values())
    out["欄序"] = pages["godan"]["表頭"] == ["辞書形", "ます形", "て形", "た形", "ない形"]

    # 找行く與食べる的五形
    async def row_of(kana):
        return await js("""(function(){
          var rows=document.querySelectorAll('.vftbl tbody tr:not(.vgrp)');
          for (var i=0;i<rows.length;i++){
            var b=rows[i].querySelector('.vdtop b');
            if (b && b.textContent==='%s'){
              var out=[rows[i].querySelector('.vd').textContent.trim()];
              Array.prototype.forEach.call(rows[i].querySelectorAll('td.vf'), function(td){
                var fn=td.querySelector('.fn'), fk=td.querySelector('.fk');
                out.push([fn?fn.textContent:'', fk?fk.textContent:'']);
              });
              return out;
            }
          }
          return null; })()""" % kana)
    await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/godan"}, sid)
    await wait_until("document.querySelectorAll('.vftbl tbody tr').length")
    out["行く"] = await row_of("行く")
    out["行く五形正確"] = out["行く"][1:] == [["行きます","いきます"],["行って","いって"],["行った","いった"],["行かない","いかない"]]
    await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/ichidan"}, sid)
    await wait_until("document.querySelectorAll('.vftbl tbody tr').length")
    out["食べる"] = await row_of("食べる")
    out["食べる五形正確"] = out["食べる"][1:] == [["食べます","たべます"],["食べて","たべて"],["食べた","たべた"],["食べない","たべない"]]

    # 闊度：表格容器不可橫向滾動，格子文字不可爆出
    for w in (390, 375, 360):
        await viewport(w)
        await asyncio.sleep(0.4)
        await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/irregular"}, sid)
        await wait_until("document.querySelectorAll('.vftbl tbody tr').length")
        out["溢出 %dpx" % w] = await js("""(function(){
          var wrap=document.querySelector('.vftblwrap');
          var bad=[];
          Array.prototype.forEach.call(document.querySelectorAll('.vftbl td'),function(td){
            if (td.scrollWidth > td.clientWidth+1){ bad.push([td.textContent.slice(0,12), td.scrollWidth, td.clientWidth]); }
          });
          return {wrap:[wrap.scrollWidth, wrap.clientWidth], bad:bad.slice(0,4), inner:innerWidth};
        })()""")

    # 音檔：点辞書形的喇叭，依次播五形
    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/godan"}, sid)
    await wait_until("document.querySelectorAll('.vftbl .vfrow').length")
    await js(INSTR)
    clicked = await js("""(function(){
      var rows=document.querySelectorAll('.vftbl tbody tr:not(.vgrp)');
      for (var i=0;i<rows.length;i++){
        var b=rows[i].querySelector('.vdtop b');
        if (b && b.textContent==='行く'){
          rows[i].querySelector('.vfrow').click(); return 1;
        }
      }
      return null; })()""")
    got = []
    for _ in range(30):
        await asyncio.sleep(0.4)
        got = await js("window.__played || []")
        if len(got) >= 5:
            break
    out["行く喇叭數"] = await js("""(function(){
      var rows=document.querySelectorAll('.vftbl tbody tr:not(.vgrp)');
      for (var i=0;i<rows.length;i++){
        var b=rows[i].querySelector('.vdtop b');
        if (b && b.textContent==='行く'){ return rows[i].querySelectorAll('.vspk').length; }
      } })()""")
    out["播放檔"] = got
    out["五形依次"] = [g.split("?")[0].split("/")[-1] for g in got[:5]] == \
        ["L06-0.mp3", "L06-0-masu.mp3", "L06-0-te.mp3", "L06-0-ta.mp3", "L06-0-nai.mp3"]
    out["播放中高亮"] = await js("document.querySelectorAll('.vftbl td.on').length")
    # 再按一次停止（趁還在播）
    await js("""(function(){
      var rows=document.querySelectorAll('.vftbl tbody tr:not(.vgrp)');
      for (var i=0;i<rows.length;i++){
        var b=rows[i].querySelector('.vdtop b');
        if (b && b.textContent==='行く'){ rows[i].querySelector('.vfrow').click(); break; }
      }
    })()""")
    await asyncio.sleep(0.4)
    out["停止後"] = await js("[document.querySelectorAll('.vftbl .spk.playing').length, document.querySelectorAll('.vftbl td.on').length, !!(window.__cur && !window.__cur.paused)]")

    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()

asyncio.run(main())
