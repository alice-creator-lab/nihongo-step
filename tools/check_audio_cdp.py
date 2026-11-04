#!/usr/bin/env python3
"""用 CDP 檢查人聲音檔有無接上：文法段、文法總表、聽力、對話。

用法： python3 tools/check_audio_cdp.py [http://127.0.0.1:8899/]
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
PORT = int(os.environ.get("CDP_PORT", "9333"))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-prof-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]
    reqs = []

    async def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time()))
            except asyncio.TimeoutError:
                return
            m = json.loads(raw)
            if m.get("method") == "Network.requestWillBeSent":
                reqs.append(m["params"]["request"]["url"])

    async def call(method, params=None, sid=None, timeout=8):
        seq[0] += 1
        msg = {"id": seq[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time()))
            except asyncio.TimeoutError:
                return None
            m = json.loads(raw)
            if m.get("method") == "Network.requestWillBeSent":
                reqs.append(m["params"]["request"]["url"])
            if m.get("id") == seq[0]:
                return m
        return None

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Network.enable", {}, sid)
    await call("Runtime.enable", {}, sid)

    async def js(expr, tries=2):
        for _ in range(tries):
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                "awaitPromise": True}, sid, timeout=20)
            if r and "result" in r:
                return r["result"].get("result", {}).get("value")
        return None

    async def visit(hash_, wait=1.6):
        await js("location.hash='%s'; 1" % hash_)
        await pump(wait)

    async def wait_until(expr, secs=25):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await pump(0.4)
        return None

    INSTR = ("(function(){ window.__played=[]; window.__rates=[];"
             "var p=HTMLMediaElement.prototype.play;"
             "HTMLMediaElement.prototype.play=function(){window.__played.push(String(this.src||'').split('/audio/').pop());"
             "window.__rates.push(this.playbackRate); return p.apply(this,arguments);};"
             "var s=window.speechSynthesis; if(s){var q=s.speak.bind(s); s.speak=function(u){window.__played.push('TTS:'+u.text); q(u);};}"
             "return 1; })()")

    await call("Page.navigate", {"url": BASE}, sid)
    await asyncio.sleep(3)

    out = {}
    out["首頁載入"] = await wait_until("document.querySelectorAll('#grammarCard, a[href=\"#/all/grammar\"]').length")

    # 1) 文法總表
    await visit("#/all/grammar", 2.5)
    await wait_until("document.querySelectorAll('#alllist .gex .spk').length")
    await js(INSTR)
    out["文法總表 例子喇叭"] = await js("document.querySelectorAll('#alllist .gex .spk').length")
    out["文法總表 有音檔"] = await js("document.querySelectorAll('#alllist .gex .spk[data-audio]').length")
    await js("document.querySelectorAll('#alllist .gex .spk')[0].click(); 1")
    await pump(1.2)
    out["文法總表 播放"] = await js("window.__played.slice(-1)")
    out["文法總表 用機械聲"] = await js("window.__played.some(x=>x.indexOf('TTS:')===0)")

    # 2) 課內文法段
    await visit("#/l/L01/grammar", 2.5)
    await wait_until("document.querySelectorAll('#seg .exrow .spk').length")
    await js(INSTR)
    out["課內文法 例子喇叭"] = await js("document.querySelectorAll('#seg .exrow .spk').length")
    out["課內文法 有音檔"] = await js("document.querySelectorAll('#seg .exrow .spk[data-audio]').length")
    await js("document.querySelectorAll('#seg .exrow .spk')[1].click(); 1")
    await pump(1.2)
    out["課內文法 播放"] = await js("window.__played.slice(-1)")
    out["課內文法 用機械聲"] = await js("window.__played.some(x=>x.indexOf('TTS:')===0)")

    # 3) 聽力（正常 + 慢速）
    await visit("#/l/L01/exercises", 2.5)
    await js("(function(){var b=[].find.call(document.querySelectorAll('button'),function(x){return x.textContent.indexOf('聽力')>=0;}); if(b){b.click(); return 1;} return 0;})()")
    await wait_until("document.getElementById('lplay')")
    await js(INSTR)
    await js("document.getElementById('lplay').click(); 1")
    await pump(1.2)
    out["聽力 播放"] = await js("[window.__played.slice(-1)[0], window.__rates.slice(-1)[0]]")
    await js("(function(){window.__played=[]; window.__rates=[]; document.getElementById('lslow').click(); return 1;})()")
    await pump(1.2)
    out["聽力 慢速"] = await js("[window.__played.slice(-1)[0], window.__rates.slice(-1)[0]]")

    # 4) 對話整段（正常）
    await visit("#/l/L01/dialogue", 2.5)
    await wait_until("document.querySelector('[data-play]')")
    await js(INSTR)
    await js("document.querySelector('[data-play]').click(); 1")
    await pump(1.5)
    out["對話 播放"] = await js("window.__played.slice(-1)")

    # 5) 對話整段（慢速：改放慢人聲，不用機械聲）
    await js("localStorage.setItem('ngs-slow','1'); location.hash='#/l/L01/dialogue'; 1")
    await call("Page.reload", {}, sid)
    await asyncio.sleep(3)
    await wait_until("document.querySelector('[data-play]')")
    await js(INSTR)
    await js("document.querySelector('[data-play]').click(); 1")
    await pump(1.5)
    out["對話 慢速"] = await js("[window.__played.slice(-1)[0], window.__rates.slice(-1)[0]]")
    await js("localStorage.removeItem('ngs-slow'); 1")

    # 6) 跟讀：示範按鈕也要用會話人聲（假名文字交給系統合成會讀成 ha）
    await visit("#/l/L01/dialogue", 2.5)
    await wait_until("document.querySelector('[data-speak]')")
    await js("document.querySelector('[data-speak]').click(); 1")
    await wait_until("document.getElementById('spkModel')")
    await js(INSTR)
    await js("document.getElementById('spkModel').click(); 1")
    await pump(1.5)
    out["跟讀 示範"] = await js("[window.__played.slice(-1)[0], window.__rates.slice(-1)[0]]")
    out["跟讀 用機械聲"] = await js("window.__played.some(x=>x.indexOf('TTS:')===0)")

    out["頁面錯誤"] = await js("(window.__errs||[]).length")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()


asyncio.run(main())
