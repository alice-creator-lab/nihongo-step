#!/usr/bin/env node
/*
 * 單課內容校驗：只檢查一個 lesson JSON，規則與 tools/validate.mjs 相同。
 * 用法：node tools/validate-one.mjs data/lesson-L07.json
 */
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const rel = process.argv[2];
if (!rel) {
  console.error('用法：node tools/validate-one.mjs data/lesson-L07.json');
  process.exit(2);
}
const path = join(ROOT, rel);
if (!existsSync(path)) {
  console.error(`找不到檔案：${rel}`);
  process.exit(2);
}

let les;
try {
  les = JSON.parse(readFileSync(path, 'utf8'));
} catch (e) {
  console.error(`JSON 解析失敗：${rel} — ${e.message}`);
  process.exit(1);
}

const errors = [];
const warn = [];
const need = ['id', 'book', 'no', 'title', 'titleJa', 'level', 'goal',
              'patterns', 'vocab', 'grammar', 'exercises', 'dialogues', 'culture'];
for (const k of need) if (!(k in les)) errors.push(`缺少欄位 ${k}`);
if (les.id && basename(rel) !== `lesson-${les.id}.json`) errors.push(`檔名與 id 不一致（${les.id}）`);

(les.patterns || []).forEach((p, i) => {
  if (!p.ja || !p.zh) errors.push(`patterns[${i}] 需要 ja 與 zh`);
  if (!Array.isArray(p.ex) || p.ex.length < 2) errors.push(`patterns[${i}] 需要至少 2 句例句 ex`);
  (p.ex || []).forEach((x, j) => {
    if (!x.ja || !x.zh) errors.push(`patterns[${i}].ex[${j}] 需要 ja 與 zh`);
  });
});
if ((les.patterns || []).length < 4) errors.push('patterns 至少 4 條句型');

(les.vocab || []).forEach((v, i) => {
  if (!v.kana || !v.zh || !v.pos) errors.push(`vocab[${i}] 需要 kana、zh、pos`);
});
if ((les.vocab || []).length < 18) errors.push(`單字只有 ${(les.vocab || []).length} 個，每課至少 18 個`);

(les.grammar || []).forEach((g, i) => {
  if (!g.h || !Array.isArray(g.p) || !g.p.length) errors.push(`grammar[${i}] 需要 h 與 p`);
});
if ((les.grammar || []).length < 5) errors.push('grammar 至少 5 節');

(les.exercises || []).forEach((e, i) => {
  if (!e.q || !e.a) errors.push(`exercises[${i}] 需要 q 與 a`);
  if (!e.type) errors.push(`exercises[${i}] 需要 type（fill／rewrite／free）`);
  if (e.type !== 'free' && !Array.isArray(e.answers)) errors.push(`exercises[${i}] 非 free 需要 answers 陣列`);
  if (e.type === 'free' && !e.model) errors.push(`exercises[${i}] free 需要 model`);
});
if ((les.exercises || []).length < 6) errors.push('exercises 至少 6 題');

(les.dialogues || []).forEach((d, i) => {
  if (!d.scene || !Array.isArray(d.lines) || d.lines.length < 4) {
    errors.push(`dialogues[${i}] 需要 scene 與至少 4 句`);
  }
  (d.lines || []).forEach((x, j) => {
    if (!x.who || !x.ja || !x.zh) errors.push(`dialogues[${i}].lines[${j}] 需要 who、ja、zh`);
  });
});
if ((les.dialogues || []).length < 2) errors.push('dialogues 至少 2 段');

if (!les.culture || !les.culture.title || !(les.culture.paras || []).length) {
  errors.push('culture 需要 title 與 paras');
}
if ((les.listening || []).length < 6) errors.push('listening 至少 6 題');

const NAMES = { 李: 'り', 林: 'りん', 王: 'おう', 田中: 'たなか', 山田: 'やまだ', 佐藤: 'さとう', 鈴木: 'すずき' };
const pairs = {};
(les.vocab || []).forEach((v) => { if (v.kanji) pairs[v.kanji] = v.kana; });
Object.assign(pairs, NAMES);

function checkReadings(where, ja, kana) {
  if (!ja || !kana) return;
  Object.keys(pairs).forEach((word) => {
    if (!ja.includes(word)) return;
    if (kana.indexOf(pairs[word]) < 0) {
      errors.push(`${where} 的假名疑似讀錯：「${word}」應讀「${pairs[word]}」，但 kana 是「${kana}」`);
    }
  });
}
const KANJI = /[\u3400-\u9fff]/;
function checkKana(where, ja, kana) {
  if (!kana) { errors.push(`${where} 缺少 kana（朗讀需要假名）`); return; }
  if (KANJI.test(kana) && !KANJI.test(ja)) errors.push(`${where} 的 kana 含有漢字：${kana}`);
  if (kana === ja && KANJI.test(ja)) errors.push(`${where} 的 kana 與 ja 相同，應改為假名讀音`);
}
function both(where, x) { checkKana(where, x.ja, x.kana); checkReadings(where, x.ja, x.kana); }
(les.patterns || []).forEach((p, i) => (p.ex || []).forEach((x, j) => both(`patterns[${i}].ex[${j}]`, x)));
(les.grammar || []).forEach((g, i) => (g.ex || []).forEach((x, j) => both(`grammar[${i}].ex[${j}]`, x)));
(les.dialogues || []).forEach((d, i) => (d.lines || []).forEach((x, j) => both(`dialogues[${i}].lines[${j}]`, x)));

(les.listening || []).forEach((x, i) => {
  if (!x.ja) errors.push(`listening[${i}] 缺少 ja`);
  checkKana(`listening[${i}]`, x.ja || '', x.kana);
  checkReadings(`listening[${i}]`, x.ja || '', x.kana);
  if (!Array.isArray(x.choices) || x.choices.length !== 4) {
    errors.push(`listening[${i}] 需要 4 個選項，實際 ${(x.choices || []).length}`);
  }
  if (typeof x.answer !== 'number' || x.answer < 0 || x.answer > 3) {
    errors.push(`listening[${i}] 的 answer 必須是 0–3 的數字`);
  }
});

(les.exercises || []).forEach((e, i) => {
  if (e.kana) checkKana(`exercises[${i}]`, e.a, e.kana);
});

if (warn.length) warn.forEach((w) => console.warn(`提示：${w}`));
if (errors.length) {
  errors.forEach((e) => console.error(`錯誤：${e}`));
  console.error(`\n校驗失敗：${errors.length} 個錯誤`);
  process.exit(1);
}
console.log(`校驗通過：${rel}（${(les.vocab || []).length} 字、${(les.patterns || []).length} 句型、${(les.grammar || []).length} 節文法、${(les.exercises || []).length} 題、${(les.listening || []).length} 題聽力）`);
