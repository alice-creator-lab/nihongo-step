#!/usr/bin/env python3
"""驗證匯出：錯題簿／練習本的 CSV 下載與 PDF 列印稿。

用法： python3 tools/test_export.py [http://127.0.0.1:8934/]

檢查項目：
  1. 錯題簿 sheet 有「Excel（CSV）／PDF」兩顆鍵，文字帶條數。
  2. 按 CSV 會下載一個帶 UTF-8 BOM 的 .csv，欄位與行數正確（含逗號的欄位要加引號）。
  3. 按 PDF 會砌出 #printout（畫面上 display:none、列印媒體下 display:block），
     標題、表頭、行數正確，並叫了一次 window.print()。
  4. 用 Page.printToPDF 產出真正的 PDF，確認頁數與文字。
  5. 練習本：單字／句子兩個分頁各自匯出當前分頁，行數與表頭跟著分頁。
  6. 390px 下匯出列不溢出。

PDF 文字檢查需要 pypdf；沒有就只驗頁數以外的部分（會印 skip）。
"""
import asyncio, json, os, re, shutil, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8934/"
PORT = int(os.environ.get("CDP_PORT", "9347"))
DL = os.environ.get("DL", "/tmp/ngs-export-dl-%d" % os.getpid())
TODAY = time.strftime("%Y-%m-%d")
PDF = os.environ.get("PDF", "/tmp/ngs-export.pdf")

MIST = {
    "v": 1,
    "items": [
        {"key": "L04:w:シャツ", "kind": "word", "prompt": "シャツ", "answer": "襯衫",
         "sub": "L04 · シャツ, 襯衫", "at": 1762700000000, "n": 2},
        {"key": "ex1:12", "kind": "exam", "prompt": "くつ", "answer": "鞋子",
         "sub": "", "at": 1762710000000, "n": 1},
        {"key": "L13:s:1", "kind": "sentence", "prompt": "雨が降ったら、行きません。",
         "answer": "下雨的話就不去", "sub": "L13", "at": 1762720000000, "n": 1},
    ],
}
NOTE = {
    "v": 1,
    "items": [
        {"type": "word", "id": "L04", "vi": 1, "kanji": "傘", "kana": "かさ", "zh": "雨傘",
         "pos": "名詞", "audio": "", "src": "L04", "at": 1762700000000},
        {"type": "word", "id": "L08", "vi": 2, "kanji": "", "kana": "あまい", "zh": "甜的",
         "pos": "い形容詞", "audio": "", "src": "L08", "at": 1762710000000},
        {"type": "sentence", "id": "L12", "ja": "箸を使って食べます。", "kana": "はしをつかってたべます",
         "zh": "用筷子吃飯", "audio": "", "src": "L12 · 「で」：動作場所", "at": 1762720000000},
    ],
}


def read_pdf(path):
    """回傳 (頁數, 文字) 或 None。"""
    try:
        from pypdf import PdfReader
    except Exception:
        return None
    r = PdfReader(path)
    return len(r.pages), "\n".join((p.extract_text() or "") for p in r.pages)


async def main():
    shutil.rmtree(DL, ignore_errors=True)
    os.makedirs(DL, exist_ok=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=430,900",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-ngexp-" + str(os.getpid()),
         "about:blank"],
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

    async def wait(mid, timeout=30):
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

    async def call(method, params=None, sid=None, timeout=30):
        return await wait(await send(method, params, sid), timeout)

    tgt = await call("Target.getTargets")
    tid = [t["targetId"] for t in tgt["result"]["targetInfos"] if t["type"] == "page"][0]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Page.enable", {}, sid)
    await call("Runtime.enable", {}, sid)
    await call("Browser.setDownloadBehavior",
               {"behavior": "allow", "downloadPath": DL, "eventsEnabled": True})

    async def js(expr):
        r = await call("Runtime.evaluate",
                       {"expression": expr, "returnByValue": True, "awaitPromise": True}, sid)
        if not r or "result" not in r:
            return None
        return r["result"].get("result", {}).get("value")

    fails = []

    def check(name, got, want):
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got)
              + ("" if ok else " (want " + repr(want) + ")"))
        if not ok:
            fails.append(name)

    def wait_csv(before):
        for _ in range(40):
            now = set(f for f in os.listdir(DL) if f.endswith(".csv"))
            new = now - before
            if new:
                return sorted(new)[0]
            time.sleep(0.25)
        return None

    def read_csv(name):
        import csv as _csv, io
        with open(os.path.join(DL, name), "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8-sig")
        rows = [r for r in _csv.reader(io.StringIO(text)) if r]
        return raw, text, rows

    URL = BASE + "index.html#/"
    await call("Page.navigate", {"url": URL}, sid)
    await asyncio.sleep(5)
    await js("localStorage.setItem('ngs-mistakes-v1', %s)" % json.dumps(json.dumps(MIST)))
    await js("localStorage.setItem('ngs-notebook-v1', %s)" % json.dumps(json.dumps(NOTE)))
    await call("Page.reload", {"ignoreCache": True}, sid)
    await asyncio.sleep(6)
    for _ in range(25):
        if await js("!!document.querySelector('#mkBtn')"):
            break
        await asyncio.sleep(1)
    await call("Emulation.setDeviceMetricsOverride",
               {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)
    await asyncio.sleep(0.5)

    # ── 錯題簿 ──────────────────────────────────────────────
    await js("document.querySelector('#mkBtn').click()")
    await asyncio.sleep(0.8)
    check("錯題簿匯出列", await js("document.querySelectorAll('#sheetbox .expbar').length"), 1)
    check("錯題簿匯出鍵",
          await js("[].map.call(document.querySelectorAll('#sheetbox .expbar .btn2'),function(b){return b.innerText})"),
          ["Excel（CSV）", "PDF"])
    check("錯題簿匯出說明",
          await js("(document.querySelector('#sheetbox .expbar .exl')||{}).innerText||''"),
          "匯出全部 3 條")
    check("390px 錯題簿 sheet 不溢出",
          await js("document.querySelector('#sheetbox').scrollWidth <= 391"), True)

    before = set(f for f in os.listdir(DL) if f.endswith(".csv"))
    await js("document.querySelector('#sheetbox [data-exp=\"csv\"]').click()")
    name = wait_csv(before)
    check("CSV 有落檔", bool(name), True)
    if name:
        raw, text, rows = read_csv(name)
        check("CSV 檔名", name, "錯題簿-%s.csv" % TODAY)
        check("CSV 有 UTF-8 BOM", raw[:3], b"\xef\xbb\xbf")
        check("CSV 表頭", rows[0], ["#", "類型", "題目", "正確答案", "補充", "最後答錯"])
        check("CSV 行數（含表頭）", len(rows), 4)
        check("CSV 類型欄", [r[1] for r in rows[1:]], ["單字", "階段測驗", "句子"])
        check("CSV 逗號欄位有引號", '"L04 · シャツ, 襯衫"' in text, True)
        check("CSV 日期格式", re.match(r"\d{4}-\d{2}-\d{2}$", rows[1][5]) is not None, True)

    await js("window.__pr=0; window.print=function(){ window.__pr++; };")
    await js("document.querySelector('#sheetbox [data-exp=\"pdf\"]').click()")
    await asyncio.sleep(0.9)
    check("PDF 叫了一次列印", await js("window.__pr"), 1)
    check("PDF 稿存在", await js("!!document.getElementById('printout')"), True)
    check("PDF 稿畫面上隱藏",
          await js("getComputedStyle(document.getElementById('printout')).display"), "none")
    check("PDF 表頭",
          await js("[].map.call(document.querySelectorAll('#printout thead th'),function(t){return t.innerText})"),
          ["#", "類型", "題目", "正確答案", "補充", "最後答錯"])
    check("PDF 行數", await js("document.querySelectorAll('#printout tbody tr').length"), 3)
    check("PDF 標題", await js("document.querySelector('#printout h1').innerText"), "錯題簿")

    await call("Emulation.setEmulatedMedia", {"media": "print"}, sid)
    await asyncio.sleep(0.4)
    check("列印媒體：app 收起",
          await js("getComputedStyle(document.getElementById('app')).display"), "none")
    check("列印媒體：sheet 收起",
          await js("getComputedStyle(document.getElementById('sheet')).display"), "none")
    check("列印媒體：PDF 稿顯示",
          await js("getComputedStyle(document.getElementById('printout')).display"), "block")
    r = await call("Page.printToPDF",
                   {"printBackground": True, "preferCSSPageSize": True}, sid, timeout=60)
    if r and "result" in r:
        import base64
        with open(PDF, "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        info = read_pdf(PDF)
        if info:
            pages, text = info
            check("PDF 頁數（3 條＝1 頁）", pages, 1)
            check("PDF 首行是標題", text.strip().splitlines()[0].strip(), "錯題簿")
            check("PDF 見到題目", "シャツ" in text, True)
            check("PDF 見到正確答案", "襯衫" in text, True)
        else:
            print("  skip PDF 內文檢查（無 pypdf）")
        check("PDF 檔大小 > 2KB", os.path.getsize(PDF) > 2048, True)
    else:
        check("Page.printToPDF", "timeout", "ok")
    await call("Emulation.setEmulatedMedia", {"media": ""}, sid)
    await js("document.querySelector('#sheetClose').click()")
    await asyncio.sleep(0.4)

    # ── 練習本・單字 ────────────────────────────────────────
    await js("location.hash = '#/note'")
    await asyncio.sleep(1.2)
    check("練習本匯出列", await js("document.querySelectorAll('#app .expbar').length"), 1)
    check("練習本匯出說明（單字分頁）",
          await js("(document.querySelector('#app .expbar .exl')||{}).innerText||''"),
          "匯出這頁 2 項")
    check("390px 練習本匯出列不溢出",
          await js("document.querySelector('#app .expbar').scrollWidth <= 391"), True)

    before = set(f for f in os.listdir(DL) if f.endswith(".csv"))
    await js("document.querySelector('#app [data-exp=\"csv\"]').click()")
    name = wait_csv(before)
    check("練習本 CSV 有落檔", bool(name), True)
    if name:
        raw, text, rows = read_csv(name)
        check("練習本 CSV 檔名", name, "練習本-單字-%s.csv" % TODAY)
        check("練習本 CSV 表頭", rows[0],
              ["#", "漢字", "假名", "中文", "詞性", "出處", "加入日期"])
        check("練習本 CSV 行數", len(rows), 3)
        check("練習本 CSV 第一行", rows[1][:6], ["1", "傘", "かさ", "雨傘", "名詞", "L04"])
        check("練習本 CSV 假名詞漢字留空", rows[2][1], "")

    await js("window.__pr=0; window.print=function(){ window.__pr++; };")
    await js("document.querySelector('#app [data-exp=\"pdf\"]').click()")
    await asyncio.sleep(0.9)
    check("練習本 PDF 標題", await js("document.querySelector('#printout h1').innerText"),
          "練習本・單字")
    check("練習本 PDF 行數", await js("document.querySelectorAll('#printout tbody tr').length"), 2)

    # ── 練習本・句子分頁 ────────────────────────────────────
    await js("document.querySelector('#nbTabs [data-t=\"sent\"]').click()")
    await asyncio.sleep(0.9)
    check("句子分頁匯出說明",
          await js("(document.querySelector('#app .expbar .exl')||{}).innerText||''"),
          "匯出這頁 1 項")
    before = set(f for f in os.listdir(DL) if f.endswith(".csv"))
    await js("document.querySelector('#app [data-exp=\"csv\"]').click()")
    name = wait_csv(before)
    check("句子 CSV 有落檔", bool(name), True)
    if name:
        raw, text, rows = read_csv(name)
        check("句子 CSV 檔名", name, "練習本-句子-%s.csv" % TODAY)
        check("句子 CSV 表頭", rows[0], ["#", "日文", "假名", "中文", "出處", "加入日期"])
        check("句子 CSV 行數", len(rows), 2)
        check("句子 CSV 內容", rows[1][1], "箸を使って食べます。")

    # ── 多頁：60 條錯題應自動分頁 ──────────────────────────
    many = {"v": 1, "items": [
        {"key": "k%d" % i, "kind": "word", "prompt": "ことば%d" % i, "answer": "詞語%d" % i,
         "sub": "L%02d" % (i % 40 + 1), "at": 1762700000000, "n": 1} for i in range(60)]}
    await js("localStorage.setItem('ngs-mistakes-v1', %s)" % json.dumps(json.dumps(many)))
    await js("location.hash = '#/'")
    await call("Page.reload", {"ignoreCache": True}, sid)
    await asyncio.sleep(6)
    for _ in range(20):
        if await js("!!document.querySelector('#mkBtn')"):
            break
        await asyncio.sleep(1)
    await js("document.querySelector('#mkBtn').click()")
    await asyncio.sleep(0.8)
    check("60 條時匯出說明", await js("(document.querySelector('#sheetbox .expbar .exl')||{}).innerText||''"),
          "匯出全部 60 條")
    await js("window.__pr=0; window.print=function(){ window.__pr++; };")
    await js("document.querySelector('#sheetbox [data-exp=\"pdf\"]').click()")
    await asyncio.sleep(0.9)
    check("60 條 PDF 行數", await js("document.querySelectorAll('#printout tbody tr').length"), 60)
    await call("Emulation.setEmulatedMedia", {"media": "print"}, sid)
    r = await call("Page.printToPDF", {"printBackground": True, "preferCSSPageSize": True}, sid, timeout=90)
    await call("Emulation.setEmulatedMedia", {"media": ""}, sid)
    if r and "result" in r:
        import base64
        with open(PDF, "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        info = read_pdf(PDF)
        if info:
            pages, text = info
            check("60 條 PDF 多於一頁", pages >= 2, True)
            check("每頁重複表頭（表頭出現 >= 頁數）",
                  text.count("正確答案") >= pages, True)
            # pypdf 抽 CJK 時會在字與數字之間插空格，比對前先去空白
            flat = re.sub(r"\s+", "", text)
            check("最後一條有印出", "ことば59" in flat, True)
        else:
            print("  skip 多頁 PDF 內文檢查（無 pypdf）")

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
