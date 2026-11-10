#!/usr/bin/env python3
"""驗證練習本：單字／句子分頁，以及文法例句的 ☆ 收藏。

用法： SHOT=/tmp/x.png python3 tools/test_note_sent.py [http://127.0.0.1:8934/]
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8934/"
PORT = int(os.environ.get("CDP_PORT", "9357"))

JA = "宿題をして、食堂で昼ごはんを食べます。"
SEED = {"v": 1, "items": [
    {"type": "word", "id": "L01", "vi": 0, "kanji": "学生", "kana": "がくせい", "zh": "學生",
     "pos": "名詞", "audio": "", "src": "L01", "at": 3},
    {"type": "sentence", "id": "L12", "ja": JA, "kana": "しゅくだいをして、しょくどうでひるごはんをたべます。",
     "zh": "先做功課，然後在食堂吃午飯。", "audio": "audio/L12-g5-e2.mp3", "src": "L12 · て形連接：順序、手段、理由", "at": 2},
]}


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=430,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-notesent-" + str(os.getpid()), "about:blank"],
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

    async def send(method, params, sid=None):
        seq[0] += 1
        mid = seq[0]
        msg = {"id": mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        return mid

    async def wait(mid, timeout=25):
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.time()))
            except asyncio.TimeoutError:
                return None
            m = json.loads(raw)
            if m.get("id") == mid:
                return m
        return None

    async def call(method, params=None, sid=None, timeout=25):
        return await wait(await send(method, params, sid), timeout)

    tgt = await call("Target.getTargets")
    tid = [t["targetId"] for t in tgt["result"]["targetInfos"] if t["type"] == "page"][0]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Page.enable", {}, sid)
    await call("Runtime.enable", {}, sid)
    await call("Emulation.setDeviceMetricsOverride",
               {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def js(expr):
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, sid)
        if not r or "result" not in r:
            return None
        return r["result"].get("result", {}).get("value")

    fails = []

    def check(name, got, want):
        ok = want(got) if callable(want) else got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got))
        if not ok:
            fails.append(name)

    await call("Page.navigate", {"url": BASE + "index.html#/note"}, sid)
    await asyncio.sleep(4)
    await js("localStorage.setItem('ngs-notebook-v1', %s)" % json.dumps(json.dumps(SEED)))
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(25):
        if await js("!!document.querySelector('#nbTabs')"):
            break
        await asyncio.sleep(1)

    # 1) 分頁
    check("分頁兩個", await js("document.querySelectorAll('#nbTabs button').length"), 2)
    check("單字分頁數字", await js("document.querySelectorAll('#nbTabs button')[0].innerText.trim()"), "單字 1")
    check("句子分頁數字", await js("document.querySelectorAll('#nbTabs button')[1].innerText.trim()"), "句子 1")
    check("預設在單字", await js("document.querySelectorAll('#notebody .nrow').length"), 1)
    check("預設無句子列", await js("document.querySelectorAll('#notebody .nrow.sent').length"), 0)

    # 2) 切到句子
    await js("document.querySelectorAll('#nbTabs button')[1].click()")
    await asyncio.sleep(0.6)
    check("句子分頁有句子列", await js("document.querySelectorAll('#notebody .nrow.sent').length"), 1)
    check("句子列顯示日文", await js("((document.querySelector('#notebody .nrow.sent .nsj')||{}).innerText||'').indexOf('宿題')>=0"), True)
    check("句子列有音檔", await js("(document.querySelector('#notebody .nrow.sent .spk')||{}).dataset ? document.querySelector('#notebody .nrow.sent .spk').getAttribute('data-audio') : ''"), "audio/L12-g5-e2.mp3")
    check("寬度無溢出", await js("document.documentElement.scrollWidth <= 390"), True)

    # 3) 句子卡片練習
    await js("document.querySelector('#nbStart').click()")
    await asyncio.sleep(0.8)
    check("卡片出日文句子", await js("((document.querySelector('.fq')||{}).innerText||'').indexOf('宿題')>=0"), True)

    # 4) 文法頁的 ☆
    await call("Page.navigate", {"url": BASE + "index.html#/l/L12/grammar"}, sid)
    await asyncio.sleep(1.5)
    await js("localStorage.setItem('ngs-notebook-v1', JSON.stringify({v:1, items:[]})); 1")
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(25):
        if await js("document.querySelectorAll('.gsec .nbk[data-gs]').length"):
            break
        await asyncio.sleep(1)
    stars = await js("document.querySelectorAll('.gsec .nbk[data-gs]').length")
    exs = await js("document.querySelectorAll('.gsec .ex .exrow').length")
    check("每句都有 ☆", stars, lambda n: n == exs and n > 0)
    check("首次是空心", await js("document.querySelectorAll('.gsec .nbk[data-gs]')[0].textContent.trim()"), "☆")
    await js("document.querySelectorAll('.gsec .nbk[data-gs]')[0].click()")
    await asyncio.sleep(0.5)
    check("按下變實心", await js("document.querySelectorAll('.gsec .nbk[data-gs]')[0].textContent.trim()"), "★")
    check("已寫入句子", await js("JSON.parse(localStorage.getItem('ngs-notebook-v1')).items.filter(function(x){return x.type==='sentence'}).length"), 1)
    first_ja = await js("(document.querySelectorAll('.gsec .exrow')[0].querySelector('.ja')||{}).innerText||''")
    check("句子內容與畫面一致", await js("(JSON.parse(localStorage.getItem('ngs-notebook-v1')).items[0]||{}).ja"), first_ja)
    check("句子帶音檔", await js("(JSON.parse(localStorage.getItem('ngs-notebook-v1')).items[0]||{}).audio"), lambda a: bool(a) and a.startswith("audio/L12-g"))
    check("句子有出處", await js("(JSON.parse(localStorage.getItem('ngs-notebook-v1')).items[0]||{}).src"), lambda s: bool(s) and s.startswith("L12 · "))

    # 4b) 文法總表也可以收藏
    await js("localStorage.setItem('ngs-notebook-v1', JSON.stringify({v:1, items:[]})); 1")
    await call("Page.reload", {"ignoreCache": True}, sid)
    await asyncio.sleep(1.5)
    await js("location.hash='#/all/grammar'; 1")
    for _ in range(20):
        if await js("document.querySelectorAll('.gacc .gex .nbk').length"): break
        await asyncio.sleep(0.6)
    n0 = await js("document.querySelectorAll('.gacc .gex .nbk').length")
    check("總表每句有 ☆", n0, lambda n: bool(n))
    await js("document.querySelectorAll('.gacc .gex .nbk')[0].click()")
    await asyncio.sleep(0.5)
    check("總表按下變實心", await js("document.querySelectorAll('.gacc .gex .nbk')[0].textContent.trim()"), "★")
    check("總表收藏成句子", await js("JSON.parse(localStorage.getItem('ngs-notebook-v1')).items.filter(function(x){return x.type==='sentence'}).length"), 1)
    await js("document.querySelectorAll('.gacc .gex .nbk')[0].click()")
    await asyncio.sleep(0.4)
    check("再按可取消", await js("JSON.parse(localStorage.getItem('ngs-notebook-v1')).items.length"), 0)
    await js("localStorage.setItem('ngs-notebook-v1', JSON.stringify({v:1, items:[{type:'sentence',id:'L12',ja:%s,kana:'',zh:'測試',audio:'',src:'L12',at:1}]})); 1" % json.dumps(JA))

    # 5) 回到練習本看分頁數字
    await call("Page.navigate", {"url": BASE + "index.html#/note"}, sid)
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(30):
        if await js("document.querySelectorAll('#nbTabs button').length"):
            break
        await asyncio.sleep(1)
    check("練習本句子 1", await js("((document.querySelectorAll('#nbTabs button')[1]||{}).innerText||'').trim()"), "句子 1")

    if os.environ.get("SHOT"):
        r = await call("Page.captureScreenshot", {"format": "png"}, sid)
        with open(os.environ["SHOT"], "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
