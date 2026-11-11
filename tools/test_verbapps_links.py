#!/usr/bin/env python3
"""驗證「不同形態的應用」每個句型牌的課號，真的指到有教該句型的課。

檢查：
1. 每一行（現 67 行）的 l（課號）等於預期課號，而且該課的 patterns 內有完全相同的句型文字。
2. 瀏覽器實際點課號 → 跳到該課句型頁，頁上真的有這張句型卡（.pja 完全相符）。
3. 390px 無橫向溢出。

用法： python3 tools/test_verbapps_links.py http://127.0.0.1:8911
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import websockets

CHROME = "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
BASE = sys.argv[1]
SHOT = os.environ.get("SHOT", "")
PORT = 9356
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = json.load(open(os.path.join(ROOT, "data/verbapps.json"), encoding="utf-8"))

# (課號, 該課句型卡的完整文字) — 次序跟 data/verbapps.json 的 67 行一致
EXPECT = [
    # ます形：課本「動詞句型練習」的 10 行
    ("L07", "～ませんか"),
    ("L07", "～ましょう"),
    ("L06", "～に行きます（目的）"),
    ("L07", "～ましょうか"),
    ("L12", "～方（かた）"),
    ("L13", "～ながら"),
    ("L14", "～やすい"),
    ("L14", "～にくい"),
    ("L14", "～すぎる"),
    ("L31", "～なさい"),
    # ます形：後補的 4 個（L23 たい／L36 そうです）
    ("L23", "ます形＋たいです"),
    ("L23", "ます形＋たくないです／たくありません"),
    ("L23", "～たいですか／～たいんですが"),
    ("L36", "動詞ます形＋そうです"),
    # 辞書形
    ("L11", "～のが好きです"),
    ("L11", "～ことです（趣味は～）"),
    ("L15", "～まえに"),
    ("L21", "～のは～です"),
    ("L24", "辞書形＋ことができる"),
    ("L28", "動詞辞書形＋つもりです"),
    ("L28", "名詞／動詞辞書形＋予定です"),
    ("L28", "動詞辞書形＋ことにしました／ことにしています"),
    ("L35", "～と、～"),
    ("L35", "～と、～（過去）"),
    # て形
    ("L12", "～て、～て（順序）"),
    ("L12", "～てください"),
    ("L12", "～てくださいませんか"),
    ("L12", "～ています（進行）"),
    ("L15", "～ています（結果の状態）"),
    ("L13", "～てから"),
    ("L15", "～てみます"),
    ("L20", "～てもいいです"),
    ("L20", "～てもかまいません"),
    ("L20", "～てはいけません"),
    ("L20", "～てはだめです"),
    ("L12", "～て（手段・方法）"),
    ("L15", "まだ～ていません"),
    ("L15", "～てみたいです"),
    ("L26", "自動詞＋ている（結果の状態）"),
    ("L26", "他動詞＋てある（人為の状態）"),
    ("L26", "他動詞＋ておく（事前の準備）"),
    ("L26", "他動詞＋てしまう（残念・完了）"),
    ("L33", "～ておきます"),
    ("L33", "～ておいてください"),
    ("L33", "～ておきました"),
    ("L34", "～てあります"),
    ("L34", "～ておきます／～てあります"),
    ("L38", "～てあげます"),
    ("L38", "～てもらいます"),
    ("L38", "～てくれます"),
    # た形
    ("L13", "～たあとで"),
    ("L13", "～たり～たりします"),
    ("L17", "～たことがあります"),
    ("L17", "～たばかりです"),
    ("L13", "～ました／た形"),
    ("L17", "もう～ました／まだ～ていません"),
    ("L31", "～たほうがいいです"),
    ("L33", "～たら、～"),
    ("L33", "～たらどうですか"),
    ("L33", "～たらいいですか"),
    # ない形
    ("L14", "～ないでください"),
    ("L14", "～ないで、～"),
    ("L14", "～なければなりません"),
    ("L28", "〜つもりはありません／〜ないつもりです"),
    ("L31", "～なくてはいけません"),
    ("L31", "～ないほうがいいです"),
    ("L35", "～ないと、～"),
]

rows = [(g["form"], r) for g in DATA["groups"] for r in g["rows"]]
fails = []
if len(rows) != len(EXPECT):
    fails.append(f"行數 {len(rows)} ≠ {len(EXPECT)}")

# 1. 資料層：課號與該課 patterns 必須完全對上
lessons = {}
for lid in {l for l, _ in EXPECT}:
    lessons[lid] = json.load(open(os.path.join(ROOT, f"data/lesson-{lid}.json"), encoding="utf-8"))
def norm(l):
    return "L" + str(int(l[1:]))


for (form, r), (want_l, want_pat) in zip(rows, EXPECT):
    if norm(r["l"]) != norm(want_l):
        fails.append(f"「{r['pat']}」課號 {r['l']} ≠ 預期 {want_l}")
    pats = [p["ja"] for p in lessons[want_l]["patterns"]]
    if want_pat not in pats:
        fails.append(f"{want_l} 沒有句型卡「{want_pat}」（來自「{r['pat']}」）")


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={PORT}",
         "--user-data-dir=/tmp/cdp-aplink-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    n = [0]

    async def send(method, params=None, sid=None):
        n[0] += 1
        msg = {"id": n[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        while True:
            raw = json.loads(await ws.recv())
            if raw.get("id") == n[0]:
                return raw

    t = await send("Target.createTarget", {"url": "about:blank"})
    s = await send("Target.attachToTarget", {"targetId": t["result"]["targetId"], "flatten": True})
    sid = s["result"]["sessionId"]
    await send("Page.enable", {}, sid)
    await send("Runtime.enable", {}, sid)

    async def ev(js):
        r = await send("Runtime.evaluate",
                       {"expression": js, "returnByValue": True, "awaitPromise": True}, sid)
        return r.get("result", {}).get("result", {}).get("value")

    await send("Emulation.setDeviceMetricsOverride",
               {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}, sid)

    # 2. 瀏覽器層：逐個課號真的跳過去，頁上有該句型卡
    await send("Page.navigate", {"url": BASE + "#/all/verbs/apps"}, sid)
    for _ in range(60):
        await asyncio.sleep(0.25)
        if await ev("document.querySelectorAll('.aptbl tr.apr').length == %d" % len(EXPECT)):
            break
    links = await ev("""JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.apl'), function(a){ return a.innerText; }))""")
    if [norm(x) for x in json.loads(links or "[]")] != [norm(l) for l, _ in EXPECT]:
        fails.append(f"頁上課號 {links} ≠ 資料")

    for lid in sorted({l for l, _ in EXPECT}):
        await ev(f"location.hash = '#/l/{lid}'")
        ok = False
        for _ in range(60):
            await asyncio.sleep(0.2)
            got = await ev("JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.pat .pja'), function(e){ return e.innerText; }))")
            if got and json.loads(got):
                ok = True
                break
        if not ok:
            fails.append(f"{lid} 沒有渲染句型卡")
            continue
        have = set(json.loads(got))
        for want_l, want_pat in EXPECT:
            if want_l == lid and want_pat not in have:
                fails.append(f"點 {lid} 後頁上找不到「{want_pat}」")

    await ev("location.hash = '#/all/verbs/apps'")
    await asyncio.sleep(0.6)
    over = await ev("document.documentElement.scrollWidth + '/' + window.innerWidth")
    sw = int(over.split("/")[0])
    if sw > 391:
        fails.append(f"390px 橫向溢出：{over}")
    if SHOT:
        await ev("window.scrollTo(0,0)")
        await asyncio.sleep(0.3)
        r = await send("Page.captureScreenshot", {"format": "png"}, sid)
        open(SHOT, "wb").write(base64.b64decode(r["result"]["data"]))

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
    else:
        print(f"全部通過：{len(rows)} 行課號都指到真正有教該句型的課")
    await ws.close()
    proc.terminate()
    sys.exit(1 if fails else 0)


asyncio.run(main())
