// 驗證「鍵盤輸入」模式的判定規則：
//  - 只認五十音表上的一個音（清音／濁音／半濁音／拗音）
//  - 打羅馬拼音也接受
//  - 漢字、符號、表外的音（ねぇ、目、2）不算答案，也不判錯
// 直接由 kana/index.html 抽出 judgeTyped()，測試跑的是真正上線的程式碼。
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
  const i = html.indexOf('function judgeTyped(');
  if (i < 0) throw new Error('找不到 judgeTyped');
  let depth = 0, j = i;
  for (; j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}') { depth--; if (!depth) break; }
  }
  return html.slice(i, j + 1);
})();
const helpers = html.slice(html.indexOf('const kanaOnly ='), html.indexOf('\n', html.indexOf('const VALID_ROM =')));
const toHira = s => (s || '').replace(/[\u30a1-\u30f6]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
const BY_ROMAJI = {};
for (const [k, r] of Object.entries(ROMAJI)) if (!BY_ROMAJI[r]) BY_ROMAJI[r] = k;

const judgeTyped = new Function('toHira', 'ROMAJI', 'BY_ROMAJI', `${helpers}\n${fnSrc}\nreturn judgeTyped;`)(toHira, ROMAJI, BY_ROMAJI);

const cases = [
  // [正解, 輸入, 期望 status]
  ['ぬ', 'ぬ', 'ok'],
  ['ぬ', 'ヌ', 'ok'],              // 片假名同樣算對
  ['デ', 'で', 'ok'],
  ['め', 'めー', 'ok'],            // 長音符不影響
  ['そ', 'そう', 'ok'],            // 只看第一個音節
  ['きゃ', 'きゃく', 'ok'],         // 拗音是一個音節
  ['ぬ', 'nu', 'ok'],              // 打羅馬拼音也接受
  ['ぬ', 'nuu', 'ok'],
  ['を', 'o', 'ok'],
  ['ぬ', 'ど', 'wrong'],
  ['きゃ', 'きや', 'wrong'],        // きや 不是 きゃ
  ['ぬ', '', 'empty'],
  ['め', '目', 'empty'],           // 漢字不算答案，也不判錯
  ['め', 'ねぇ', 'empty'],          // 表外的音
  ['め', '2', 'empty'],
  ['デ', '(笑)', 'empty'],
];

let bad = 0;
for (const [kana, typed, want] of cases) {
  const r = judgeTyped(typed, kana);
  const pass = r.status === want;
  if (!pass) bad++;
  console.log(`${pass ? 'PASS' : 'FAIL'}  正解 ${kana} · 輸入「${typed}」→ ${r.status}${r.unit ? '（' + r.unit + '）' : ''}`);
}

// 表外的輸入永遠不可以被判錯，也不可以回傳 unit 給畫面顯示
for (const junk of ['目', 'ねぇ', '2', '(笑)', '今日', 'P']) {
  const r = judgeTyped(junk, 'め');
  if (r.status === 'wrong' || r.unit) {
    bad++;
    console.log(`FAIL  表外的「${junk}」被判成 ${r.status}（unit=${r.unit}）`);
  }
}

console.log(bad ? `\n${bad} 個個案不符預期` : `\n全部 ${cases.length + 1} 個個案符合預期`);
process.exit(bad ? 1 : 0);
