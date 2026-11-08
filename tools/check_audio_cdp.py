#!/usr/bin/env python3
"""用 CDP 檢查人聲音檔有無接上：文法段、文法總表、聽力、對話。

用法： python3 tools/check_audio_cdp.py [http://127.0.0.1:8899/]
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import websockets

CANDIDATES = [
    "/home/admin/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome",
    "/home/admin/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
]
CHROME = next((c for c in CANDIDATES if os.path.exists(c)), None)
if not CHROME:
    sys.exit("找不 chromium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899/"
PORT = int(os.environ.get("CDP_PORT", "9333"))


async def main():
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--autoplay-policy=no-user-gesture-required",
         f"--remote-debugging-port={PORT}", "--user-data-dir=/tmp/cdp-prof-" + str(os.getpid()), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"))
            break
        except Exception:
            time.sleep(0.3)
    ws = await websockets.connect(ver["webSocketDebuggerUrl"], max_size=None)
    seq = [0]
    reqs = []

    async def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time()))
            except asyncio.TimeoutError:
                return
            m = json.loads(raw)
            if m.get("method") == "Network.requestWillBeSent":
                reqs.append(m["params"]["request"]["url"])

    async def call(method, params=None, sid=None, timeout=8):
        seq[0] += 1
        msg = {"id": seq[0], "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await ws.send(json.dumps(msg))
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.02, end - time.time()))
            except asyncio.TimeoutError:
                return None
            m = json.loads(raw)
            if m.get("method") == "Network.requestWillBeSent":
                reqs.append(m["params"]["request"]["url"])
            if m.get("id") == seq[0]:
                return m
        return None

    tid = (await call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    sid = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]
    await call("Network.enable", {}, sid)
    await call("Runtime.enable", {}, sid)

    async def js(expr, tries=2):
        for _ in range(tries):
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                                "awaitPromise": True}, sid, timeout=20)
            if r and "result" in r:
                return r["result"].get("result", {}).get("value")
        return None

    async def visit(hash_, wait=1.6):
        await js("location.hash='%s'; 1" % hash_)
        await pump(wait)

    async def wait_until(expr, secs=25):
        end = time.time() + secs
        while time.time() < end:
            v = await js(expr)
            if v:
                return v
            await pump(0.4)
        return None

    INSTR = ("(function(){ window.__played=[]; window.__rates=[]; window.__cur=null;"
             "var p=HTMLMediaElement.prototype.play;"
             "HTMLMediaElement.prototype.play=function(){window.__cur=this; window.__played.push(String(this.src||'').split('/audio/').pop());"
             "window.__times=window.__times||[]; window.__times.push(Date.now());"
             "window.__rates.push(this.playbackRate); return p.apply(this,arguments);};"
             "var s=window.speechSynthesis; if(s){var q=s.speak.bind(s); s.speak=function(u){window.__played.push('TTS:'+u.text); q(u);};}"
             "return 1; })()")

    await call("Page.navigate", {"url": BASE}, sid)
    await asyncio.sleep(3)

    out = {}
    out["首頁載入"] = await wait_until("document.querySelectorAll('#grammarCard, a[href=\"#/all/grammar\"]').length")

    # 1) 文法總表
    await visit("#/all/grammar", 2.5)
    await wait_until("document.querySelectorAll('#alllist .gex .spk').length")
    await js(INSTR)
    out["文法總表 例子喇叭"] = await js("document.querySelectorAll('#alllist .gex .spk').length")
    out["文法總表 有音檔"] = await js("document.querySelectorAll('#alllist .gex .spk[data-audio]').length")
    await js("document.querySelectorAll('#alllist .gex .spk')[0].click(); 1")
    await pump(1.2)
    out["文法總表 播放"] = await js("window.__played.slice(-1)")
    out["文法總表 用機械聲"] = await js("window.__played.some(x=>x.indexOf('TTS:')===0)")

    # 2) 課內文法段
    await visit("#/l/L01/grammar", 2.5)
    await wait_until("document.querySelectorAll('#seg .exrow .spk').length")
    await js(INSTR)
    out["課內文法 例子喇叭"] = await js("document.querySelectorAll('#seg .exrow .spk').length")
    out["課內文法 有音檔"] = await js("document.querySelectorAll('#seg .exrow .spk[data-audio]').length")
    await js("document.querySelectorAll('#seg .exrow .spk')[1].click(); 1")
    await pump(1.2)
    out["課內文法 播放"] = await js("window.__played.slice(-1)")
    out["課內文法 用機械聲"] = await js("window.__played.some(x=>x.indexOf('TTS:')===0)")

    # 2b) 句型：播放全部（順序播完全課例句）
    await visit("#/l/L01/patterns", 2.5)
    await wait_until("document.getElementById('pplayall')")
    await js(INSTR)
    out["句型 播放全部 按鈕"] = await js("document.getElementById('pplayall').textContent + '|' + document.querySelector('.vplaybar .cnt').textContent")
    await js("document.getElementById('pplayall').click(); 1")
    await pump(3.5)
    out["句型 播放全部 起播"] = await js("window.__played.slice(-1)")
    out["句型 播放全部 狀態"] = await js("document.getElementById('pplayall').textContent")
    await js("document.getElementById('pplayall').click(); 1")
    await pump(0.8)
    out["句型 播放全部 可停止"] = await js("document.getElementById('pplayall').textContent")

    # 3) 聽力
    await visit("#/l/L01/exercises", 2.5)
    await js("(function(){var b=[].find.call(document.querySelectorAll('button'),function(x){return x.textContent.indexOf('聽力')>=0;}); if(b){b.click(); return 1;} return 0;})()")
    await wait_until("document.getElementById('lplay')")
    await js(INSTR)
    await js("document.getElementById('lplay').click(); 1")
    await pump(1.2)
    out["聽力 播放"] = await js("[window.__played.slice(-1)[0], window.__rates.slice(-1)[0]]")
    out["聽力 已無慢速鍵"] = await js("!document.getElementById('lslow')")

    # 4) 對話整段（正常）
    await visit("#/l/L01/dialogue", 2.5)
    await wait_until("document.querySelector('[data-play]')")
    await js(INSTR)
    await js("document.querySelector('[data-play]').click(); 1")
    await pump(1.5)
    out["對話 播放"] = await js("window.__played.slice(-1)")

    # 5) 全域已無慢速：header 不應再有慢速鍵，播放一律原速
    out["header 無慢速鍵"] = await js("!document.getElementById('slowBtn')")
    out["播放速度全為 1"] = await js("window.__rates.every(r => r === 1)")

    # 6) 跟讀：示範按鈕也要用會話人聲（假名文字交給系統合成會讀成 ha）
    await visit("#/l/L01/dialogue", 2.5)
    await wait_until("document.querySelector('[data-speak]')")
    await js("document.querySelector('[data-speak]').click(); 1")
    await wait_until("document.getElementById('spkModel')")
    await js(INSTR)
    await js("document.getElementById('spkModel').click(); 1")
    await pump(1.5)
    out["跟讀 示範"] = await js("[window.__played.slice(-1)[0], window.__rates.slice(-1)[0]]")
    out["跟讀 用機械聲"] = await js("window.__played.some(x=>x.indexOf('TTS:')===0)")

    # 7) 詞語總表：播放全部
    await visit("#/all/vocab", 2.5)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    await js(INSTR)
    out["詞語總表 按鈕"] = await js("!!document.getElementById('allplay')")
    await js("document.getElementById('allplay').click(); 1")
    await pump(1.0)
    out["詞語總表 開始播"] = await js("[window.__played.slice(-1)[0], document.getElementById('allplay').textContent, document.querySelectorAll('#alllist .arow.playing').length]")
    await js("window.__cur && window.__cur.dispatchEvent(new Event('ended')); 1")
    await pump(1.0)
    out["詞語總表 續播"] = await js("window.__played.slice(-2)")
    await js("document.getElementById('allplay').click(); 1")
    await pump(0.6)
    out["詞語總表 停止"] = await js("[document.getElementById('allplay').textContent, document.querySelectorAll('#alllist .arow.playing').length]")

    # 8) 每課單字：播放全部
    await visit("#/l/L01/vocab", 2.5)
    await wait_until("document.querySelectorAll('#seg .vrow').length")
    await js(INSTR)
    out["課內單字 按鈕"] = await js("!!document.getElementById('vplayall')")
    await js("document.getElementById('vplayall').click(); 1")
    await pump(1.0)
    out["課內單字 開始播"] = await js("[window.__played.slice(-1)[0], document.getElementById('vplayall').textContent, document.querySelectorAll('#seg .vrow.playing').length]")
    await js("window.__cur && window.__cur.dispatchEvent(new Event('ended')); 1")
    await pump(1.0)
    out["課內單字 續播"] = await js("window.__played.slice(-2)")
    await js("document.getElementById('vplayall').click(); 1")
    await pump(0.6)
    out["課內單字 停止"] = await js("[document.getElementById('vplayall').textContent, document.querySelectorAll('#seg .vrow.playing').length]")

    # 9) 順序表：新分組與播放
    await visit("#/seq", 3)
    await wait_until("document.querySelectorAll('.sgrp').length")
    out["順序表 分組數"] = await js("document.querySelectorAll('.sgrp').length")
    out["順序表 ひとつ"] = await js("(function(){var s=[].find.call(document.querySelectorAll('.sgrp'),function(g){return g.textContent.indexOf('ひとつ')>=0;}); return s? s.querySelectorAll('.srow').length : -1;})()")
    out["順序表 金額變音"] = await js("(function(){var s=[].find.call(document.querySelectorAll('.sgrp'),function(g){return g.textContent.indexOf('百\u30fb千\u30fb萬')>=0;}); return s? s.querySelectorAll('.srow').length : -1;})()")
    await js(INSTR)
    await js("(function(){var s=[].find.call(document.querySelectorAll('.sgrp'),function(g){return g.textContent.indexOf('百\u30fb千\u30fb萬')>=0;}); s.querySelector('.splay').click(); return 1;})()")
    await pump(1.0)
    out["順序表 播放金額"] = await js("[window.__played.slice(-1)[0], document.querySelectorAll('.srow.playing').length]")
    # 量「播放全部」節奏：ひとつ 10 項連續播放 6 秒內播到第幾項、平均間隔
    await js("(function(){try{window.__times=[]; window.__played=[];}catch(e){} return 1;})()")
    await js("(function(){var s=[].find.call(document.querySelectorAll('.sgrp'),function(g){return g.textContent.indexOf('ひとつ')>=0;}); s.querySelector('.splay').click(); return 1;})()")
    await pump(6.0)
    out["ひとつ 6 秒內播段數"] = await js("window.__played.length")
    out["ひとつ 平均間隔(秒)"] = await js("(function(){var t=window.__times; if(t.length<2) return null; var g=[]; for(var i=1;i<t.length;i++) g.push(t[i]-t[i-1]); return Math.round(g.reduce(function(a,b){return a+b},0)/g.length)/1000;})()")
    await js("(function(){var s=[].find.call(document.querySelectorAll('.sgrp'),function(g){return g.textContent.indexOf('ひとつ')>=0;}); s.querySelector('.splay').click(); return 1;})()")
    await pump(0.5)

    # 10) 練習本：收藏 → 列表 → 播放全部 → 卡片練習
    await js("localStorage.removeItem('ngs-notebook-v1'); 1")
    await visit("#/l/L01/vocab", 2.5)
    await wait_until("document.querySelectorAll('#seg .vrow .nbk').length")
    out["單字表 有收藏鍵"] = await js("document.querySelectorAll('#seg .vrow .nbk').length")
    await js("document.querySelectorAll('#seg .vrow .nbk')[0].click(); document.querySelectorAll('#seg .vrow .nbk')[1].click(); 1")
    await pump(0.5)
    out["收藏後"] = await js("[JSON.parse(localStorage.getItem('ngs-notebook-v1')).items.length, document.querySelectorAll('#seg .vrow .nbk.on').length]")

    # 詞語總表同樣可以收藏
    await visit("#/all/vocab", 2.5)
    await wait_until("document.querySelectorAll('#alllist .arow .nbk').length")
    await js("document.querySelectorAll('#alllist .arow .nbk')[0].click(); 1")
    await pump(0.5)
    out["詞語總表 收藏"] = await js("[JSON.parse(localStorage.getItem('ngs-notebook-v1')).items.length, document.querySelectorAll('#alllist .arow .nbk.on').length]")

    await visit("#/note", 2.5)
    await wait_until("document.querySelectorAll('#notebody .nrow').length")
    out["練習本 列數"] = await js("document.querySelectorAll('#notebody .nrow').length")
    await js(INSTR)
    await js("document.getElementById('nbPlay').click(); 1")
    await pump(1.0)
    out["練習本 播放全部"] = await js("[window.__played.slice(-1)[0], document.getElementById('nbPlay').textContent]")
    await js("document.getElementById('nbPlay').click(); 1")
    await pump(0.4)
    await js("document.getElementById('nbStart').click(); 1")
    await pump(0.6)
    out["練習本 卡片"] = await js("[!!document.getElementById('fcard'), document.querySelector('.cardmeta').textContent]")
    await js("document.getElementById('reveal').click(); 1")
    await pump(0.3)
    out["練習本 看答案"] = await js("[document.getElementById('fback').classList.contains('hide'), document.getElementById('know').style.display]")
    await js("document.getElementById('know').click(); 1")
    await pump(0.5)
    out["練習本 下一題"] = await js("document.querySelector('.cardmeta').textContent")
    await js("document.getElementById('reveal').click(); document.getElementById('dunno').click(); 1")
    await pump(0.6)
    out["練習本 完成"] = await js("[!!document.querySelector('.sum .big'), window.localStorage.getItem('ngs-mistakes-v1').indexOf('word')>0]")
    await js("document.getElementById('nbBack').click(); 1")
    await pump(0.5)
    out["練習本 返回"] = await js("document.querySelectorAll('#notebody .nrow').length")

    await visit("#/", 2)
    out["首頁 練習本入口"] = await js("(function(){var a=document.querySelector('a[href=\"#/note\"]'); return a? a.textContent.replace(/\\s+/g,' ').trim() : null;})()")

    # 11) 動詞表／形容詞表
    await visit("#/all/verbs", 2.5)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    out["動詞表 分組"] = await js("(function(){return [].map.call(document.querySelectorAll('#alllist .wth'),function(h){return h.textContent;});})()")
    out["動詞表 行數"] = await js("document.querySelectorAll('#alllist .arow').length")
    await js(INSTR)
    await js("document.querySelectorAll('#alllist .arow .spk')[0].click(); 1")
    await pump(1.0)
    out["動詞表 播放"] = await js("window.__played.slice(-1)")
    await js("(function(){var i=document.getElementById('allq'); i.value='たべ'; i.dispatchEvent(new Event('input')); return 1;})()")
    await pump(0.6)
    out["動詞表 搜尋たべ"] = await js("[document.querySelectorAll('#alllist .arow').length, document.getElementById('allcnt').textContent]")
    await js("(function(){var i=document.getElementById('allq'); i.value=''; i.dispatchEvent(new Event('input')); return 1;})()")
    await pump(0.5)
    await js("document.querySelectorAll('#alllist .arow .nbk')[0].click(); 1")
    await pump(0.4)
    out["動詞表 收藏"] = await js("(function(){var n=JSON.parse(localStorage.getItem('ngs-notebook-v1')).items[0]; return [n.kanji, n.kana, n.audio];})()")

    await visit("#/all/adjs", 2.5)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    out["形容詞表 分組"] = await js("(function(){return [].map.call(document.querySelectorAll('#alllist .wth'),function(h){return h.textContent;});})()")
    out["形容詞表 行數"] = await js("document.querySelectorAll('#alllist .arow').length")

    await visit("#/note", 2.5)
    await wait_until("document.querySelectorAll('#notebody .nrow').length")
    await js(INSTR)
    await js("document.getElementById('nbPlay').click(); 1")
    await pump(1.0)
    out["練習本 播動詞"] = await js("window.__played.slice(-1)")

    # 12) 形容詞的變化：入口在形容詞表頂部，16 個形式都要接到音檔
    await visit("#/all/adjs", 2.5)
    await wait_until("document.querySelectorAll('#alllist .arow').length")
    out["形容詞表 變化入口"] = await js("(function(){var a=document.querySelector('a.afentry'); return a? [a.getAttribute('href'), a.textContent.replace(/\\s+/g,' ').trim()] : null;})()")
    await js("document.querySelector('a.afentry').click(); 1")
    await pump(1.2)
    await wait_until("document.querySelectorAll('.afrow').length")
    out["形容詞變化 行數"] = await js("document.querySelectorAll('.afrow').length")
    out["形容詞變化 喇叭數"] = await js("document.querySelectorAll('.afrow .spk[data-audio]').length")
    out["形容詞變化 標題"] = await js("document.querySelector('.lhead h1').textContent")
    await js(INSTR)
    played = []
    for k in range(16):
        await js("document.querySelectorAll('.afrow .spk')[%d].click(); 1" % k)
        await pump(0.35)
        played.append(await js("window.__played.slice(-1)[0]"))
    want = await js("Array.prototype.map.call(document.querySelectorAll('.afrow .spk'), function(b){return b.getAttribute('data-audio').split('/').slice(-2).join('/');})")
    out["形容詞變化 播放順序"] = [p.split("?")[0] for p in played]
    out["形容詞變化 每行播對"] = bool(want) and [p.split("?")[0] for p in played] == want
    out["形容詞變化 16 段齊"] = len(set(want or [])) == 16
    out["形容詞變化 未落 TTS"] = not any(str(p).startswith("TTS:") for p in played)
    await js("document.querySelector('.lhead .back').click(); 1")
    await pump(1.0)
    out["形容詞變化 返回表"] = await js("(document.querySelectorAll('#alllist .arow').length > 0) && location.hash")

    out["頁面錯誤"] = await js("(window.__errs||[]).length")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    proc.terminate()
    await ws.close()


asyncio.run(main())
