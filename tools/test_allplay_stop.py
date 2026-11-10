#!/usr/bin/env python3
"""驗證「詞語總表 → 播放全部」的浮動「停止播放」鍵。

- 詞語總表頁頂有 ▶ 播放全部；按下後底部出現浮動停止鍵，顯示「第幾項／共幾項」。
- 按浮動鍵即停：鍵消失、行高亮清空、音檔暫停、頁頂按鈕還原「▶ 播放全部」、之後不再播。
- 再按一次頁頂按鈕同樣停。
- 390 / 360px 下浮動鍵不出現橫向溢出。

用法： python3 tools/test_allplay_stop.py [http://127.0.0.1:8791/]
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
PORT = int(os.environ.get("CDP_PORT", "9341"))

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-apstop-" + str(os.getpid()), "about:blank"],
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

    # 1) 詞語總表載入
    await call("Page.navigate", {"url": BASE + "#/all/vocab"}, sid)
    rows = await wait_until("document.querySelectorAll('#alllist .arow').length")
    out["行數"] = rows
    out["版本"] = await js("document.getElementById('verTag').textContent.trim()")
    out["初始停止鍵隱藏"] = await js("!document.getElementById('allstop').classList.contains('on')")
    out["播放全部鍵"] = await js("(function(){var b=document.querySelector('#allplay'); return b?b.textContent.trim():null})()")

    # 2) 按下播放全部 → 浮動鍵出現、進度遞增
    await js(INSTR)
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.8)
    out["按後浮動鍵"] = await js("document.getElementById('allstop').classList.contains('on')")
    out["浮動鍵文字"] = await js("document.getElementById('allstop').textContent.trim()")
    out["進度"] = await js("document.getElementById('allstopN').textContent.trim()")
    out["頁頂按鈕"] = await js("[document.getElementById('allplay').classList.contains('onplay'), document.getElementById('allplay').textContent.trim()]")
    out["當前字詞高亮"] = await js("document.querySelectorAll('#alllist .arow.playing').length")
    out["浮動鍵位置"] = await js("(function(){var b=document.getElementById('allstop').getBoundingClientRect();"
                                 "return [Math.round(b.left), Math.round(b.top), Math.round(b.right), Math.round(b.bottom), window.innerWidth];})()")
    await shot("allstop-390.png")

    first = await js("window.__played.length")
    await asyncio.sleep(4.0)
    later = await js("window.__played.length")
    out["已播段數"] = [first, later]
    out["會自動續播"] = bool(first and later and later > first)
    out["進度有更新"] = await js("document.getElementById('allstopN').textContent.trim()")
    out["已播檔頭"] = await js("window.__played.slice(0,6)")

    # 3) 按浮動鍵即停
    await js("document.getElementById('allstop').click()")
    await asyncio.sleep(0.5)
    out["停後"] = await js("""(function(){
      return { bar: document.getElementById('allstop').classList.contains('on'),
               rows: document.querySelectorAll('#alllist .arow.playing').length,
               stillPlaying: !!(window.__cur && !window.__cur.paused),
               btnOn: document.getElementById('allplay').classList.contains('onplay'),
               btnTx: document.getElementById('allplay').textContent.trim() };
    })()""")
    st = out["停後"] or {}
    out["停止鍵消失"] = (not st.get("bar") and st.get("rows") == 0
                     and not st.get("stillPlaying") and not st.get("btnOn")
                     and st.get("btnTx") == "▶ 播放全部")
    n_after_stop = await js("window.__played.length")
    await asyncio.sleep(2.0)
    out["停後不再播"] = await js("window.__played.length") == n_after_stop

    # 4) 再按頁頂按鈕同樣停
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.6)
    out["第二輪播放中"] = await js("document.getElementById('allstop').classList.contains('on')")
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.4)
    out["再按即停"] = await js("!document.getElementById('allstop').classList.contains('on')")

    # 5) 換頁自動收起（不會留在下一頁）
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.5)
    await call("Page.navigate", {"url": BASE + "#/all/grammar"}, sid)
    await wait_until("document.querySelectorAll('#alllist .gacc').length")
    out["換頁後收起"] = await js("!document.getElementById('allstop').classList.contains('on')")

    # 5b) 全程只用一個 <audio>：iOS Safari 每段 new Audio() 會在幾十段後卡死
    await call("Page.navigate", {"url": BASE + "#/all/vocab"}, sid)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    await js("""(function(){
      window.__audioNew = 0;
      var O = window.Audio;
      window.Audio = function(u){ window.__audioNew++; return new O(u); };
      window.Audio.prototype = O.prototype;
      var p = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function(){ window.__cur = this;
        window.__played.push(String(this.src||'').split('/audio/').pop());
        return p.apply(this, arguments); };
      window.__played = window.__played || [];
    })()""")
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(1.0)
    out["建立音檔元素數"] = await js("window.__audioNew")
    out["單一播放器"] = (out["建立音檔元素數"] is not None and out["建立音檔元素數"] <= 1)

    # 5c) watchdog：播到一半被系統打斷（paused 又冇 ended），會自動接下一項
    before = await js("document.getElementById('allstopN').textContent.trim()")
    await js("if (window.__cur) window.__cur.pause()")
    await asyncio.sleep(3.2)
    after = await js("document.getElementById('allstopN').textContent.trim()")
    out["打斷前後"] = [before, after]
    out["打斷後自動續播"] = bool(before and after and before != after
                              and await js("document.getElementById('allstop').classList.contains('on')"))
    await js("document.getElementById('allstop').click()")
    await asyncio.sleep(0.3)

    # 7) 由某一項開始順播：點字詞本身（不是 ☆、不是喇叭）
    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/all/vocab"}, sid)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    picked = await js("""(function(){
      window.__played = [];
      var rows = document.querySelectorAll('#alllist .arow');
      var r = rows[99] || rows[rows.length-1];
      var sp = r.querySelector('.spk');
      r.querySelector('.ak').click();
      return { total: rows.length,
               audio: sp ? sp.getAttribute('data-audio') : null,
               text: (r.querySelector('.ak b')||{}).innerText };
    })()""")
    await asyncio.sleep(1.2)
    out["點字詞起播"] = {
        "所點字詞": picked["text"],
        "第一段": await js("window.__played[0]"),
        "該行音檔": picked["audio"],
        "進度": await js("document.getElementById('allstopN').textContent.trim()"),
        "浮動鍵": await js("document.getElementById('allstop').classList.contains('on')"),
        "頁頂按鈕": await js("document.getElementById('allplay').textContent.trim()"),
    }
    t = out["點字詞起播"]
    first = (t["第一段"] or "").split("?")[0]
    rowfile = (t["該行音檔"] or "").split("/")[-1]
    out["由所點那項開始"] = bool(rowfile and first == rowfile and t["進度"].startswith("100／"))
    await js("document.getElementById('allstop').click()")
    await asyncio.sleep(0.3)

    # 6) 360px 無溢出
    await viewport(360)
    await call("Page.navigate", {"url": BASE + "#/all/vocab"}, sid)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.7)
    out["360"] = await js("(function(){var b=document.getElementById('allstop').getBoundingClientRect();"
                          "return {visible: document.getElementById('allstop').classList.contains('on'),"
                          " left: Math.round(b.left), right: Math.round(b.right),"
                          " iw: window.innerWidth, sw: document.documentElement.scrollWidth};})()")
    out["360無溢出"] = bool(out["360"] and out["360"]["left"] >= 0
                          and out["360"]["right"] <= out["360"]["iw"]
                          and out["360"]["sw"] <= out["360"]["iw"] + 1)
    await js("document.getElementById('allstop').click()")

    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()

asyncio.run(main())
