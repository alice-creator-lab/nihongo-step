#!/usr/bin/env python3
"""驗證「句型屬於某個形」的小框標示（v193：全 40 課已標 65 個句型、66 個標籤）：

- 第20課 7 卡 7 框（て形×5、ない形×2）。
- 第17課 6 卡 7 框（た形×6 ＋ て形×1）：第 4 張「もう～ました／まだ～ていません」屬兩個形，兩個框並排。
- 第12課 7 框含「ます形」；第07課（未標）0 框。
- 每個框連去五段動詞詳細表（#/all/verbs/forms/godan），藍色 #0b5cad、1px 框、無底線。
- 390／375／360px：小框落在句型第一行的垂直範圍內、不溢出、頁面不需橫向捲動。

用法： python3 tools/test_pat_form.py [http://127.0.0.1:8899/]
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
PORT = int(os.environ.get("CDP_PORT", "9351"))
EXPECT_VERSION = os.environ.get("EXPECT_VERSION", "v193")
EXPECT_VER_ROWS = int(os.environ.get("EXPECT_VER_ROWS", "115"))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-pf-" + str(os.getpid()), "about:blank"],
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

    fails = []

    def check(name, got, want):
        ok = got == want
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
        if not ok:
            fails.append(name)

    CHIPS = "Array.prototype.map.call(document.querySelectorAll('.pat .pfrm'), function(a){return a.textContent;})"

    async def lesson(lid):
        await js(f"location.hash='#/l/{lid}/patterns'; 1")
        await asyncio.sleep(1.2)
        await wait_until("document.querySelectorAll('.pat').length && document.querySelector('.pat .pja')")

    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/l/L20/patterns"}, sid)
    await wait_until("document.querySelectorAll('.pat').length")

    check("版本", await js("document.getElementById('verTag').textContent"), EXPECT_VERSION)

    # 1. 第20課：7 卡 7 框
    check("L20 句型卡數", await js("document.querySelectorAll('.pat').length"), 7)
    check("L20 小框數目", await js("document.querySelectorAll('.pat .pfrm').length"), 7)
    check("L20 小框文字", await js(CHIPS),
          ["て形", "て形", "て形", "ない形", "ない形", "て形", "て形"])
    check("小框連結", await js("Array.prototype.every.call(document.querySelectorAll('.pat .pfrm'), function(a){return a.getAttribute('href')==='#/all/verbs/forms/godan';})"), True)
    check("小框包在 .pfrmg、在句型之前", await js("""Array.prototype.every.call(document.querySelectorAll('.pat'), function(c){
        var g=c.querySelector('.pfrmg'), p=c.querySelector('.pja');
        if(!g) return true;
        return g.nextElementSibling===p && g.querySelectorAll('.pfrm').length>0;})"""), True)

    style = await js("""(function(){var a=document.querySelector('.pat .pfrm'); var s=getComputedStyle(a);
      return {color:s.color, bg:s.backgroundColor, border:s.borderTopColor, bw:s.borderTopWidth,
              radius:s.borderTopLeftRadius, deco:s.textDecorationLine};})()""")
    check("小框顏色（藍）", (style or {}).get("color"), "rgb(11, 92, 173)")
    check("小框底色", (style or {}).get("bg"), "rgb(230, 238, 251)")
    check("小框有框線", ((style or {}).get("border"), (style or {}).get("bw")), ("rgb(11, 92, 173)", "1px"))
    check("小框無底線", ((style or {}).get("deco"), (style or {}).get("radius")), ("none", "7px"))

    # 2. 第17課：一個句型同屬兩個形
    await lesson("L17")
    check("L17 句型卡數", await js("document.querySelectorAll('.pat').length"), 6)
    check("L17 小框數目", await js("document.querySelectorAll('.pat .pfrm').length"), 7)
    check("L17 小框文字", await js(CHIPS),
          ["た形", "た形", "た形", "た形", "て形", "た形", "た形"])
    check("L17 第4張兩個框", await js("Array.prototype.map.call(document.querySelectorAll('.pat')[3].querySelectorAll('.pfrm'), function(a){return a.textContent;})"),
          ["た形", "て形"])
    check("L17 第4張兩個框同組", await js("document.querySelectorAll('.pat')[3].querySelectorAll('.pfrmg .pfrm').length"), 2)

    lay = await js("""(function(){var c=document.querySelectorAll('.pat')[3];
        var g=c.querySelector('.pfrmg').getBoundingClientRect(), p=c.querySelector('.pja').getBoundingClientRect();
        return {兩框並排: Math.abs(c.querySelectorAll('.pfrm')[0].getBoundingClientRect().top - c.querySelectorAll('.pfrm')[1].getBoundingClientRect().top) < 1,
                在句型之上: g.bottom <= p.top + 2, 間距: Math.round(p.top - g.bottom)};})()""") or {}
    print("   第4張排版", json.dumps(lay, ensure_ascii=False))
    check("L17 兩框並排", lay.get("兩框並排"), True)
    check("L17 兩框在句型之上", lay.get("在句型之上"), True)

    # 3. 第12課有ます形；第07課未標
    await lesson("L12")
    check("L12 小框數目", await js("document.querySelectorAll('.pat .pfrm').length"), 7)
    check("L12 有ます形", await js("Array.prototype.filter.call(document.querySelectorAll('.pat .pfrm'), function(a){return a.textContent==='ます形';}).length"), 1)
    await lesson("L07")
    check("L07 無小框", await js("document.querySelectorAll('.pat .pfrm').length"), 0)
    check("L07 句型仍在", await js("document.querySelector('.pat .pja').textContent.length > 0"), True)

    # 4. 窄螢幕（用有兩個框的第17課量）
    await lesson("L17")
    for w in (390, 375, 360):
        await viewport(w)
        await asyncio.sleep(0.6)
        r = await js("""(function(){
          var bad=[], offLine=[];
          Array.prototype.forEach.call(document.querySelectorAll('.pat'), function(c){
            var g=c.querySelector('.pfrmg'), p=c.querySelector('.pja');
            if(!g||!p) return;
            var gr=g.getBoundingClientRect(), pr=p.getBoundingClientRect(), cr=c.getBoundingClientRect();
            /* 小框可以：(a) 在句型第一行旁邊，或 (b) 句型太長時自成一行、排在句型之上。
               兩種都不可以壓住句型文字。 */
            var lineTop = pr.top, lineBot = pr.top + parseFloat(getComputedStyle(p).lineHeight);
            var beside = (gr.top >= lineTop - 6 && gr.bottom <= lineBot + 6);
            var above = (gr.bottom <= lineTop + 2);
            if (!beside && !above) offLine.push([p.textContent, gr.top, lineTop, gr.bottom, lineBot]);
            if (gr.right > cr.right - 8) bad.push([p.textContent, gr.right, cr.right]);
            if (p.scrollWidth > p.clientWidth + 1) bad.push([p.textContent, p.scrollWidth, p.clientWidth]);
          });
          return {跑出第一行: offLine, 溢出: bad, body:[document.body.scrollWidth, window.innerWidth]};
        })()""") or {}
        print(f"--- {w}px", json.dumps(r, ensure_ascii=False))
        check(f"{w}px 小框與句型不重疊", r.get("跑出第一行"), [])
        check(f"{w}px 無溢出", r.get("溢出"), [])
        check(f"{w}px 頁面不需橫向捲動", r.get("body"), [w, w])

    # 5. 點小框 → 五段動詞詳細表
    await viewport(390)
    await asyncio.sleep(0.3)
    await js("document.querySelectorAll('.pat')[3].querySelectorAll('.pfrm')[1].click(); 1")
    await wait_until("document.querySelectorAll('.vftbl tbody tr.vgrp').length")
    check("點小框後 hash", await js("location.hash"), "#/all/verbs/forms/godan")
    check("詳細表標題", await js("document.querySelector('.lhead h1').textContent.indexOf('五段動詞') === 0"), True)
    check("詳細表有表頭", await js("Array.prototype.map.call(document.querySelectorAll('.vftbl thead th'), function(t){return t.textContent;})"),
          ["辞書形", "ます形", "て形", "た形", "ない形"])
    check("五段行數", await js("(function(){var all=document.querySelectorAll('.vftbl tbody tr').length; var grp=document.querySelectorAll('.vftbl tbody tr.vgrp').length; return all-grp;})()"), EXPECT_VER_ROWS)
    check("返回鍵回動詞表", await js("document.querySelector('.lhead a.back').getAttribute('href')"), "#/all/verbs")

    print()
    if fails:
        print("失敗：", "、".join(fails))
        proc.terminate()
        await ws.close()
        sys.exit(1)
    print("全部通過")
    proc.terminate()
    await ws.close()

asyncio.run(main())
