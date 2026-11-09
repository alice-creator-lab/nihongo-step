#!/usr/bin/env python3
"""驗證「動詞詳細表」的「播放全部」＋浮動「停止播放」鍵。

- 三個詳細表頁頂都有 ▶ 播放全部，旁邊寫總項數（115／51／15）。
- 按下後由第一行起逐行播五形，當前行有 .playnow、當前格有 .on。
- 播放中右下／底部出現浮動停止鍵，顯示「第幾行／共幾行」。
- 按浮動停止鍵即停：bar 消失、行與格高亮清空、音檔暫停。
- 再按一次「播放全部」同樣會停（與其他頁一致）。

用法： python3 tools/test_vfplayall.py [http://127.0.0.1:8791/]
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
PORT = int(os.environ.get("CDP_PORT", "9338"))

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-vfa-" + str(os.getpid()), "about:blank"],
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
        r = await call("Page.captureScreenshot", {"format": "png"}, sid, timeout=25)
        if r and "result" in r:
            open("/tmp/" + name, "wb").write(base64.b64decode(r["result"]["data"]))

    out = {}
    await viewport(390)

    # 1) 三個表都有播放全部鍵與正確項數
    bars = {}
    for setid, total in (("godan", 115), ("ichidan", 51), ("irregular", 15)):
        await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/" + setid}, sid)
        await wait_until("document.querySelectorAll('.vftbl tbody tr').length")
        bars[setid] = {
            "鍵": await js("(function(){var b=document.querySelector('#vfplayall'); return b?b.textContent.trim():null})()"),
            "說明": await js("(function(){var s=document.querySelector('.vfbar .vfcnt'); return s?s.textContent:null})()"),
            "預期": total,
        }
    out["播放全部鍵"] = bars
    out["三頁都有鍵"] = all(b["鍵"] and "播放全部" in b["鍵"] for b in bars.values())
    out["項數正確"] = all(str(b["預期"]) in (b["說明"] or "") for b in bars.values())

    # 2) 五段：按下去逐行播
    await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/godan"}, sid)
    await wait_until("document.querySelectorAll('.vftbl .vfrow').length")
    await js(INSTR)
    out["初始停止鍵隱藏"] = await js("!document.getElementById('vfstop').classList.contains('on')")
    await js("document.getElementById('vfplayall').click()")
    await asyncio.sleep(0.6)
    out["按下後停止鍵"] = await js("document.getElementById('vfstop').classList.contains('on')")
    out["停止鍵文字"] = await js("document.getElementById('vfstop').textContent.trim()")
    out["播放進度"] = await js("document.getElementById('vfstopN').textContent.trim()")
    out["按鈕變停止態"] = await js("[document.getElementById('vfplayall').classList.contains('onplay'), document.getElementById('vfplayall').textContent.trim()]")
    out["當前行高亮"] = await js("document.querySelectorAll('.vftbl tr.playnow').length")
    out["當前格高亮"] = await js("document.querySelectorAll('.vftbl td.on').length")
    await shot("vfplayall-390.png")

    # 3) 等幾秒看有沒有繼續前進（五形一行，約 1 秒一形）
    first = await js("window.__played.length")
    await asyncio.sleep(4.5)
    later = await js("window.__played.length")
    out["已播段數"] = [first, later]
    out["會自動續播"] = bool(first and later and later > first)
    out["進度有更新"] = await js("document.getElementById('vfstopN').textContent.trim()")
    out["已播檔頭"] = await js("window.__played.slice(0,8)")

    # 4) 浮動停止鍵：一按即停
    await js("document.getElementById('vfstop').click()")
    await asyncio.sleep(0.5)
    out["停後"] = await js("""(function(){
      return { bar: document.getElementById('vfstop').classList.contains('on'),
               rows: document.querySelectorAll('.vftbl tr.playnow').length,
               cells: document.querySelectorAll('.vftbl td.on').length,
               stillPlaying: !!(window.__cur && !window.__cur.paused),
               btnOn: document.getElementById('vfplayall').classList.contains('onplay'), btnTx: document.getElementById('vfplayall').textContent.trim() };
    })()""")
    out["停止鍵消失"] = bool(out["停後"] and not out["停後"]["bar"] and out["停後"]["rows"] == 0
        and out["停後"]["cells"] == 0 and not out["停後"]["stillPlaying"]
        and not out["停後"]["btnOn"] and out["停後"]["btnTx"] == "▶ 播放全部")
    n_after_stop = await js("window.__played.length")
    await asyncio.sleep(2.0)
    out["停後不再播"] = await js("window.__played.length") == n_after_stop

    # 5) 再按一次播放全部＝停止
    await js("document.getElementById('vfplayall').click()")
    await asyncio.sleep(0.5)
    out["第二輪播放中"] = await js("document.getElementById('vfstop').classList.contains('on')")
    await js("document.getElementById('vfplayall').click()")
    await asyncio.sleep(0.4)
    out["再按即停"] = await js("!document.getElementById('vfstop').classList.contains('on')")

    # 6) 短表（不規則 15 項）也可用
    await call("Page.navigate", {"url": BASE + "#/all/verbs/forms/irregular"}, sid)
    await wait_until("document.querySelectorAll('.vftbl .vfrow').length")
    await js("document.getElementById('vfplayall').click()")
    await asyncio.sleep(0.6)
    out["短表播放中"] = await js("[document.getElementById('vfstop').classList.contains('on'), document.getElementById('vfstopN').textContent.trim()]")
    await js("document.getElementById('vfstop').click()")

    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()

asyncio.run(main())
