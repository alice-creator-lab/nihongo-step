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
    errors.push(`第 ${book.no} 階段應有 10 課，實際 ${(book.lessons || []).length}`);
  }
  for (const l of book.lessons || []) {
    total++;
    if (ids.has(l.id)) errors.push(`課號重複：${l.id}`);
    ids.add(l.id);
    if (!l.title) errors.push(`${l.id} 缺少課名`);
  }
}
if (total !== 40) errors.push(`全課程應為 40 課，實際 ${total}`);

/* 全 40 課的漢字→假名詞庫：句子裡的漢字詞，讀音必須跟單字表一致 */
const NAMES = { 李: 'り', 林: 'りん', 王: 'おう', 田中: 'たなか', 山田: 'やまだ', 佐藤: 'さとう', 鈴木: 'すずき' };
const GLOSS = Object.assign({}, NAMES);
/* 句型／文法可用的形標籤：前五個連去五段動詞詳細表，後五個連去「動詞的衍生形」 */
const FORM_KEYS = ['masu', 'te', 'ta', 'nai', 'dict', 'pot', 'vol', 'ba', 'pass', 'caus'];
for (const book of course.books || []) {
  for (const meta of book.lessons.filter((l) => l.available)) {
    try {
      const les = JSON.parse(readFileSync(join(ROOT, `data/lesson-${meta.id}.json`), 'utf8'));
      (les.vocab || []).forEach((v) => { if (v.kanji) GLOSS[v.kanji] = v.kana; });
    } catch (e) { /* 缺檔由下面主迴圈報錯 */ }
  }
}

/* 找出句子裡沒有任何單字表讀音可對照的漢字詞 */
function checkGloss(rel, where, ja) {
  if (!ja) return;
  const runs = ja.match(/[\u4e00-\u9fff々]+/g) || [];
  runs.forEach((run) => {
    if (GLOSS[run]) return;
    const covered = Object.keys(GLOSS).some((k) => k.length > 1 && run.indexOf(k) >= 0);
    if (!covered) warn.push(`${rel} ${where} 的「${run}」不在任何一課單字表，讀音無法自動核對`);
  });
}

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
      /* form 只可以是固定幾種形之一：masu／te／ta／nai／dict（五段動詞詳細表）
         與 pot／vol／ba／pass／caus（可能・意志・ば・受身・使役，連去衍生形頁）；
         一個句型同屬兩個形時寫成陣列（前端 PAT_FORM 對應顯示文字） */
      const pforms = 'form' in p ? (Array.isArray(p.form) ? p.form : [p.form]) : [];
      if (Array.isArray(p.form) && !p.form.length) {
        errors.push(`${rel} patterns[${i}].form 是空陣列`);
      }
      pforms.forEach((f) => {
        if (!FORM_KEYS.includes(f)) {
          errors.push(`${rel} patterns[${i}].form「${f}」不在 ${FORM_KEYS.join('／')} 之內`);
        }
      });
      (p.ex || []).forEach((x, j) => {
        if (!x.ja || !x.zh) errors.push(`${rel} patterns[${i}].ex[${j}] 需要 ja 與 zh`);
      });
    });
    (les.vocab || []).forEach((v, i) => {
      if (!v.kana || !v.zh || !v.pos) errors.push(`${rel} vocab[${i}] 需要 kana、zh、pos`);
      /* 詞性只用固定 8 類，避免同義標籤（い形／形容動詞／動詞（他動詞）…）再次混入；
         新增寫法請先用 tools/normalize_pos.py 的對照表收斂。 */
      if (v.pos && !['名詞', '動詞', 'い形容詞', 'な形容詞', '副詞', '代名詞', '連體詞', '其他'].includes(v.pos)) {
        errors.push(`${rel} vocab[${i}] 詞性「${v.pos}」不在固定 8 類之內`);
      }
    });
    (les.grammar || []).forEach((g, i) => {
      if (!g.h || !Array.isArray(g.p) || !g.p.length) errors.push(`${rel} grammar[${i}] 需要 h 與 p`);
      const gforms = 'form' in g ? (Array.isArray(g.form) ? g.form : [g.form]) : [];
      gforms.forEach((f) => {
        if (!FORM_KEYS.includes(f)) {
          errors.push(`${rel} grammar[${i}].form「${f}」不在 ${FORM_KEYS.join('／')} 之內`);
        }
      });
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
    const pairs = Object.assign({}, GLOSS);
    /* 逐個漢字詞核對：先看整個詞是否在詞庫，否則只比對兩個字以上的詞，
       避免「上手」中的「手」、「時間」中的「間」被單字讀音誤判 */
    /* 連濁容錯：カード会社 → がいしゃ、十分 → じゅっぷん */
    const VOICED = { か:'が', き:'ぎ', く:'ぐ', け:'げ', こ:'ご', さ:'ざ', し:'じ', す:'ず', せ:'ぜ', そ:'ぞ',
                     た:'だ', ち:'ぢ', つ:'づ', て:'で', と:'ど', は:'ば', ひ:'び', ふ:'ぶ', へ:'べ', ほ:'ぼ' };
    /* 同一個詞有兩種讀音（一日＝ついたち／いちにち、何＝なに／なん） */
    const ALT = { 一日: ['いちにち', 'ついたち'], 何: ['なに', 'なん'], 上: ['うえ', 'あげ', 'あが'], 分: ['ふん', 'ぷん', 'ぶん'] };
    function kanaHas(kana, reading, word) {
      if (kana.indexOf(reading) >= 0) return true;
      if ((ALT[word] || []).some((a) => kana.indexOf(a) >= 0)) return true;
      const v = VOICED[reading[0]];
      return !!v && kana.indexOf(v + reading.slice(1)) >= 0;
    }
    function checkReadings(where, ja, kana) {
      if (!ja || !kana) return;
      const runs = ja.match(/[\u4e00-\u9fff々]+/g) || [];
      runs.forEach((run) => {
        /* 只核對兩個字以上的詞，或整個人名（單字漢字在複合詞中讀音常變） */
        const nameKey = Object.keys(NAMES).find((n) => n === run);
        const word = pairs[run] && (run.length >= 2 || nameKey) ? run : null;
        if (word) {
          if (!kanaHas(kana, pairs[word], word)) {
            errors.push(`${rel} ${where} 的假名疑似讀錯：「${word}」應讀「${pairs[word]}」，但 kana 是「${kana}」`);
          }
          return;
        }
        Object.keys(pairs).forEach((w) => {
          if (w.length < 2 || run.indexOf(w) < 0) return;
          if (!kanaHas(kana, pairs[w], w)) {
            errors.push(`${rel} ${where} 的假名疑似讀錯：「${w}」應讀「${pairs[w]}」，但 kana 是「${kana}」`);
          }
        });
      });
    }

    /* 朗讀一律用假名，缺 kana 就會由 TTS 猜漢字讀音而出錯 */
    const KANJI = /[\u3400-\u9fff]/;
    function checkKana(where, ja, kana) {
      if (!kana) { errors.push(`${rel} ${where} 缺少 kana（朗讀需要假名）`); return; }
      if (KANJI.test(kana) && !KANJI.test(ja)) errors.push(`${rel} ${where} 的 kana 含有漢字：${kana}`);
      if (kana === ja && KANJI.test(ja)) errors.push(`${rel} ${where} 的 kana 與 ja 相同，應改為假名讀音`);
    }
    function both(where, x) { checkKana(where, x.ja, x.kana); checkReadings(where, x.ja, x.kana); checkGloss(rel, where, x.ja); }
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
  const shown = warn.slice(0, 25);
  for (const w of shown) console.warn('提示：' + w);
  if (warn.length > shown.length) console.warn(`提示：另有 ${warn.length - shown.length} 項漢字不在單字表（不影響校驗）`);
  // 每階段的單字數／句型數必須與課文一致（改課文後跑 tools/update_counts.py）
  for (const b of course.books) {
    let v = 0;
    let p = 0;
    for (const l of b.lessons) {
      const d = readJSON(`data/lesson-${l.id}.json`);
      if (!d) continue;
      v += (d.vocab || []).length;
      p += (d.patterns || []).length;
    }
    if (b.vocab !== v || b.patterns !== p) {
      errors.push(`第 ${b.no} 階段登記 ${b.vocab} 單字／${b.patterns} 句型，課文實為 ${v}／${p}；請執行 python3 tools/update_counts.py`);
    }
  }

  for (const e of errors) console.error('錯誤：' + e);
  console.log(errors.length ? `\n校驗失敗：${errors.length} 個錯誤` : `\n校驗通過：${ids.size} 課、${course.books.length} 階段`);
  return errors.length ? 1 : 0;
}

process.exit(report());
