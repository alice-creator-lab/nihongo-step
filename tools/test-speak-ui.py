#!/usr/bin/env python3
"""檢查「自動辨識」按鈕的狀態：收音完結之後，按鈕一定要離開「■ 停止並辨識」。

以往只靠 MediaRecorder 的 stop 事件改按鈕文字，iOS 唔派事件時按鈕就會卡死。
這支腳本用 Chromium 的假麥克風（一段響音＋長靜音）跑兩個情境：
  1. normal  —— 正常收到 stop 事件
  2. nostop  —— 攔住 stop 事件（模擬 iOS 唔派事件），靠看門狗收尾
兩個情境都要求：按停之後 5 秒內按鈕變成「辨識中…」或「● 自動辨識」。

用法：python3 tools/test-speak-ui.py
（第一次要由 CDN 下載約 40MB 模型，之後沿用 --user-data-dir 的快取。）
"""
import asyncio, http.server, json, os, socket, struct, subprocess, sys, tempfile, threading, time, urllib.request
import math, wave
import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME_CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
PORT = int(os.environ.get("CDP_PORT", "9412"))
PROFILE = "/tmp/ngs-speak-ui-profile"

NOSTOP = r"""
(function(){
  var Orig = window.MediaRecorder;
  window.MediaRecorder = function(stream, opts){
    var mr = new Orig(stream, opts);
    var realAdd = mr.addEventListener.bind(mr);
    var val = null;
    Object.defineProperty(mr, 'onstop', { configurable: true,
      get: function(){ return val; }, set: function(v){ val = v; } });
    mr.addEventListener = function(t, fn, o){ if (t === 'stop') return; realAdd(t, fn, o); };
    return mr;
  };
  window.__patchedNoStop = 1;
})()
"""


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def make_wav(path):
    """5 秒響音（夠大聲觸發 VAD）＋40 秒靜音"""
    sr = 16000
    frames = [int(0.35 * 32767 * math.sin(2 * math.pi * 220 * i / sr)) for i in range(sr * 5)]
    frames += [0] * (sr * 40)
    w = wave.open(path, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(b"".join(struct.pack("<h", f) for f in frames))
    w.close()


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    port = free_port()
    handler = lambda *a, **k: Quiet(*a, directory=ROOT, **k)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/" % port


async def run_scenario(base, wav, mode):
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        "--use-file-for-fake-audio-capture=" + wav,
        "--remote-debugging-port=%d" % PORT, "--user-data-dir=" + PROFILE, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT)); break
        except Exception:
            time.sleep(0.3)
    if not ver:
        proc.terminate(); return None, "Chromium 起唔到"
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def call(method, params=None, sid=None, timeout=40):
        seq[0] += 1
        msg = {"id": seq[0], "method": method, "params": params or {}}
        if sid: msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time()))
            except asyncio.TimeoutError:
                return None
            m = json.loads(raw)
            if m.get("id") == seq[0]:
                return m
        return None

    async def js(expr, timeout=40):
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                            "awaitPromise": True}, sid, timeout=timeout)
        if r and "result" in r:
            return r["result"].get("result", {}).get("value")
        return None

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Runtime.enable", {}, sid)
    await call("Page.enable", {}, sid)
    await call("Browser.grantPermissions",
               {"origin": base.rstrip("/"), "permissions": ["audioCapture"]})
    if mode == "nostop":
        await call("Page.addScriptToEvaluateOnNewDocument", {"source": NOSTOP}, sid)

    await call("Page.navigate", {"url": base + "#/l/L01/dialogue"}, sid)
    await asyncio.sleep(3)
    await js("document.querySelector('[data-speak]').click(); 1")
    await asyncio.sleep(0.8)
    if not await js("!!document.getElementById('spkAuto')"):
        proc.terminate(); await ws.close(); return None, "找不到 #spkAuto"

    label = "(function(){var b=document.getElementById('spkAuto'); return b.textContent+'|'+(b.disabled?'off':'on');})()"
    await js("document.getElementById('spkAuto').click(); 1")
    # 等模型下載完、真正開始收音（按鈕變「停止並辨識」）
    started = None
    for _ in range(240):
        v = await js(label)
        if v and v.startswith("■"):
            started = v; break
        await asyncio.sleep(0.5)
    if not started:
        proc.terminate(); await ws.close(); return None, "一直未開始收音（模型下載失敗？）"

    await js("document.getElementById('spkAuto').click(); 1")   # 手動按停
    deadline = time.time() + 5
    while time.time() < deadline:
        v = await js(label)
        if v and not v.startswith("■"):
            proc.terminate(); await ws.close(); return v, None
        await asyncio.sleep(0.25)
    final = await js(label)
    proc.terminate(); await ws.close()
    return None, "按停 5 秒後按鈕仍是「停止並辨識」（最後狀態：%s）" % final


def main():
    if not CHROME:
        sys.exit("找不到 Chromium（見 CHROME_CANDIDATES）")
    tmp = tempfile.mkdtemp(prefix="ngs-speak-")
    wav = os.path.join(tmp, "fake-speech.wav")
    make_wav(wav)
    srv, base = serve()
    print("serve", base)
    bad = 0
    for mode in ("normal", "nostop"):
        state, err = asyncio.run(run_scenario(base, wav, mode))
        if err:
            bad += 1
            print("FAIL  %-7s %s" % (mode, err))
        else:
            print("PASS  %-7s 按停後按鈕 → %s" % (mode, state))
    srv.shutdown()
    print("全部通過" if not bad else "%d 項未通過" % bad)
    sys.exit(1 if bad else 0)


main()
