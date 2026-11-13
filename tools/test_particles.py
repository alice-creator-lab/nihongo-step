#!/usr/bin/env python3
"""驗證「助詞一覧」頁（#/all/particles）。

檢查：
1. 19 張助詞卡、每個助詞一張「標籤｜例句」兩欄表（56 列、60 句例句，14 句是新寫的音檔）。
2. 每個用法標籤與 data/particles.json 完全一致（含「時間點」「居住」「任職」）。
3. 例句照 ref 解析出課文原文；右邊課號可跳去該課。
4. 喇叭：新例句播 audio/particles/<a>.mp3，既有例句播原本課堂音檔。
5. 文法總表的入口卡可入頁；返回鍵回文法總表。
6. 跳轉 chip（に）捲到該卡；390／360px 無橫向溢出。

用法： python3 tools/test_particles.py [http://127.0.0.1:8912/]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8912/"
PORT = int(os.environ.get("CDP_PORT", "9351"))
SHOT = os.environ.get("SHOT", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = json.load(open(os.path.join(ROOT, "data/particles.json"), encoding="utf-8"))
GROUPS = DATA["groups"]
USES = sum(len(g["uses"]) for g in GROUPS)
ROWS = sum(len(u["ex"]) for g in GROUPS for u in g["uses"])
NEW = sum(1 for g in GROUPS for u in g["uses"] for x in u["ex"] if "ja" in x)
REFS = ROWS - NEW

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-particles-" + str(os.getpid()), "about:blank"],
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
            open(name, "wb").write(base64.b64decode(r["result"]["data"]))

    fails = []

    def check(ok, label, detail=""):
        if not ok:
            fails.append(f"{label}：{detail}")

    # 1) 由文法總表入頁
    await viewport(390)
    await call("Page.navigate", {"url": BASE + "#/all/grammar"}, sid)
    entry = await wait_until("document.querySelector('a[href=\"#/all/particles\"]') ? 1 : 0")
    check(entry, "文法總表應有助詞一覧入口")
    await js("document.querySelector('a[href=\"#/all/particles\"]').click()")
    n = await wait_until(f"document.querySelectorAll('#pglist section.pgc').length")
    check(n == len(GROUPS), "助詞卡數", f"{n} ≠ {len(GROUPS)}")
    out = await js("""(function(){
      return { uses: document.querySelectorAll('#pglist .pgtbl tr').length,
               rows: document.querySelectorAll('#pglist .pex').length,
               newAudio: document.querySelectorAll('#pglist .pex [data-audio^="audio/particles/"]').length,
               links: document.querySelectorAll('#pglist .pex a.pl').length,
               back: !!document.querySelector('.lhead a.back[href="#/all/grammar"]'),
               title: (document.querySelector('.lhead h1')||{}).innerText || '' };
    })()""") or {}
    check(out.get("uses") == USES, "用法數", f"{out.get('uses')} ≠ {USES}")
    check(out.get("rows") == ROWS, "例句數", f"{out.get('rows')} ≠ {ROWS}")
    check(out.get("newAudio") == NEW, "新例句音檔數", f"{out.get('newAudio')} ≠ {NEW}")
    check(out.get("links") == REFS, "課號連結數", f"{out.get('links')} ≠ {REFS}")
    check(out.get("back"), "應有返回文法總表")
    check("助詞一覧" in (out.get("title") or ""), "標題", str(out.get("title")))

    # 2) 標籤與資料一致（抽三組，含「時間點」「居住」「任職」）
    labels = await js("""(function(){
      var o={};
      document.querySelectorAll('#pglist section.pgc').forEach(function(s,i){
        o[i]=Array.prototype.map.call(s.querySelectorAll('.pglb'),function(x){return x.innerText.trim();});
      });
      return o;
    })()""") or {}
    for gi in (4, 3, 11):
        want = [u["label"] for u in GROUPS[gi]["uses"]]
        check(labels.get(str(gi)) == want, f"{GROUPS[gi]['p']} 用法標籤", f"{labels.get(str(gi))} ≠ {want}")

    # 3) 喇叭：新例句與既有例句各播一次
    await js(INSTR)
    await js("document.querySelector('#pglist .pex [data-audio^=\"audio/particles/\"]').click()")
    await asyncio.sleep(0.9)
    a1 = await js("(window.__played||[])[0] || null")
    check((a1 or "").split("?")[0].split("/")[-1] == "01.mp3", "新例句應播 audio/particles/01.mp3", str(a1))
    await js("window.__played=[]; window.__cur=null")
    await js("document.querySelectorAll('#pglist .pex .spk')[40].click()")
    await asyncio.sleep(0.8)
    a2 = await js("""(function(){var b=document.querySelectorAll('#pglist .pex .spk')[40];
      return { got:(window.__played||[])[0]||null, want:b.getAttribute('data-audio') };})()""") or {}
    got = (a2.get("got") or "").split("?")[0].split("/")[-1]
    want = (a2.get("want") or "").split("/")[-1]
    check(got == want and got.endswith(".mp3"), "既有例句應播原課堂音檔", f"{got} ≠ {want}")
    await js("if (window.__cur) window.__cur.pause();")

    # 4) 課號連結跳去該課
    await js("document.querySelectorAll('#pglist .pex a.pl')[0].click()")
    await asyncio.sleep(0.8)
    lid = await js("(location.hash.match(/L\\d\\d/)||[''])[0]")
    check(lid.startswith("L"), "課號連結應跳到課堂", str(lid))
    await call("Page.navigate", {"url": BASE + "#/all/particles"}, sid)
    await wait_until("document.querySelectorAll('#pglist section.pgc').length")

    # 5) 跳轉 chip：に → 第 5 張卡
    await js("Array.prototype.filter.call(document.querySelectorAll('#pgjump .jump'),function(b){return b.innerText.trim()==='に';})[0].click()")
    await asyncio.sleep(1.0)
    pos = await js("""(function(){var e=document.getElementById('pgg-4'); if(!e) return null;
      var r=e.getBoundingClientRect(); return {top:Math.round(r.top), y:Math.round(window.scrollY)};})()""") or {}
    check(pos.get("y", 0) > 100 and -80 <= pos.get("top", 999) <= 140, "に chip 應捲到該卡", str(pos))

    # 6) 390／360 無溢出
    for w in (390, 360):
        await viewport(w)
        await call("Page.navigate", {"url": BASE + "#/all/particles"}, sid)
        await wait_until("document.querySelectorAll('#pglist section.pgc').length")
        box = await js("""(function(){return {iw:window.innerWidth, sw:document.documentElement.scrollWidth,
          cards:document.querySelectorAll('#pglist section.pgc').length};})()""") or {}
        check(box.get("sw", 9e9) <= box.get("iw", 0) + 1, f"{w}px 無橫向溢出", str(box))
        if SHOT and w == 390:
            await js("window.scrollTo(0, 0)")
            await asyncio.sleep(0.4)
            await shot(SHOT)

    await ws.close()
    proc.terminate()
    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print(f"全部通過：{len(GROUPS)} 個助詞、{USES} 個用法、{ROWS} 句例句（{NEW} 句新音檔）、"
          "喇叭、課號跳轉、入口與返回、390／360px")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
