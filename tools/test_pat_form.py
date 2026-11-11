#!/usr/bin/env python3
"""驗證「句型屬於某個形」的小框標示（第20課先行）：

第20課 7 個句型全部有 form（て形 ×5、ない形 ×2），卡片左上出現可點的小框，
按下去連到五段動詞詳細表（#/all/verbs/forms/godan）；未標 form 的課（如第19課）不出現小框；
390／375／360px 小框與句型同一行、不爆版；小框用藍色（#0b5cad），不是紅色。

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
EXPECT_VERSION = os.environ.get("EXPECT_VERSION", "v192")
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

    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/l/L20/patterns"}, sid)
    await wait_until("document.querySelectorAll('.pat').length")

    check("版本", await js("document.getElementById('verTag').textContent"), EXPECT_VERSION)
    check("第20課句型卡數", await js("document.querySelectorAll('.pat').length"), 7)
    check("小框數目", await js("document.querySelectorAll('.pat .pfrm').length"), 7)
    check("小框文字", await js("Array.prototype.map.call(document.querySelectorAll('.pat .pfrm'), function(a){return a.textContent;})"),
          ["て形", "て形", "て形", "ない形", "ない形", "て形", "て形"])
    check("小框連結", await js("Array.prototype.every.call(document.querySelectorAll('.pat .pfrm'), function(a){return a.getAttribute('href')==='#/all/verbs/forms/godan';})"), True)
    check("小框在卡片內、句型之上", await js("Array.prototype.every.call(document.querySelectorAll('.pat'), function(c){var a=c.querySelector('.pfrm'); if(!a) return true; var p=c.querySelector('.pja'); return a.parentNode===p.parentNode && a.nextElementSibling===p;})"), True)

    style = await js("""(function(){var a=document.querySelector('.pat .pfrm'); var s=getComputedStyle(a);
      return {color:s.color, bg:s.backgroundColor, border:s.borderTopColor, bw:s.borderTopWidth,
              radius:s.borderTopLeftRadius, deco:s.textDecorationLine};})()""")
    check("小框顏色（藍）", (style or {}).get("color"), "rgb(11, 92, 173)")
    check("小框底色", (style or {}).get("bg"), "rgb(230, 238, 251)")
    check("小框有框線", ((style or {}).get("border"), (style or {}).get("bw")), ("rgb(11, 92, 173)", "1px"))
    check("小框無底線", ((style or {}).get("deco"), (style or {}).get("radius")), ("none", "7px"))

    # 未標 form 的課不出現小框
    await js("location.hash='#/l/L19/patterns'; 1")
    await wait_until("document.querySelectorAll('.pat').length")
    check("第19課無小框", await js("document.querySelectorAll('.pat .pfrm').length"), 0)
    check("第19課句型仍在", await js("document.querySelector('.pat .pja').textContent.length > 0"), True)

    # 窄螢幕：小框與句型同一行、不溢出
    await js("location.hash='#/l/L20/patterns'; 1")
    await wait_until("document.querySelectorAll('.pat').length")
    for w in (390, 375, 360):
        await viewport(w)
        await asyncio.sleep(0.5)
        r = await js("""(function(){
          var bad=[], sameLine=[];
          Array.prototype.forEach.call(document.querySelectorAll('.pat'), function(c){
            var a=c.querySelector('.pfrm'), p=c.querySelector('.pja');
            if(!a||!p) return;
            var ar=a.getBoundingClientRect(), pr=p.getBoundingClientRect();
            if (Math.abs((ar.top+ar.height/2) - (pr.top+pr.height/2)) > 3) sameLine.push(p.textContent);
            var cr=c.getBoundingClientRect();
            if (a.getBoundingClientRect().right > cr.right - 8) bad.push([a.textContent, a.getBoundingClientRect().right, cr.right]);
            if (p.scrollWidth > p.clientWidth + 1) bad.push([p.textContent, p.scrollWidth, p.clientWidth]);
          });
          return {同行: sameLine, 溢出: bad, body:[document.body.scrollWidth, window.innerWidth]};
        })()""") or {}
        print(f"--- {w}px", json.dumps(r, ensure_ascii=False))
        check(f"{w}px 小框與句型同行", r.get("同行"), [])
        check(f"{w}px 無溢出", r.get("溢出"), [])
        check(f"{w}px 頁面不需橫向捲動", r.get("body"), [w, w])

    # 點小框 → 五段動詞詳細表
    await viewport(390)
    await asyncio.sleep(0.3)
    await js("document.querySelectorAll('.pat .pfrm')[3].click(); 1")
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
