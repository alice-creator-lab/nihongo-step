#!/usr/bin/env python3
"""驗證詞語總表：同一詞只保留最早出現的一課。

用法： python3 tools/test_vocab_dedupe.py [http://127.0.0.1:8934/]
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
if not os.path.exists(CHROME):
    CHROME = "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8934/"
PORT = int(os.environ.get("CDP_PORT", "9381"))
EXPECT = int(os.environ.get("EXPECT", "983"))


async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=430,900",
                             f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-vdedup-" + str(os.getpid()), "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version")); break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def send(m, p, sid=None):
        seq[0] += 1; mid = seq[0]
        msg = {"id": mid, "method": m, "params": p or {}}
        if sid: msg["sessionId"] = sid
        await ws.send(json.dumps(msg)); return mid

    async def wait(mid, t=30):
        end = time.time() + t
        while time.time() < end:
            try: raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.time()))
            except asyncio.TimeoutError: return None
            m = json.loads(raw)
            if m.get("id") == mid: return m
        return None

    async def call(m, p=None, sid=None, t=30): return await wait(await send(m, p, sid), t)

    tgt = await call("Target.getTargets")
    tid = [t["targetId"] for t in tgt["result"]["targetInfos"] if t["type"] == "page"][0]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Page.enable", {}, sid); await call("Runtime.enable", {}, sid)
    await call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def js(e):
        r = await call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True}, sid)
        if not r or "result" not in r: return None
        return r["result"].get("result", {}).get("value")

    fails = []

    def check(name, got, want):
        ok = want(got) if callable(want) else got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got))
        if not ok: fails.append(name)

    await call("Page.navigate", {"url": BASE + "index.html#/all/vocab"}, sid)
    for _ in range(40):
        if await js("document.querySelectorAll('#alllist .arow').length"): break
        await asyncio.sleep(1)

    check("版本", await js("(document.querySelector('#verTag')||{}).innerText"), lambda s: s and s.startswith("v17"))
    check("項數", await js("document.querySelectorAll('#alllist .arow').length"), EXPECT)
    check("計數文字", await js("(document.querySelector('#allcnt')||{}).innerText"), "共 %d 項 · 40 課" % EXPECT)

    # 畫面上不應再有同一詞兩次（同漢字＋同假名）
    dup = await js("""(function(){
      var seen = {}, dup = [];
      document.querySelectorAll('#alllist .arow').forEach(function(r){
        var k = (r.querySelector('.ak b')||{}).innerText || '';
        var s = (r.querySelector('.ak span')||{}).innerText || '';
        var key = k + '|' + s;
        if (seen[key]) dup.push(key); else seen[key] = 1;
      });
      return dup.slice(0, 8).join(' , ');
    })()""")
    check("無重複列", dup, "")

    # 保留最早一課
    def lesson_of(word):
        return """(function(){
          var rows = document.querySelectorAll('#alllist .arow');
          for (var i=0;i<rows.length;i++){
            var b=(rows[i].querySelector('.ak b')||{}).innerText||'';
            if (b==='%s') return rows[i].querySelector('.al').innerText;
          }
          return null;
        })()""" % word

    check("帰る 在 L06", await js(lesson_of("帰る")), "L06")
    check("聞く 在 L07", await js(lesson_of("聞く")), "L07")
    check("傘 在 L02", await js(lesson_of("傘")), "L02")
    check("料理 在 L07", await js(lesson_of("料理")), "L07")
    check("時計 在 L02", await js(lesson_of("時計")), "L02")

    # 一課寫漢字、一課只寫假名：同一個詞只留最早一課（L06 明後日 / L13 あさって）
    check("明後日 在 L06", await js(lesson_of("明後日")), "L06")
    check("あさって 只一條", await js("""(function(){
      var n = 0;
      document.querySelectorAll('#alllist .arow').forEach(function(r){
        var k = (r.querySelector('.ak b')||{}).innerText || '';
        var s = (r.querySelector('.ak span')||{}).innerText || '';
        if (k === 'あさって' || s === 'あさって') n++;
      });
      return n;
    })()"""), 1)
    # 同音異字不算同一詞（早い／速い はやい 各自保留）
    check("はやい 兩條", await js("""(function(){
      var n = 0;
      document.querySelectorAll('#alllist .arow').forEach(function(r){
        var k = (r.querySelector('.ak b')||{}).innerText || '';
        var s = (r.querySelector('.ak span')||{}).innerText || '';
        if (k === 'はやい' || s === 'はやい') n++;
      });
      return n;
    })()"""), 2)

    # 搜尋只回一條
    await js("var q=document.querySelector('#allq'); q.value='かえります'; q.dispatchEvent(new Event('input',{bubbles:true})); 1")
    await asyncio.sleep(0.8)
    check("搜かえります 一條", await js("document.querySelectorAll('#alllist .arow').length"), 1)
    check("搜かえります 是帰る", await js("(document.querySelector('#alllist .ak b')||{}).innerText"), "帰る")
    await js("var q=document.querySelector('#allq'); q.value=''; q.dispatchEvent(new Event('input',{bubbles:true})); 1")
    await asyncio.sleep(0.6)

    if os.environ.get("SHOT"):
        r = await call("Page.captureScreenshot", {"format": "png"}, sid)
        open(os.environ["SHOT"], "wb").write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close(); proc.terminate()


asyncio.run(main())
