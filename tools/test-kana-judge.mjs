// 驗證「讀音模式」的判定規則：
//  - 只認五十音表上的一個音（清音／濁音／半濁音／拗音）
//  - 漢字、符號、表外的音（ねぇ）一律不顯示、不判錯
//  - 表上有的音但聽錯：先給一次機會，第二次才判錯
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

// 依序餵多次辨識結果，回傳每次之後的狀態（等同同一題重錄）
function runSeq(kana, seq) {
  const stub = { cls: '', innerHTML: '', hidden: true, textContent: '' };
  const stats = { correct: 0, wrong: 0, streak: 0 };
  const wrongBook = [];
  const note = { textContent: '' };
  const body = `
    var answered = false, srMisses = 0, srAllowSkip = false, srRetried = false;
    ${helpers}
    ${fnSrc}
    const snaps = [];
    for(const alts of seq){
      fbSpeak.innerHTML = '';
      judgeSpeak(alts);
      snaps.push({ answered: answered, correct: stats.correct, wrong: stats.wrong,
                   fb: fbSpeak.innerHTML, note: speakNote.textContent,
                   skip: srAllowSkip, nextLabel: speakNextBtn.textContent, nextShown: !speakNextBtn.hidden });
    }
    return snaps;
  `;
  const fn = new Function('mode', 'current', 'ROMAJI', 'toHira', 'stats', 'scope',
    'addWrong', 'dropWrong', 'showFeedback', 'updateStats', 'speakNextBtn', 'speakNote', 'fbSpeak', 'seq', body);
  const snaps = fn('speak', { k: kana }, ROMAJI, toHira, stats, 'all',
    k => wrongBook.push(k), () => {}, () => {}, () => {}, stub, note, stub, seq);
  return { snaps, stats, wrongBook };
}

const cases = [
  // [正解, 辨識序列, 期望（每次一個）]
  ['め', [['め']], ['ok']],
  ['め', [['メ']], ['ok']],
  ['デ', [['で']], ['ok']],
  ['め', [['めー']], ['ok']],
  ['そ', [['そう']], ['ok']],              // 多出嚟的音不理
  ['そ', [['それ']], ['ok']],
  ['きゃ', [['きゃく']], ['ok']],           // 拗音是一個音節
  ['め', [['目']], ['retry']],            // 漢字不接受、不顯示
  ['め', [['ねぇ']], ['retry']],           // 表外的音不接受、不顯示
  ['デ', [['(笑)']], ['retry']],
  ['め', [['目', 'め']], ['ok']],           // 多個候選，其中一個命中
  ['ぬ', [['ど'], ['ど']], ['retry', 'wrong']],   // 聽錯先給一次機會
  ['ぬ', [['ど'], ['ぬ']], ['retry', 'ok']],      // 第二次讀對就答對
  ['ぬ', [['め']], ['retry']],              // 只有一次機會，唔會即刻判錯
  ['きゃ', [['きや'], ['きや']], ['retry', 'wrong']],
];

let bad = 0;
for (const [kana, seq, want] of cases) {
  const r = runSeq(kana, seq);
  const got = r.snaps.map(s => (s.correct ? 'ok' : s.wrong ? 'wrong' : 'retry'));
  const pass = got.length === want.length && got.every((g, i) => g === want[i]);
  if (!pass) bad++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  正解 ${kana} · 餵 ${seq.map(a => a.join('|')).join(' → ')} → ${got.join(' → ')}`
    + `  最後備註：${r.snaps[r.snaps.length - 1].note || r.snaps[r.snaps.length - 1].fb}`);
  // 表外的音／漢字／雜訊不可以出現在畫面文字
  const shown = r.snaps.map(s => s.fb + s.note).join(' ');
  if (/ねぇ|目|笑/.test(shown)) {
    bad++;
    console.log('FAIL  畫面仍顯示了不該出現的辨識結果');
  }
}

// 連續兩次都收不到表上的音 → 第二次才給「跳過」，且不計答錯
{
  const r = runSeq('め', [['目'], ['(笑)']]);
  const [a, b] = r.snaps;
  const pass = a.skip === false && b.skip === true && b.nextShown && /跳過/.test(b.nextLabel) && r.stats.wrong === 0;
  if (!pass) bad++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  連續兩次收不到音 → 第二次給「${b.nextLabel}」，且不計答錯`);
}

console.log(bad ? `\n${bad} 個個案不符預期` : `\n全部 ${cases.length + 1} 個個案符合預期`);
process.exit(bad ? 1 : 0);
