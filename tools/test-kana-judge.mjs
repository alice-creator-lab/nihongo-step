// 驗證「讀音模式」只認聲音：漢字／符號一律不接受（不判錯、不顯示），
// 假名則化成羅馬拼音後再核對。
// 直接由 kana/index.html 抽出 judgeSpeak()，測試跑的是真正上線的程式碼。
// 用法：node tools/test-kana-judge.mjs
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const html = fs.readFileSync(path.join(root, 'kana/index.html'), 'utf8');

// 由頁面的假名表建立 kana → 羅馬拼音
const ROMAJI = {};
for (const m of html.matchAll(/\[['"]([\u3041-\u3096\u30a1-\u30f6ー]{1,3})['"]\s*,\s*'([a-z]+)'/g)) {
  if (!(m[1] in ROMAJI)) ROMAJI[m[1]] = m[2];
}

const fnSrc = (() => {
  const i = html.indexOf('function judgeSpeak(alts){');
  if (i < 0) throw new Error('找不到 judgeSpeak');
  let depth = 0, j = i;
  for (; j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (!depth) break; }
  }
  return html.slice(i, j + 1);
})();
const helpers = html.slice(html.indexOf('const kanaOnly ='), html.indexOf('\n', html.indexOf('const normRom =')));
const toHira = s => (s || '').replace(/[\u30a1-\u30f6]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));

// 跑一次 judgeSpeak（每次重建狀態，等同新一題）
function run(kana, alts) {
  const stub = { cls: '', innerHTML: '', hidden: true, textContent: '' };
  const stats = { correct: 0, wrong: 0, streak: 0 };
  const wrongBook = [];
  const note = { textContent: '' };
  const body = `
    var answered = false, srMisses = 0, srAllowSkip = false;
    ${helpers}
    ${fnSrc}
    judgeSpeak(alts);
    return { answered: answered, misses: srMisses, skip: srAllowSkip, fb: fbSpeak.innerHTML, note: speakNote.textContent };
  `;
  const fn = new Function('mode', 'current', 'ROMAJI', 'toHira', 'stats', 'scope',
    'addWrong', 'dropWrong', 'showFeedback', 'updateStats', 'speakNextBtn', 'speakNote', 'fbSpeak', 'alts', body);
  const out = fn('speak', { k: kana }, ROMAJI, toHira, stats, 'all',
    k => wrongBook.push(k), () => {}, () => {}, () => {}, stub, note, stub, alts);
  return { ...out, stats, wrongBook };
}

const cases = [
  // [正解, 辨識結果, 期望: 'ok' | 'wrong' | 'ignore']
  ['め', ['め'], 'ok'],
  ['め', ['メ'], 'ok'],
  ['デ', ['で'], 'ok'],              // 片假名題、平假名結果：同一個音
  ['め', ['めー'], 'ok'],
  ['そ', ['そう'], 'ok'],            // 多了 う：一題只得一個音，只看第一個音節
  ['そ', ['それ'], 'ok'],
  ['きゃ', ['きゃく'], 'ok'],         // 拗音本身是一個音節
  ['そ', ['す'], 'wrong'],
  ['きゃ', ['きゃ'], 'ok'],
  ['め', ['目'], 'ignore'],          // 漢字不接受，但也不算答錯
  ['デ', ['(笑)'], 'ignore'],         // 符號雜訊
  ['め', ['目', 'め'], 'ok'],         // 多個候選，其中一個是假名
  ['ぬ', ['め'], 'wrong'],
  ['きゃ', ['きや'], 'wrong'],
];

let bad = 0;
for (const [kana, heard, want] of cases) {
  const r = run(kana, heard);
  const got = r.stats.correct ? 'ok' : r.stats.wrong ? 'wrong' : 'ignore';
  const pass = got === want;
  if (!pass) bad++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  正解 ${kana} · 聽到 ${heard.join('|')} → ${got}`
    + (got === 'ignore' ? `（備註：${r.note}）` : ''));
  if (want === 'ignore' && /目|笑/.test(r.fb + r.note)) {
    bad++;
    console.log('FAIL  畫面仍顯示了漢字／雜訊');
  }
}

// 連續兩次辨識不到假名 → 第二次才給「跳過」，且不計答錯
{
  const stub = { cls: '', innerHTML: '', hidden: true, textContent: '' };
  const stats = { correct: 0, wrong: 0, streak: 0 };
  const note = { textContent: '' };
  const body = `
    var answered = false, srMisses = 0, srAllowSkip = false;
    ${helpers}
    ${fnSrc}
    judgeSpeak(['目']);
    const firstSkip = srAllowSkip, firstNote = speakNote.textContent;
    judgeSpeak(['(笑)']);
    return { firstSkip: firstSkip, firstNote: firstNote, skip: srAllowSkip,
             label: speakNextBtn.textContent, shown: !speakNextBtn.hidden };
  `;
  const fn = new Function('mode', 'current', 'ROMAJI', 'toHira', 'stats', 'scope',
    'addWrong', 'dropWrong', 'showFeedback', 'updateStats', 'speakNextBtn', 'speakNote', 'fbSpeak', body);
  const r = fn('speak', { k: 'め' }, ROMAJI, toHira, stats, 'all',
    () => {}, () => {}, () => {}, () => {}, stub, note, stub);
  const pass = r.firstSkip === false && r.skip === true && r.shown && /跳過/.test(r.label) && stats.wrong === 0;
  if (!pass) bad++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  連續兩次無假名 → 第一次不給跳過，第二次給「${r.label}」，且不計答錯`);
}

console.log(bad ? `\n${bad} 個個案不符預期` : `\n全部 ${cases.length + 1} 個個案符合預期`);
process.exit(bad ? 1 : 0);
