#!/usr/bin/env python3
"""驗證「副詞一覧／連接詞一覧 → 播放全部」。

檢查：
- 頁頂有 ▶ 播放全部，旁邊寫總項數
- 按下後逐段播（檔序＝畫面次序）、浮動停止鍵出現、顯示「第幾項／共幾項」、該行高亮
- 按浮動鍵即停：鍵消失、高亮清空、按鈕還原、之後不再播
- 再按頁頂鍵同樣停
- 點左欄的詞可以由那一行開始順播
- 換頁會自動收起
- 360px 無橫向溢出

用法：python3 tools/test_advconj_playall.py http://127.0.0.1:8912/
"""
import asyncio, base64, json, os, random, re, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8912/").rstrip("/") + "/"
PORT = 9300 + random.randint(0, 400)

INSTR = ("(function(){ window.__played=[];"
         "var p=HTMLMediaElement.prototype.play;"
         "HTMLMediaElement.prototype.play=function(){window.__cur=this;"
         "window.__played.push(String(this.src||'').split('/audio/').pop()); return p.apply(this,arguments);};"
         "return 1; })()")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}",
         "--user-data-dir=/tmp/cdp-acplay-" + str(os.getpid()), "about:blank"],
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

    data = json.load(open(os.path.join(ROOT, "data/advconj.json"), encoding="utf-8"))

    def sorted_audio(kind):
        """畫面次序＝照課號排序（同課維持原次序），同 app 的做法一致。"""
        its = data[kind]["items"]
        its = sorted(its, key=lambda a: int(re.sub(r"\D", "", str(a.get("l") or "")) or 0))
        return [i["a"] + ".mp3" for i in its]
    out = {}
    fail = []

    def check(ok, msg, extra=""):
        if not ok:
            fail.append(msg + (("：" + str(extra)) if extra else ""))
            print("  FAIL", msg, extra)
        else:
            print("  ok  ", msg)

    await viewport(390)

    for kind, path, title in (("adverbs", "#/all/adverbs", "副詞一覧"),
                              ("conjunctions", "#/all/conjunctions", "連接詞一覧")):
        exp = sorted_audio(kind)
        print(f"【{title}】播放全部")
        await call("Page.navigate", {"url": BASE + "?cb=" + kind + path}, sid)
        await wait_until("(document.querySelector('.lhead h1')||{}).textContent.indexOf(%r)===0" % title)
        rows = await wait_until("document.querySelectorAll('#aclist tr[data-k]').length")
        check(rows == len(exp), f"{title} 行數", rows)
        o = {}
        o["版本"] = await js("document.getElementById('verTag').textContent.trim()")
        o["播放全部鍵"] = await js("(function(){var b=document.querySelector('#allplay');"
                                   "return b?b.textContent.trim():null})()")
        o["項數"] = await js("document.getElementById('accnt').textContent.trim()")
        check(o["播放全部鍵"] == "▶ 播放全部", f"{title} 頁頂有播放全部", o["播放全部鍵"])
        check(o["項數"] == f"{len(exp)} 項", f"{title} 項數", o["項數"])

        # 按下播放全部
        await js(INSTR)
        await js("document.getElementById('allplay').click()")
        await asyncio.sleep(1.0)
        o["浮動鍵"] = await js("document.getElementById('allstop').classList.contains('on')")
        o["進度"] = await js("document.getElementById('allstopN').textContent.trim()")
        o["按鈕"] = await js("[document.getElementById('allplay').classList.contains('onplay'),"
                             " document.getElementById('allplay').textContent.trim()]")
        o["高亮行"] = await js("document.querySelectorAll('#aclist tr.playing').length")
        check(o["浮動鍵"], f"{title} 按後出現浮動停止鍵")
        check(o["進度"].startswith("1／" + str(len(exp))), f"{title} 進度顯示", o["進度"])
        check(o["按鈕"] == [True, "■ 停止"], f"{title} 頁頂鍵變停止", o["按鈕"])
        check(o["高亮行"] == 1, f"{title} 只高亮當前一行", o["高亮行"])
        await shot(f"acplay-{kind}-390.png")

        first = await js("window.__played.length")
        await asyncio.sleep(6.0)
        later = await js("window.__played.length")
        o["已播段數"] = [first, later]
        o["已播檔頭"] = await js("window.__played.slice(0,4)")
        check(bool(first and later and later > first), f"{title} 會自動續播", o["已播段數"])
        check(os.path.basename(((o["已播檔頭"] or [""])[0]).split("?")[0]) == exp[0],
              f"{title} 由第一項開始播", o["已播檔頭"])

        # 浮動鍵即停
        await js("document.getElementById('allstop').click()")
        await asyncio.sleep(0.6)
        st = await js("""(function(){
          return { bar: document.getElementById('allstop').classList.contains('on'),
                   rows: document.querySelectorAll('#aclist tr.playing').length,
                   stillPlaying: !!(window.__cur && !window.__cur.paused),
                   btnOn: document.getElementById('allplay').classList.contains('onplay'),
                   btnTx: document.getElementById('allplay').textContent.trim() };
        })()""")
        o["停後"] = st
        check(not st["bar"] and st["rows"] == 0 and not st["stillPlaying"]
              and not st["btnOn"] and st["btnTx"] == "▶ 播放全部",
              f"{title} 按浮動鍵完全停下", st)
        n0 = await js("window.__played.length")
        await asyncio.sleep(2.0)
        check(await js("window.__played.length") == n0, f"{title} 停後不再播")

        # 再按頁頂鍵同樣停
        await js("document.getElementById('allplay').click()")
        await asyncio.sleep(0.7)
        check(await js("document.getElementById('allstop').classList.contains('on')"),
              f"{title} 第二輪播放中")
        await js("document.getElementById('allplay').click()")
        await asyncio.sleep(0.5)
        check(await js("!document.getElementById('allstop').classList.contains('on')"),
              f"{title} 再按即停")

        # 由中間某一行開始
        want = min(5, len(exp) - 1)
        picked = await js("""(function(){
          window.__played = [];
          var rows = document.querySelectorAll('#aclist tr[data-k]');
          var r = rows[%d];
          var sp = r.querySelector('.spk');
          r.querySelector('.aclb').click();
          return { audio: sp ? sp.getAttribute('data-audio') : null };
        })()""" % want)
        await asyncio.sleep(1.2)
        o["點詞起播"] = {
            "第一段": await js("window.__played[0]"),
            "該行音檔": picked["audio"],
            "進度": await js("document.getElementById('allstopN').textContent.trim()"),
        }
        f1 = os.path.basename((o["點詞起播"]["第一段"] or "").split("?")[0])
        rf = (o["點詞起播"]["該行音檔"] or "").split("/")[-1]
        check(bool(rf and f1 == rf and
                   o["點詞起播"]["進度"].startswith(str(want + 1) + "／" + str(len(exp)))),
              f"{title} 點詞由該行起播", o["點詞起播"])
        await js("document.getElementById('allstop').click()")
        await asyncio.sleep(0.4)

        out[title] = o

    # 換頁自動收起
    print("【換頁自動收起】")
    await call("Page.navigate", {"url": BASE + "?cb=z#/all/adverbs"}, sid)
    await wait_until("document.querySelectorAll('#aclist tr[data-k]').length")
    await js(INSTR)
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.6)
    await call("Page.navigate", {"url": BASE + "?cb=x#/all/grammar"}, sid)
    await wait_until("document.querySelectorAll('#alllist .gacc').length")
    check(await js("!document.getElementById('allstop').classList.contains('on')"),
          "換頁後浮動鍵收起")

    # 360px 無溢出
    print("【360px】")
    await viewport(360)
    await call("Page.navigate", {"url": BASE + "?cb=w#/all/adverbs"}, sid)
    await wait_until("document.querySelectorAll('#aclist tr[data-k]').length")
    await js("document.getElementById('allplay').click()")
    await asyncio.sleep(0.8)
    m = await js("""(function(){var b=document.getElementById('allstop').getBoundingClientRect();
      return {visible: document.getElementById('allstop').classList.contains('on'),
              left: Math.round(b.left), right: Math.round(b.right),
              iw: window.innerWidth, sw: document.documentElement.scrollWidth};})()""")
    out["360"] = m
    check(bool(m and m["visible"] and m["left"] >= 0 and m["right"] <= m["iw"]
               and m["sw"] <= m["iw"] + 1), "360px 浮動鍵不出現溢出", m)
    await shot("acplay-360.png")
    await js("document.getElementById('allstop').click()")

    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()
    if fail:
        print("\nFAIL")
        for f in fail:
            print(" -", f)
        return 1
    print("\n全部通過")
    return 0


sys.exit(asyncio.run(main()))
