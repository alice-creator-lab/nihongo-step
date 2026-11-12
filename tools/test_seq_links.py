#!/usr/bin/env python3
"""驗證「相關順序表」入口：位置（詞語區頂部、播放列下面）、每課對應、深層連結。

檢查項目
1. 7 課（L03/04/05/07/10/16/17）的詞語頁有 .seqlinks，文字與 SEQ_FOR_LESSON 相符。
2. 入口在第一個 .vrow 之前（唔再埋在單字表最尾），且在 #vplayall 之後（播放列下面）。
3. 未教相關量詞的課（L01、L19、L40）冇入口。
4. L10「數詞（二）」→ #/seq/cnt2、該 section 有 .focus、頁面有捲動。
5. 390／360px 無橫向溢出。

用法： python3 tools/test_seq_links.py [http://127.0.0.1:8899/]
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不到 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899/"
PORT = int(os.environ.get("CDP_PORT", "9337"))

EXPECT = {
    "L03": ["時間"],
    "L04": ["數字", "～つ", "數詞（四）"],
    "L05": ["日數", "星期"],
    "L07": ["樓層"],
    "L10": ["數詞（一）", "數詞（二）", "數詞（三）"],
    "L16": ["數詞（一）", "數詞（三）"],
    "L17": ["數詞（四）"],
}
NONE = ["L01", "L19", "L40"]

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else f"  → {detail}"))
    if not ok:
        fails.append(label)


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-sl-" + str(os.getpid()), "about:blank"],
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

    await viewport(390)

    async def open_hash(h, wait=25):
        await js("location.hash='" + h + "'; 1")
        await asyncio.sleep(0.6)
        await wait_until("document.querySelector('#seg') && document.querySelector('#seg').children.length", wait)

    # 由地圖起步，之後只改 hash
    await call("Page.navigate", {"url": BASE + "#/"}, sid)
    await wait_until("document.querySelector('#app') && !!document.querySelector('.lrow, .tool')")
    await js("history.replaceState(null,'','#/l/L03/vocab'); window.dispatchEvent(new HashChangeEvent('hashchange')); 1")
    await asyncio.sleep(1.0)

    print("版本:", await js("document.getElementById('verTag').textContent"))

    # 1+2. 每課入口文字、位置
    for lid, want in EXPECT.items():
        await open_hash(f"#/l/{lid}/vocab")
        got = await js("(function(){var b=document.querySelector('.seqlinks'); if(!b) return null;"
                       "return Array.prototype.map.call(b.querySelectorAll('a'),function(a){"
                       "return a.textContent.replace('→','').trim();});})()")
        check(f"{lid} 入口文字 {want}", got == want, str(got))
        pos = await js("(function(){var b=document.querySelector('.seqlinks'), v=document.querySelector('.vrow'),"
                       " p=document.getElementById('vplayall'); if(!b||!v||!p) return null;"
                       "var bb=b.getBoundingClientRect(), vb=v.getBoundingClientRect(), pb=p.getBoundingClientRect();"
                       "return {beforeVrow: bb.top < vb.top, afterPlay: bb.top > pb.top};})()")
        check(f"{lid} 入口喺播放列下面、單字表之前", bool(pos and pos["beforeVrow"] and pos["afterPlay"]), str(pos))
        of = await js("document.documentElement.scrollWidth <= window.innerWidth")
        check(f"{lid} 390px 無橫向溢出", of is True)
        await js("window.scrollTo(0,0); 1")

    # 3. 冇相關量詞的課
    for lid in NONE:
        await open_hash(f"#/l/{lid}/vocab")
        n = await js("document.querySelectorAll('.seqlinks').length")
        check(f"{lid} 冇入口", n == 0, str(n))

    # 4. 深層連結
    await open_hash("#/l/L10/vocab")
    await js("(function(){var a=document.querySelector('.seqlinks a[href=\"#/seq/cnt2\"]'); a && a.click();})()")
    ok = await wait_until("document.querySelector('#sgrp-cnt2') ? 1 : 0")
    check("跳去 #/seq/cnt2", ok is not None)
    await asyncio.sleep(1.2)
    focus = await js("!!document.querySelector('#sgrp-cnt2.focus')")
    check("cnt2 section 有 focus 邊框", focus is True)
    sy = await js("window.scrollY")
    check("有捲到該段", isinstance(sy, (int, float)) and sy > 200, str(sy))

    # 5. 360px
    await viewport(360)
    await open_hash("#/l/L04/vocab")
    of = await js("document.documentElement.scrollWidth <= window.innerWidth")
    check("L04 360px 無橫向溢出", of is True)

    print("\n" + ("全部通過" if not fails else f"{len(fails)} 項失敗: " + ", ".join(fails)))
    try:
        proc.kill()
    except Exception:
        pass
    return 0 if not fails else 1


sys.exit(asyncio.run(main()))
