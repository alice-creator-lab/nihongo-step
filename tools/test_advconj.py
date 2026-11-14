#!/usr/bin/env python3
"""驗收「副詞一覧」(#/all/adverbs) 與「連接詞整合」(#/all/conjunctions)。

檢查：入口卡、行數、每行有喇叭且有音檔、課號連結、音檔 200、390px 無橫向溢出。
用法：python3 tools/test_advconj.py http://127.0.0.1:8912/
"""
import asyncio
import json
import os
import random
import sys
import time
import urllib.request

import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = os.path.expanduser("~/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome")
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8912/").rstrip("/") + "/"
PORT = 9300 + random.randint(0, 400)
FAIL = []


def check(ok, msg, extra=""):
    if not ok:
        FAIL.append(msg + (("：" + extra) if extra else ""))
        print("  FAIL", msg, extra)
    else:
        print("  ok  ", msg)


class Browser:
    def __init__(self):
        self.proc = None
        self.ws = None
        self.seq = 0
        self.sid = None

    async def start(self, width, height, mobile=False, fine=False):
        import subprocess
        udd = f"/tmp/cdp-advconj-{PORT}-{os.getpid()}"
        flags = ["--headless=new", "--no-sandbox", "--disable-gpu",
                 "--autoplay-policy=no-user-gesture-required",
                 f"--remote-debugging-port={PORT}", f"--user-data-dir={udd}"]
        if fine:
            flags.append("--blink-settings=primaryHoverType=2,availableHoverTypes=2,"
                         "primaryPointerType=4,availablePointerTypes=4")
        self.proc = subprocess.Popen([CHROME] + flags + ["about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ver = None
        for _ in range(60):
            try:
                ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2))
                break
            except Exception:
                await asyncio.sleep(0.3)
        if not ver:
            raise RuntimeError("chrome 起唔到")
        self.ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
        r = await self.call("Target.createTarget", {"url": "about:blank"})
        tid = r["result"]["targetId"]
        r = await self.call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        self.sid = r["result"]["sessionId"]
        await self.call("Runtime.enable", {}, self.sid)
        await self.call("Page.enable", {}, self.sid)
        await self.call("Emulation.setDeviceMetricsOverride",
                        {"width": width, "height": height, "deviceScaleFactor": 1,
                         "mobile": mobile}, self.sid)

    async def call(self, method, params=None, sid=None, timeout=20):
        self.seq += 1
        myid = self.seq
        msg = {"id": myid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await self.ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=max(0.02, end - time.time())))
            except asyncio.TimeoutError:
                return None
            if m.get("id") == myid:
                return m
        return None

    async def js(self, expr):
        r = await self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, self.sid)
        if r and "result" in r:
            return r["result"].get("result", {}).get("value")
        return None

    async def go(self, url, wait=4.0):
        await self.call("Page.navigate", {"url": url}, self.sid)
        await asyncio.sleep(wait)

    async def close(self):
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
        if self.proc:
            self.proc.kill()


async def main():
    data = json.load(open(os.path.join(ROOT, "data/advconj.json"), encoding="utf-8"))
    n_adv = len(data["adverbs"]["items"])
    n_cj = len(data["conjunctions"]["items"])
    b = Browser()
    await b.start(1440, 900, fine=True)

    print("【文法總表入口】")
    await b.go(BASE + "?cb=a#/all/grammar", 3)
    for _ in range(40):                      # 文法總表要掃 40 課，慢慢等
        if await b.js("document.querySelectorAll('.afentry').length"):
            break
        await asyncio.sleep(0.5)
    cards = await b.js("Array.prototype.map.call(document.querySelectorAll('.afentry'),"
                       "function(a){return a.getAttribute('href');})")
    check(cards and "#/all/particles" in cards, "有助詞一覧入口", str(cards))
    check(cards and "#/all/adverbs" in cards, "有副詞整合入口", str(cards))
    check(cards and "#/all/conjunctions" in cards, "有連接詞整合入口", str(cards))
    # 三張入口卡要排成一行（手機都不換行），且不再有灰色細字
    for w, mob in ((1200, False), (390, True)):
        await b.call("Emulation.setDeviceMetricsOverride",
                     {"width": w, "height": 900, "deviceScaleFactor": 2, "mobile": mob})
        await b.go(BASE + "?cb=r%d#/all/grammar" % w, 3)
        for _ in range(40):
            if await b.js("document.querySelectorAll('.afentry').length>=3"):
                break
            await asyncio.sleep(0.5)
        row = await b.js("""(function(){var cs=[].map.call(document.querySelectorAll('.afentry'),function(a){
          return Math.round(a.getBoundingClientRect().top);});
          return {tops:cs, subs:document.querySelectorAll('.afentry .tx span').length};})()""")
        check(len(set(row["tops"])) == 1, f"入口卡 {w}px 排成一行", str(row["tops"]))
        check(row["subs"] == 0, f"入口卡 {w}px 無灰色細字", str(row["subs"]))

    for kind, n, path, title in (("adverbs", n_adv, "/all/adverbs", "副詞一覧"),
                                 ("conjunctions", n_cj, "/all/conjunctions", "連接詞一覧")):
        print(f"【{title}】")
        await b.go(BASE + "?cb=b#/" + path.lstrip("/"), 5)
        st = await b.js("""(function(){
          var rows = document.querySelectorAll('#aclist .pgtbl tbody tr');
          var spk = document.querySelectorAll('#aclist .spk');
          var noAudio = 0, noLink = 0, links = [];
          Array.prototype.forEach.call(rows, function(tr){
            var s = tr.querySelector('.spk');
            if (!s || !s.getAttribute('data-audio')) noAudio++;
            var a = tr.querySelector('.pl');
            if (!a) noLink++; else links.push(a.getAttribute('href'));
          });
          var noZh = 0;
          Array.prototype.forEach.call(rows, function(tr){
            var ja = tr.querySelectorAll('.ptx .pja').length;
            var zh = tr.querySelectorAll('.ptx .aczh').length;
            if (!zh || zh !== ja) noZh++;
          });
          return {noZh:noZh, rows:rows.length, spk:spk.length, noAudio:noAudio, noLink:noLink,
                  h1:(document.querySelector('.lhead h1')||{}).textContent||'',
                  links:links.slice(0,3),
                  over: document.documentElement.scrollWidth > window.innerWidth + 1};})()""")
        check(st["rows"] == n, f"{title} 行數", str(st))
        check(st["spk"] == n, f"{title} 每行有喇叭", str(st["spk"]))
        check(st["noAudio"] == 0, f"{title} 每行有音檔", str(st["noAudio"]))
        check(st["noLink"] == 0, f"{title} 每行有課號連結", str(st["noLink"]))
        check(st["noZh"] == 0, f"{title} 每句都有中文翻譯", str(st["noZh"]))
        check(st["h1"].startswith(title), f"{title} 標題", st["h1"])
        check(all(l.startswith("#/l/L") and len(l) == 7 for l in st["links"]),
              f"{title} 課號連結格式", str(st["links"]))
        # 課號要真的跳到那一課
        await b.js("document.querySelector('#aclist .pl').click()")
        await asyncio.sleep(2.5)
        landed = await b.js("({hash: location.hash, h1: (document.querySelector('.lhead h1')||{}).textContent||''})")
        check(landed["hash"].startswith("#/l/L"), f"{title} 課號跳轉", str(landed))
        check(not st["over"], f"{title} 1440px 無橫向溢出")

        urls = await b.js("Array.prototype.map.call(document.querySelectorAll('#aclist .spk'),"
                          "function(s){return s.getAttribute('data-audio');})")
        bad = []
        for u in urls:
            try:
                code = urllib.request.urlopen(BASE + u, timeout=8).getcode()
            except Exception as e:
                code = str(e)
            if code != 200:
                bad.append((u, code))
        check(not bad, f"{title} 音檔全部 200", str(bad[:3]))

        # 390px 手機
        await b.call("Emulation.setDeviceMetricsOverride",
                     {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True})
        await b.go(BASE + "?cb=c#/" + path.lstrip("/"), 4.5)
        m = await b.js("({over: document.documentElement.scrollWidth > window.innerWidth + 1,"
                       " w: document.documentElement.scrollWidth, vw: window.innerWidth})")
        check(not m["over"], f"{title} 390px 無橫向溢出", str(m))

    await b.close()
    print()
    if FAIL:
        print("FAIL")
        for f in FAIL:
            print(" -", f)
        return 1
    print(f"全部通過：副詞 {n_adv} 行、連接詞 {n_cj} 行，入口／標題／喇叭／音檔／課號／390px 都正常")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
