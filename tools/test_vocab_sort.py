#!/usr/bin/env python3
"""驗證詞語總表的排序：課程順序 ↔ 五十音順。

- 課程順序：983 項、無分段標題、第一項是第 1 課的字。
- 五十音順：10 個「X行」分段標題、整份次序與獨立算出的五十音鍵完全一致
  （片假名按讀音混入，例如 アパート 排在 あ行）、選擇寫入 localStorage 並在重載後保留。
- 搜尋在排序後的清單內篩選（分段標題隱藏）、☆ 收藏對應正確項目、390px 不橫向溢出。

用法： python3 tools/test_vocab_sort.py [http://127.0.0.1:8934/]
環境變數：SHOT=/path/x.png 截圖；CDP_PORT 換 port。
"""
import asyncio, json, os, shutil, subprocess, sys, time, urllib.request
import websockets

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8934/"
PORT = int(os.environ.get("CDP_PORT", "9353"))

# ---------- 獨立算出預期結果（照 index.html 的去重與五十音規則重寫一次） ----------
KROWS = ['あいうえお', 'かきくけこ', 'さしすせそ', 'たちつてと', 'なにぬねの',
         'はひふへほ', 'まみむめも', 'やゆよ', 'らりるれろ', 'わを', 'ん']
KROWLET = 'あかさたなはまやらわん'
KSMALL = {'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
          'っ': 'つ', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ', 'ゎ': 'わ'}
VSTEM = {'い': 'う', 'き': 'く', 'ぎ': 'ぐ', 'し': 'す', 'ち': 'つ',
         'に': 'ぬ', 'ひ': 'ふ', 'び': 'ぶ', 'み': 'む', 'り': 'る'}


def build_kana_maps():
    base, row, voice, slot = {}, {}, {}, 0
    for ri, line in enumerate(KROWS):
        for ch in line:
            base[ch], row[ch], voice[ch] = slot, KROWLET[ri], 0
            slot += 1
    pairs = [('か', 'が'), ('き', 'ぎ'), ('く', 'ぐ'), ('け', 'げ'), ('こ', 'ご'),
             ('さ', 'ざ'), ('し', 'じ'), ('す', 'ず'), ('せ', 'ぜ'), ('そ', 'ぞ'),
             ('た', 'だ'), ('ち', 'ぢ'), ('つ', 'づ'), ('て', 'で'), ('と', 'ど'),
             ('は', 'ば'), ('ひ', 'び'), ('ふ', 'ぶ'), ('へ', 'べ'), ('ほ', 'ぼ')]
    semi = [('は', 'ぱ'), ('ひ', 'ぴ'), ('ふ', 'ぷ'), ('へ', 'ぺ'), ('ほ', 'ぽ')]
    for a, b in pairs:
        base[b], row[b], voice[b] = base[a], row[a], 1
    for a, b in semi:
        base[b], row[b], voice[b] = base[a], row[a], 2
    return base, row, voice


KBASE, KROW, KVOICE = build_kana_maps()


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


def kana_row(s):
    for ch in s:
        c = ord(ch)
        if 0x30A1 <= c <= 0x30F6:
            ch = chr(c - 0x60)
        r = KROW.get(ch) or (KROW.get(KSMALL[ch]) if ch in KSMALL else None)
        if r:
            return 'ん' if r == 'ん' else r + '行'
    return '其他'


def is_verb(v):
    return (v.get('pos') or '').startswith('動詞')


def same_verb_kana(a, b):
    if a == b:
        return True
    if a.endswith('ます'):
        stem, other = a[:-2], b
    elif b.endswith('ます'):
        stem, other = b[:-2], a
    else:
        return False
    if not stem or other.endswith('ます'):
        return False
    if other == stem + 'る':
        return True
    return other == stem[:-1] + VSTEM.get(stem[-1], '')


def same_vocab(a, b):
    if a['kana'] != b['kana']:
        if not (is_verb(a) and is_verb(b) and same_verb_kana(a['kana'], b['kana'])):
            return False
    ka, kb = a.get('kanji') or '', b.get('kanji') or ''
    if ka or kb:
        if ka == kb:
            return True
        # 一邊寫漢字、另一邊只寫假名：同詞性＋同中文意思才算同一詞（明後日／あさって）
        if ka and kb:
            return False
        return (a.get('pos') or '') == (b.get('pos') or '') and (a.get('zh') or '') == (b.get('zh') or '')
    return (a.get('pos') or '') == (b.get('pos') or '')


def vocab_items():
    course = json.load(open(os.path.join(HERE, 'data/course.json')))
    avail = [l for b in course['books'] for l in b['lessons'] if l.get('available')]
    store, out = {'kana': {}, 'kanji': {}}, []
    for m in avail:
        d = json.load(open(os.path.join(HERE, 'data', 'lesson-%s.json' % m['id'])))
        for v in (d.get('vocab') or []):
            if v.get('seqOnly'):
                continue
            kana, kanji = v['kana'], (v.get('kanji') or '')
            cand = list(store['kana'].get(kana, []))
            if kanji:
                cand += store['kanji'].get(kanji, [])
            if any(same_vocab(x, v) for x in cand):
                continue
            store['kana'].setdefault(kana, []).append(v)
            if kanji:
                store['kanji'].setdefault(kanji, []).append(v)
            out.append((m['id'], v))
    return out


ITEMS = vocab_items()
SORTED = sorted(ITEMS, key=lambda t: kana_key(t[1]['kana']))
EXP_LESSON = [(lid, v['kana'], v.get('kanji') or '') for lid, v in SORTED]
EXP_ROWS = []
for lid, v in SORTED:
    r = kana_row(v['kana'])
    if not EXP_ROWS or EXP_ROWS[-1:] != [r]:
        EXP_ROWS.append(r)


async def main():
    print("預期：%d 項、%d 個分段（%s）" % (len(EXP_LESSON), len(EXP_ROWS), '／'.join(EXP_ROWS)))
    profile = "/tmp/cdp-vsort-" + str(os.getpid())
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--window-size=390,900",
         "--remote-debugging-port=%d" % PORT, "--user-data-dir=" + profile, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ver = None
    for _ in range(80):
        try:
            ver = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT))
            break
        except Exception:
            time.sleep(0.3)
    if not ver:
        sys.exit("CDP 起不來")
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]

    async def send(method, params, sid=None):
        seq[0] += 1
        msg = {"id": seq[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        return seq[0]

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
        print(("  ok   " if ok else "  FAIL ") + name + ": " + repr(got)[:200])
        if not ok:
            fails.append(name)

    async def ready():
        for _ in range(30):
            if await js("document.querySelectorAll('#alllist .arow').length"):
                return True
            await asyncio.sleep(1)
        return False

    async def rows():
        return await js("""(function(){
          return Array.prototype.map.call(document.querySelectorAll('#alllist .arow'), function(r){
            return { kana: (r.querySelector('.ak span')||{}).innerText || (r.querySelector('.ak b')||{}).innerText || '',
                     kanji: (r.querySelector('.ak b')||{}).innerText || '',
                     less: (r.querySelector('.al')||{}).innerText || '',
                     audio: r.querySelector('.spk') ? (r.querySelector('.spk').getAttribute('data-audio')||'') : '' };
          });
        })()""")

    await call("Page.navigate", {"url": BASE + "index.html#/all/vocab"}, sid)
    for _ in range(30):
        if await js("!!document.querySelector('#allsort')"):
            break
        await asyncio.sleep(1)
    if not await ready():
        sys.exit("詞語總表沒有 render")
    # 清掉上一個 profile／上一次測試留下的排序選擇，再由乾淨狀態重載一次，
    # 否則 Page.navigate 到同一個帶 hash 的網址不會重載，頁內 VSORT 會沿用記憶中的值
    await js("localStorage.removeItem('ngs-vsort'); localStorage.removeItem('ngs-notebook-v1')")
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(30):
        if await js("!!document.querySelector('#allsort') && document.querySelectorAll('#alllist .arow').length"):
            break
        await asyncio.sleep(1)

    check("版本", await js("(document.querySelector('#verTag')||{}).innerText"), lambda s: s and s.startswith("v1"))
    check("排序控制存在", await js("!!document.querySelector('#allsort')"), True)
    check("兩個選項", await js("Array.prototype.map.call(document.querySelectorAll('#allsort [data-s]'), function(b){return b.innerText})"),
          ["課程順序", "五十音順"])
    check("預設課程順序", await js("document.querySelector('#allsort [data-s=\"lesson\"]').classList.contains('on')"), True)

    # --- 課程順序 ---
    check("課程順序項數", await js("document.querySelectorAll('#alllist .arow').length"), len(EXP_LESSON))
    check("課程順序無分段標題", await js("document.querySelectorAll('#alllist .khead').length"), 0)
    order0 = await rows()
    check("第一項是第 1 課", order0[0]["less"] if order0 else None, ITEMS[0][0])
    check("課程順序與資料一致", [(r["less"], r["kana"]) for r in order0],
          [(lid, v["kana"]) for lid, v in ITEMS])
    check("計數文字", await js("(document.querySelector('#allcnt')||{}).innerText"), "共 %d 項 · 40 課" % len(EXP_LESSON))

    # --- 切到五十音順 ---
    await js("document.querySelector('#allsort [data-s=\"kana\"]').click()")
    await asyncio.sleep(0.8)
    check("五十音順：項數不變", await js("document.querySelectorAll('#alllist .arow').length"), len(EXP_LESSON))
    check("五十音順：分段標題", await js("Array.prototype.map.call(document.querySelectorAll('#alllist .khead'), function(h){return h.innerText})"),
          EXP_ROWS)
    order1 = await rows()
    check("五十音順：整份次序與五十音鍵一致", [(r["less"], r["kana"]) for r in order1],
          [(lid, kana) for lid, kana, _ in EXP_LESSON])
    check("第一項是 あ行首項", order1[0]["kana"] if order1 else None, EXP_LESSON[0][1])
    check("片假名按讀音混入（アパート 在 あ行）",
          next((i for i, r in enumerate(order1) if r["kanji"] == "アパート"), -1) <
          next(i for i, r in enumerate(order1) if i > 0 and r["kana"].startswith("か")), True)
    dup_kana = [k for k, n in __import__('collections').Counter(k for _, k, _ in EXP_LESSON).items() if n > 1]
    kana_seq = [r["kana"] for r in order1]
    contiguous = True
    for k in dup_kana:
        idx = [i for i, s in enumerate(kana_seq) if s == k]
        if idx and idx != list(range(idx[0], idx[0] + len(idx))):
            contiguous = False
    check("同音詞相鄰（例如 きかい 機会／機械、あさって）", contiguous, True)
    check("計數文字（五十音順）", await js("(document.querySelector('#allcnt')||{}).innerText"),
          "共 %d 項 · 五十音順" % len(EXP_LESSON))
    check("每行都有音檔", all(r["audio"] for r in order1), True)
    check("390px 不橫向溢出", await js("document.documentElement.scrollWidth <= innerWidth"), True)
    check("排序選擇已儲存", await js("localStorage.getItem('ngs-vsort')"), "kana")

    # --- 重載後保留 ---
    await call("Page.reload", {"ignoreCache": True}, sid)
    for _ in range(30):
        if await js("document.querySelectorAll('#alllist .arow').length"):
            break
        await asyncio.sleep(1)
    check("重載後仍是五十音順", await js("document.querySelectorAll('#alllist .khead').length"), len(EXP_ROWS))
    check("重載後按鈕狀態", await js("document.querySelector('#allsort [data-s=\"kana\"]').classList.contains('on')"), True)

    # --- 搜尋在排序後清單內篩選 ---
    await js("""(function(){ var q=document.querySelector('#allq'); q.value='ホンコン';
                 q.dispatchEvent(new Event('input',{bubbles:true})); })()""")
    await asyncio.sleep(0.4)
    check("搜尋命中 1 項", await js("document.querySelectorAll('#alllist .arow').length"), 1)
    check("搜尋時隱藏分段標題", await js("document.querySelectorAll('#alllist .khead').length"), 0)
    check("搜尋結果文字", await js("(document.querySelector('#allcnt')||{}).innerText"),
          "找到 1 項（共 %d 項）" % len(EXP_LESSON))
    await js("""(function(){ var q=document.querySelector('#allq'); q.value='';
                 q.dispatchEvent(new Event('input',{bubbles:true})); })()""")
    await asyncio.sleep(0.4)
    check("清空搜尋後回復分段", await js("document.querySelectorAll('#alllist .khead').length"), len(EXP_ROWS))

    # --- ☆ 對應正確項目 ---
    await js("document.querySelectorAll('#alllist .arow .nbk')[0].click()")
    await asyncio.sleep(0.4)
    mine = await js("(JSON.parse(localStorage.getItem('ngs-notebook-v1')||'{\"items\":[]}').items||[]).map(function(x){return x.kana})")
    check("☆ 收藏第一項", mine, lambda m: m == [EXP_LESSON[0][1]])
    await js("document.querySelectorAll('#alllist .arow .nbk')[0].click()")
    await asyncio.sleep(0.3)
    check("再按取消收藏", await js("(JSON.parse(localStorage.getItem('ngs-notebook-v1')||'{\"items\":[]}').items||[]).length"), 0)

    # --- 切回課程順序 ---
    await js("document.querySelector('#allsort [data-s=\"lesson\"]').click()")
    await asyncio.sleep(0.6)
    check("切回課程順序：無分段", await js("document.querySelectorAll('#alllist .khead').length"), 0)
    back = await rows()
    check("切回課程順序：次序回復", [(r["less"], r["kana"]) for r in back],
          [(lid, v["kana"]) for lid, v in ITEMS])
    check("選擇已更新", await js("localStorage.getItem('ngs-vsort')"), "lesson")

    if os.environ.get("SHOT"):
        import base64
        await js("document.querySelector('#allsort [data-s=\"kana\"]').click()")
        await asyncio.sleep(0.6)
        r = await call("Page.captureScreenshot", {"format": "png"}, sid)
        with open(os.environ["SHOT"], "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot:", os.environ["SHOT"])

    print("RESULT", "PASS" if not fails else "FAIL " + ",".join(fails))
    await ws.close()
    proc.terminate()


asyncio.run(main())
