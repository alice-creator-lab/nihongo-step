// 驗證「讀音模式」的漢字比對：語音辨識把單音寫成漢字時，仍應判為答對。
// 直接由 kana/index.html 抽出 phonCands()，避免測試與實作各寫一份。
// 用法：node tools/test-kana-judge.mjs
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const html = fs.readFileSync(path.join(root, 'kana/index.html'), 'utf8');
const table = JSON.parse(fs.readFileSync(path.join(root, 'kana/kanji-readings.json'), 'utf8'));

const grab = (start, end) => {
  const i = html.indexOf(start);
  if (i < 0) throw new Error('找不到：' + start);
  const j = html.indexOf(end, i);
  if (j < 0) throw new Error('找不到結尾：' + end);
  return html.slice(i, j + end.length);
};
const src =
  grab('const KANJI_RE', ';') + '\n' +
  grab('function phonCands(s){', '\n  }') + '\n';
const KREAD = table;
const phonCands = new Function('KREAD', src + '\nreturn phonCands;')(KREAD);

// 與 judgeSpeakNow() 相同的判定式
const toHira = s => (s || '').replace(/[\u30a1-\u30f6]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
const clean = s => toHira((s || '').replace(/[\s、。．.,!?！？「」『』・…~\-—]/g, ''));
function judge(targetKana, alts) {
  const target = toHira(targetKana);
  const raw = alts.map(clean).filter(Boolean);
  const list = raw.slice();
  raw.forEach(a => phonCands(a).forEach(p => { if (list.indexOf(p) < 0) list.push(p); }));
  return !!(list.find(a => a === target) || list.find(a => a.includes(target)));
}

const cases = [
  // 螢幕截圖的個案：讀 め，辨識成「目」
  { kana: 'め', heard: ['目'], want: true },
  { kana: 'め', heard: ['女'], want: true },
  { kana: 'め', heard: ['メ'], want: true },
  { kana: 'め', heard: ['め'], want: true },
  { kana: 'か', heard: ['蚊'], want: true },
  { kana: 'き', heard: ['木'], want: true },
  { kana: 'て', heard: ['手'], want: true },
  { kana: 'ね', heard: ['根'], want: true },
  { kana: 'ち', heard: ['血'], want: true },
  { kana: 'う', heard: ['雨'], want: true },    // 雨 有 う 這個讀音：情願寬鬆判對，也不要誤判答錯
  { kana: 'ぬ', heard: ['目'], want: false },   // 讀錯就要維持答錯
  { kana: 'あ', heard: ['目'], want: false },
  { kana: 'め', heard: ['ぬ'], want: false },
  { kana: 'め', heard: ['め', 'ぬ'], want: true },  // 多個候選，其中一個命中
  { kana: 'きゃ', heard: ['きゃ'], want: true },
  { kana: 'きゃ', heard: ['きや'], want: false },
];

let bad = 0;
for (const c of cases) {
  const got = judge(c.kana, c.heard);
  const ok = got === c.want;
  if (!ok) bad++;
  console.log((ok ? 'PASS' : 'FAIL') + '  目標 ' + c.kana + ' · 聽到 ' + c.heard.join('|') + ' → ' + (got ? '答對' : '答錯'));
}
console.log(bad ? `\n${bad} 個個案不符預期` : '\n全部 ' + cases.length + ' 個個案符合預期');
process.exit(bad ? 1 : 0);
