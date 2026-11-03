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
  }
}

function report() {
  for (const w of warn) console.warn('提示：' + w);
  for (const e of errors) console.error('錯誤：' + e);
  console.log(errors.length ? `\n校驗失敗：${errors.length} 個錯誤` : `\n校驗通過：${ids.size} 課、${course.books.length} 冊`);
  return errors.length ? 1 : 0;
}

process.exit(report());
