#!/usr/bin/env node
/*
 * 課程內容校驗：確保 course.json 與各課 JSON 結構一致。
 * 用法：node tools/validate.mjs
 */
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const errors = [];
const warn = [];

function readJSON(rel) {
  const p = join(ROOT, rel);
  if (!existsSync(p)) {
    errors.push(`缺少檔案：${rel}`);
    return null;
  }
  try {
    return JSON.parse(readFileSync(p, 'utf8'));
  } catch (e) {
    errors.push(`JSON 解析失敗：${rel} — ${e.message}`);
    return null;
  }
}

const course = readJSON('data/course.json');
if (!course) process.exit(report());

let total = 0;
const ids = new Set();

for (const book of course.books || []) {
  if (!Array.isArray(book.lessons) || book.lessons.length !== 10) {
    errors.push(`第 ${book.no} 冊應有 10 課，實際 ${(book.lessons || []).length}`);
  }
  for (const l of book.lessons || []) {
    total++;
    if (ids.has(l.id)) errors.push(`課號重複：${l.id}`);
    ids.add(l.id);
    if (!l.title) errors.push(`${l.id} 缺少課名`);
  }
}
if (total !== 40) errors.push(`全課程應為 40 課，實際 ${total}`);

for (const book of course.books || []) {
  for (const meta of book.lessons.filter((l) => l.available)) {
    const rel = `data/lesson-${meta.id}.json`;
    const les = readJSON(rel);
    if (!les) continue;

    const need = ['id', 'book', 'no', 'title', 'titleJa', 'level', 'goal',
                  'patterns', 'vocab', 'grammar', 'exercises', 'dialogues', 'culture'];
    for (const k of need) if (!(k in les)) errors.push(`${rel} 缺少欄位 ${k}`);
    if (les.id !== meta.id) errors.push(`${rel} 的 id 與 course.json 不一致`);
    if (les.book !== book.no) errors.push(`${rel} 的 book 與 course.json 不一致`);

    (les.patterns || []).forEach((p, i) => {
      if (!p.ja || !p.zh) errors.push(`${rel} patterns[${i}] 需要 ja 與 zh`);
      (p.ex || []).forEach((x, j) => {
        if (!x.ja || !x.zh) errors.push(`${rel} patterns[${i}].ex[${j}] 需要 ja 與 zh`);
      });
    });
    (les.vocab || []).forEach((v, i) => {
      if (!v.kana || !v.zh || !v.pos) errors.push(`${rel} vocab[${i}] 需要 kana、zh、pos`);
    });
    (les.grammar || []).forEach((g, i) => {
      if (!g.h || !Array.isArray(g.p) || !g.p.length) errors.push(`${rel} grammar[${i}] 需要 h 與 p`);
    });
    (les.exercises || []).forEach((e, i) => {
      if (!e.q || !e.a) errors.push(`${rel} exercises[${i}] 需要 q 與 a`);
    });
    (les.dialogues || []).forEach((d, i) => {
      if (!d.scene || !Array.isArray(d.lines) || d.lines.length < 2) {
        errors.push(`${rel} dialogues[${i}] 需要 scene 與至少兩句`);
      }
      (d.lines || []).forEach((x, j) => {
        if (!x.who || !x.ja || !x.zh) errors.push(`${rel} dialogues[${i}].lines[${j}] 需要 who、ja、zh`);
      });
    });
    if (!les.culture || !les.culture.title || !(les.culture.paras || []).length) {
      errors.push(`${rel} culture 需要 title 與 paras`);
    }
    if ((les.vocab || []).length < 15) warn.push(`${rel} 單字只有 ${les.vocab.length} 個，初級每課通常 20 個以上`);
    /* 用單字表與人名表反查讀音：句子裡出現某個漢字詞，假名就要含它的讀音 */
    const NAMES = { 李: 'り', 林: 'りん', 王: 'おう', 田中: 'たなか', 山田: 'やまだ', 佐藤: 'さとう', 鈴木: 'すずき' };
    const pairs = {};
    (les.vocab || []).forEach((v) => { if (v.kanji) pairs[v.kanji] = v.kana; });
    Object.assign(pairs, NAMES);
    function checkReadings(where, ja, kana) {
      if (!ja || !kana) return;
      Object.keys(pairs).forEach((word) => {
        if (!ja.includes(word)) return;
        if (kana.indexOf(pairs[word]) < 0) {
          errors.push(`${rel} ${where} 的假名疑似讀錯：「${word}」應讀「${pairs[word]}」，但 kana 是「${kana}」`);
        }
      });
    }

    /* 朗讀一律用假名，缺 kana 就會由 TTS 猜漢字讀音而出錯 */
    const KANJI = /[\u3400-\u9fff]/;
    function checkKana(where, ja, kana) {
      if (!kana) { errors.push(`${rel} ${where} 缺少 kana（朗讀需要假名）`); return; }
      if (KANJI.test(kana) && !KANJI.test(ja)) errors.push(`${rel} ${where} 的 kana 含有漢字：${kana}`);
      if (kana === ja && KANJI.test(ja)) errors.push(`${rel} ${where} 的 kana 與 ja 相同，應改為假名讀音`);
    }
    function both(where, x) { checkKana(where, x.ja, x.kana); checkReadings(where, x.ja, x.kana); }
    (les.patterns || []).forEach((p, i) => (p.ex || []).forEach((x, j) => both(`patterns[${i}].ex[${j}]`, x)));
    (les.grammar || []).forEach((g, i) => (g.ex || []).forEach((x, j) => both(`grammar[${i}].ex[${j}]`, x)));
    (les.dialogues || []).forEach((d, i) => (d.lines || []).forEach((x, j) => both(`dialogues[${i}].lines[${j}]`, x)));

    (les.listening || []).forEach((x, i) => {
      if (!x.ja) errors.push(`${rel} listening[${i}] 缺少 ja`);
      checkKana(`listening[${i}]`, x.ja || '', x.kana);
      checkReadings(`listening[${i}]`, x.ja || '', x.kana);
      if (!Array.isArray(x.choices) || x.choices.length !== 4) {
        errors.push(`${rel} listening[${i}] 需要 4 個選項，實際 ${(x.choices || []).length}`);
      }
      if (typeof x.answer !== 'number' || x.answer < 0 || x.answer > 3) {
        errors.push(`${rel} listening[${i}] answer 必須是 0–3 的索引`);
      }
      const set = new Set((x.choices || []).map((c) => c.trim()));
      if (set.size !== (x.choices || []).length) errors.push(`${rel} listening[${i}] 選項有重複`);
    });
  }
}

function report() {
  for (const w of warn) console.warn('提示：' + w);
  for (const e of errors) console.error('錯誤：' + e);
  console.log(errors.length ? `\n校驗失敗：${errors.length} 個錯誤` : `\n校驗通過：${ids.size} 課、${course.books.length} 冊`);
  return errors.length ? 1 : 0;
}

process.exit(report());
