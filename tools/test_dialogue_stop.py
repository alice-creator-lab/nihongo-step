#!/usr/bin/env python3
"""驗證會話「播放整段」的浮動停止鍵與播完後的按鈕狀態。

- 會話頁未播放時沒有浮動鍵。
- 按「▶ 播放整段」後底部出現浮動「停止播放」，顯示「第幾句／共幾句」，頁頂按鈕變「■ 停止」。
- 播到下一句時進度會遞增（自動續播）。
- 按浮動鍵即停：浮動鍵消失、句子高亮清空、頁頂按鈕還原「▶ 播放整段」、之後不再播。
- 讓整段自然播完：按鈕亦要還原、浮動鍵收起（舊版播完仍顯示「■ 停止」）。
- 換頁自動收起；390／360px 無橫向溢出。

用法： python3 tools/test_dialogue_stop.py [http://127.0.0.1:8791/]
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
PORT = int(os.environ.get("CDP_PORT", "9347"))

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-dlgstop-" + str(os.getpid()), "about:blank"],
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

    async def wait_until(expr, secs=30):
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

    # 1) 會話頁載入
    await call("Page.navigate", {"url": BASE + "#/l/L01/dialogue"}, sid)
    await wait_until("document.querySelectorAll('.dlg [data-play]').length")
    out["版本"] = await js("document.getElementById('verTag').textContent.trim()")
    out["段落數"] = await js("document.querySelectorAll('.dlg [data-play]').length")
    out["句數"] = await js("document.querySelectorAll('.dlg .line').length")
    out["初始浮動鍵隱藏"] = await js("!document.getElementById('dlgstop').classList.contains('on')")
    out["初始按鈕"] = await js("document.querySelector('.dlg [data-play]').textContent.trim()")

    # 2) 按播放整段 → 浮動鍵出現、頁頂變停止
    await js(INSTR)
    await js("document.querySelector('.dlg [data-play]').click()")
    await asyncio.sleep(0.8)
    out["按後浮動鍵"] = await js("document.getElementById('dlgstop').classList.contains('on')")
    out["浮動鍵文字"] = await js("document.getElementById('dlgstop').textContent.trim()")
    out["進度"] = await js("document.getElementById('dlgstopN').textContent.trim()")
    out["頁頂按鈕"] = await js("[document.querySelector('.dlg [data-play]').classList.contains('onplay'),"
                             " document.querySelector('.dlg [data-play]').textContent.trim()]")
    out["當前句高亮"] = await js("document.querySelectorAll('.dlg .line.playing').length")
    out["浮動鍵位置"] = await js("(function(){var b=document.getElementById('dlgstop').getBoundingClientRect();"
                             "return [Math.round(b.left), Math.round(b.top), Math.round(b.right), Math.round(b.bottom), window.innerWidth];})()")
    await shot("dlgstop-390.png")

    first = await js("window.__played.length")
    await asyncio.sleep(4.0)
    later = await js("window.__played.length")
    out["已播段數"] = [first, later]
    out["會自動續播"] = bool(first and later and later > first)
    out["進度有更新"] = await js("document.getElementById('dlgstopN').textContent.trim()")
    out["已播檔頭"] = await js("window.__played.slice(0,4)")

    # 3) 按浮動鍵即停
    await js("document.getElementById('dlgstop').click()")
    await asyncio.sleep(0.5)
    out["停後"] = await js("""(function(){
      var b = document.querySelector('.dlg [data-play]');
      return { bar: document.getElementById('dlgstop').classList.contains('on'),
               lines: document.querySelectorAll('.dlg .line.playing').length,
               stillPlaying: !!(window.__cur && !window.__cur.paused),
               btnOn: b.classList.contains('onplay'),
               btnTx: b.textContent.trim() };
    })()""")
    st = out["停後"] or {}
    out["停止鍵消失"] = (not st.get("bar") and st.get("lines") == 0
                     and not st.get("stillPlaying") and not st.get("btnOn")
                     and st.get("btnTx") == "▶ 播放整段")
    n_after_stop = await js("window.__played.length")
    await asyncio.sleep(2.0)
    out["停後不再播"] = await js("window.__played.length") == n_after_stop

    # 4) 自然播完整段：按鈕與浮動鍵都要收起
    await js("window.__played = []")
    await js("document.querySelector('.dlg [data-play]').click()")
    await asyncio.sleep(0.6)
    out["第二輪開始"] = await js("document.getElementById('dlgstop').classList.contains('on')")
    done = await wait_until("(function(){var b=document.querySelector('.dlg [data-play]');"
                            "return !document.getElementById('dlgstop').classList.contains('on')"
                            " && b.textContent.trim()==='▶ 播放整段' && !b.classList.contains('onplay');})()", 90)
    out["播完後還原"] = bool(done)
    out["播完句數"] = await js("window.__played.length")
    out["播完狀態"] = await js("""(function(){
      var b = document.querySelector('.dlg [data-play]');
      return { bar: document.getElementById('dlgstop').classList.contains('on'),
               btnTx: b.textContent.trim(), btnOn: b.classList.contains('onplay'),
               lines: document.querySelectorAll('.dlg .line.playing').length };
    })()""")
    out["播完後不再播"] = (await js("window.__played.length") == out["播完句數"])

    # 5) 換頁自動收起
    await js("document.querySelector('.dlg [data-play]').click()")
    await asyncio.sleep(0.5)
    await call("Page.navigate", {"url": BASE + "#/l/L01/vocab"}, sid)
    await wait_until("document.querySelectorAll('#app .vrow').length")
    out["換頁後收起"] = await js("!document.getElementById('dlgstop').classList.contains('on')")

    # 6) 390 / 360 無橫向溢出
    for w in (390, 360):
        await viewport(w)
        await call("Page.navigate", {"url": BASE + "#/l/L01/dialogue"}, sid)
        await wait_until("document.querySelectorAll('.dlg [data-play]').length")
        await js("document.querySelector('.dlg [data-play]').click()")
        await asyncio.sleep(0.7)
        out[f"寬度{w}"] = await js("[window.innerWidth, document.documentElement.scrollWidth,"
                                  " document.body.scrollWidth]")
        await js("document.getElementById('dlgstop').click()")
        await asyncio.sleep(0.2)

    print(json.dumps(out, ensure_ascii=False, indent=1))

    checks = {
        "版本 v189": out.get("版本") == "v189",
        "未播時無浮動鍵": out.get("初始浮動鍵隱藏") is True,
        "按後出現浮動鍵": out.get("按後浮動鍵") is True,
        "進度顯示 1／N": str(out.get("進度") or "").startswith("1／"),
        "頁頂變停止": out.get("頁頂按鈕") == [True, "■ 停止"],
        "自動續播": out.get("會自動續播") is True,
        "進度有更新": out.get("進度有更新") not in (None, "", out.get("進度")),
        "按浮動鍵即停": out.get("停止鍵消失") is True,
        "停後不再播": out.get("停後不再播") is True,
        "播完自動還原": out.get("播完後還原") is True,
        "播完不再播": out.get("播完後不再播") is True,
        "換頁收起": out.get("換頁後收起") is True,
        "390 無溢出": (out.get("寬度390") or [0, 1])[1] <= (out.get("寬度390") or [390, 390])[0],
        "360 無溢出": (out.get("寬度360") or [0, 1])[1] <= (out.get("寬度360") or [360, 360])[0],
    }
    bad = [k for k, v in checks.items() if not v]
    print("\n失敗：" + "、".join(bad) if bad else "\n全部通過")
    try:
        proc.terminate()
    except Exception:
        pass
    return 1 if bad else 0


sys.exit(asyncio.run(main()))
