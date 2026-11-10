#!/usr/bin/env python3
"""驗證形容詞表（#/all/adjs）的排序與「由中間開始順播」。

- 三個排序：分類（預設，い形／な形 分組）／課程順序／五十音順；
  選擇寫入 localStorage `ngs-wsort`，重載後保留。
- 五十音順：整份次序與測試內獨立算出的五十音鍵逐項比對，並插入「X行」分段標題。
- 課程順序：右邊課號單調不減。
- 點字詞本身（不是 ☆、不是喇叭）由該項播到最後，浮動停止鍵出現並顯示「第幾項／128」，
  一按即停。
- 390 / 360px 排序 chips 與浮動鍵都不橫向溢出。

用法： python3 tools/test_adj_sort.py [http://127.0.0.1:8792/]
環境變數：SHOT=/path/x.png 截圖；CDP_PORT 換 port。
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8792/"
PORT = int(os.environ.get("CDP_PORT", "9362"))
SHOT = os.environ.get("SHOT")

# ---------- 測試內獨立實作的五十音鍵（與 index.html 分開寫，避免同錯） ----------
KROWS = ['あいうえお', 'かきくけこ', 'さしすせそ', 'たちつてと', 'なにぬねの',
         'はひふへほ', 'まみむめも', 'やゆよ', 'らりるれろ', 'わを', 'ん']
KROWLET = 'あかさたなはまやらわん'
KSMALL = {'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
          'っ': 'つ', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ', 'ゎ': 'わ'}


def build_maps():
    base, row, voice, slot = {}, {}, {}, 0
    for ri, line in enumerate(KROWS):
        for ch in line:
            base[ch], row[ch], voice[ch] = slot, KROWLET[ri], 0
            slot += 1
    for a, b in [('か', 'が'), ('き', 'ぎ'), ('く', 'ぐ'), ('け', 'げ'), ('こ', 'ご'),
                 ('さ', 'ざ'), ('し', 'じ'), ('す', 'ず'), ('せ', 'ぜ'), ('そ', 'ぞ'),
                 ('た', 'だ'), ('ち', 'ぢ'), ('つ', 'づ'), ('て', 'で'), ('と', 'ど'),
                 ('は', 'ば'), ('ひ', 'び'), ('ふ', 'ぶ'), ('へ', 'べ'), ('ほ', 'ぼ')]:
        base[b], row[b], voice[b] = base[a], row[a], 1
    for a, b in [('は', 'ぱ'), ('ひ', 'ぴ'), ('ふ', 'ぷ'), ('へ', 'ぺ'), ('ほ', 'ぽ')]:
        base[b], row[b], voice[b] = base[a], row[a], 2
    return base, row, voice


KBASE, KROW, KVOICE = build_maps()


def kana_key(s):
    out = []
    for ch in s:
        c = ord(ch)
        if 0x30A1 <= c <= 0x30F6:
            ch = chr(c - 0x60)
        if ch in 'ー〜 　':
            continue
        if ch in KSMALL:
            out.append(KBASE[KSMALL[ch]] * 8 + 1)
            continue
        if ch not in KBASE:
            out.append(9999)
            continue
        out.append(KBASE[ch] * 8 + KVOICE[ch] * 2)
    return out


def row_of(s):
    for ch in s:
        c = ord(ch)
        if 0x30A1 <= c <= 0x30F6:
            ch = chr(c - 0x60)
        r = KROW.get(ch) or (KROW.get(KSMALL[ch]) if ch in KSMALL else None)
        if r:
            return 'ん' if r == 'ん' else r + '行'
    return '其他'


data = json.load(open(os.path.join(HERE, "data", "wordtables.json")))["adjs"]
FLAT = [x for g in data["groups"] for x in g["items"]]
TOTAL = len(FLAT)
BY_AUDIO = {x["audio"]: x for x in FLAT}
KANA_ORDER = [x["audio"] for _, x in sorted(enumerate(FLAT),
                                            key=lambda p: (kana_key(p[1]["kana"]), p[0]))]
LESSON_ORDER = [x["audio"] for _, x in sorted(enumerate(FLAT),
                                              key=lambda p: (int(p[1]["id"][1:]), p[0]))]
KANA_HEADS = []
_prev = None
for a in KANA_ORDER:
    r = row_of(BY_AUDIO[a]["kana"])
    if r != _prev:
        KANA_HEADS.append(r)
        _prev = r

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
         "--user-data-dir=/tmp/cdp-adjsort-" + str(os.getpid()), "about:blank"],
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

    async def call(method, params=None, sid=None, timeout=12):
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
                                                "awaitPromise": True}, sid, timeout=25)
            if r and "result" in r:
                return r["result"].get("result", {}).get("value")
        return None

    async def wait_until(expr, secs=30):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await asyncio.sleep(0.4)
        return None

    async def viewport(w):
        await call("Emulation.setDeviceMetricsOverride",
                   {"width": w, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    async def shot(name):
        r = await call("Page.captureScreenshot", {"format": "png"}, sid, timeout=25)
        if r and "result" in r:
            open("/tmp/" + name, "wb").write(base64.b64decode(r["result"]["data"]))

    ORDER_JS = ("[...document.querySelectorAll('#alllist .arow')]"
                ".map(r=>{var s=r.querySelector('.spk');return s?s.getAttribute('data-audio'):null})")
    out = {}
    await viewport(390)

    # 1) 形容詞表載入＋排序 chips
    await call("Page.navigate", {"url": BASE + "#/all/adjs"}, sid)
    rows = await wait_until("document.querySelectorAll('#alllist .arow').length")
    out["行數"] = rows
    out["預期行數"] = TOTAL
    out["版本"] = await js("document.getElementById('verTag').textContent.trim()")
    out["排序選項"] = await js("[...document.querySelectorAll('#wsort [data-s]')].map(b=>[b.getAttribute('data-s'),b.textContent.trim(),b.classList.contains('on')])")
    out["分類標題"] = await js("[...document.querySelectorAll('#alllist .wth .wtn')].map(x=>x.textContent.trim())")
    out["跳轉列可見"] = await js("(function(){var j=document.getElementById('wtjump');return j.offsetHeight>0})()")
    out["預設次序"] = (await js(ORDER_JS)) == [x["audio"] for x in FLAT]
    await shot("adjsort-group-390.png")

    # 2) 五十音順
    await js("document.querySelector('#wsort [data-s=kana]').click()")
    await asyncio.sleep(0.5)
    out["五十音次序正確"] = (await js(ORDER_JS)) == KANA_ORDER
    out["五十音分段標題"] = await js("[...document.querySelectorAll('#alllist .khead')].map(x=>x.textContent.trim())")
    out["預期分段標題"] = KANA_HEADS
    out["五十音計數"] = await js("document.getElementById('allcnt').textContent.trim()")
    out["跳轉列收起"] = await js("(function(){var j=document.getElementById('wtjump');return j.offsetHeight===0})()")
    await shot("adjsort-kana-390.png")

    # 3) 課程順序
    await js("document.querySelector('#wsort [data-s=lesson]').click()")
    await asyncio.sleep(0.5)
    out["課程次序正確"] = (await js(ORDER_JS)) == LESSON_ORDER
    ids = await js("[...document.querySelectorAll('#alllist .arow .al')].map(x=>x.textContent.trim())")
    nums = [int(s[1:]) for s in ids]
    out["課號單調"] = nums == sorted(nums)
    out["課程計數"] = await js("document.getElementById('allcnt').textContent.trim()")
    out["localStorage"] = await js("localStorage.getItem('ngs-wsort')")

    # 4) 回到分類
    await js("document.querySelector('#wsort [data-s=group]').click()")
    await asyncio.sleep(0.4)
    out["回分類"] = await js("[...document.querySelectorAll('#alllist .wth')].length") == len(
        [g for g in data["groups"] if g["items"]])
    out["本組鍵"] = await js("document.querySelectorAll('#alllist .gplay').length")

    # 5) 重載後保留選擇（先切五十音再重載）
    await js("document.querySelector('#wsort [data-s=kana]').click()")
    await asyncio.sleep(0.3)
    await call("Page.reload", {"ignoreCache": True}, sid)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    out["重載後on"] = await js("(document.querySelector('#wsort [data-s=kana]')||{}).className")
    out["重載後次序正確"] = (await js(ORDER_JS)) == KANA_ORDER
    await js("document.querySelector('#wsort [data-s=group]').click()")
    await asyncio.sleep(0.4)

    # 6) 由中間開始順播
    await js(INSTR)
    picked = await js("""(function(){
      var rows = document.querySelectorAll('#alllist .arow');
      var i = 40, r = rows[i];
      var sp = r.querySelector('.spk');
      r.querySelector('.ak').click();
      return { i:i, total:rows.length, audio: sp ? sp.getAttribute('data-audio') : null,
               text:(r.querySelector('.ak b')||{}).textContent };
    })()""")
    await asyncio.sleep(1.2)
    out["點字詞起播"] = {
        "所點第幾項": picked["i"] + 1,
        "第一段": await js("window.__played[0]"),
        "該行音檔": picked["audio"],
        "進度": await js("document.getElementById('allstopN').textContent.trim()"),
        "浮動鍵": await js("document.getElementById('allstop').classList.contains('on')"),
        "頁頂按鈕": await js("document.getElementById('allplay').textContent.trim()"),
    }
    t = out["點字詞起播"]
    firstf = (t["第一段"] or "").split("?")[0]
    rowf = (t["該行音檔"] or "").replace("audio/", "", 1)
    try:
        prog = int((t["進度"] or "0／0").split("／")[0])
    except ValueError:
        prog = 0
    # 第一段音檔要係所點那一行；進度由該項起算（第一段可能已播完而跳到下一項）
    out["由所點那項開始"] = bool(rowf and firstf == rowf
                              and picked["i"] + 1 <= prog <= picked["i"] + 3
                              and t["浮動鍵"] and t["頁頂按鈕"] == "■ 停止")
    await shot("adjsort-play-390.png")

    # 7) 浮動鍵即停
    await js("document.getElementById('allstop').click()")
    await asyncio.sleep(0.5)
    n1 = await js("window.__played.length")
    await asyncio.sleep(2.0)
    out["停後"] = await js("""(function(){
      return { bar: document.getElementById('allstop').classList.contains('on'),
               rows: document.querySelectorAll('#alllist .arow.playing').length,
               playing: !!(window.__cur && !window.__cur.paused),
               btn: document.getElementById('allplay').textContent.trim() };
    })()""")
    out["浮動鍵即停"] = bool(not out["停後"]["bar"] and out["停後"]["rows"] == 0
                          and not out["停後"]["playing"]
                          and out["停後"]["btn"] == "▶ 播放全部"
                          and await js("window.__played.length") == n1)

    # 8) 搜尋＋360px 無溢出
    await js("(function(){var q=document.getElementById('allq');q.value='おお';"
             "q.dispatchEvent(new Event('input',{bubbles:true}));})()")
    await asyncio.sleep(0.4)
    out["搜尋"] = await js("document.getElementById('allcnt').textContent.trim()")
    await js("(function(){var q=document.getElementById('allq');q.value='';"
             "q.dispatchEvent(new Event('input',{bubbles:true}));})()")
    await asyncio.sleep(0.4)
    await viewport(360)
    out["360"] = await js("""(function(){
      var b=document.querySelectorAll('#wsort button'), r=b[b.length-1].getBoundingClientRect();
      return { iw: window.innerWidth, sw: document.documentElement.scrollWidth,
               right: Math.round(r.right), left: Math.round(b[0].getBoundingClientRect().left) };
    })()""")
    out["360無溢出"] = bool(out["360"]["sw"] <= out["360"]["iw"] + 1
                          and out["360"]["right"] <= out["360"]["iw"])
    await shot("adjsort-360.png")

    checks = ["行數", "預設次序", "五十音次序正確", "五十音分段標題", "課程次序正確",
              "課號單調", "回分類", "重載後次序正確", "由所點那項開始", "浮動鍵即停", "360無溢出"]
    bad = [k for k in checks if not out.get(k)]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(("FAIL: " + ", ".join(bad)) if bad else "PASS 全部通過")
    if SHOT:
        open(SHOT, "wb").write(open("/tmp/adjsort-group-390.png", "rb").read())
    proc.terminate()
    await ws.close()
    if bad:
        sys.exit(1)

asyncio.run(main())
