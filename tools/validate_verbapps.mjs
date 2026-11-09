#!/usr/bin/env node
/* 校驗 data/verbapps.json（「不同形態的應用」頁）：
   每一行要有 pat／ex／l／a，a 不可重複，音檔 audio/apps/<a>.mp3 要存在，
   課號要是 L1–L40。用法：node tools/validate_verbapps.mjs */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/verbapps.json'), 'utf8'));
const errs = [];
const seen = new Set();
let rows = 0;

const FORMS = ['masu', 'dict', 'te', 'ta', 'nai'];
if ((d.groups || []).length !== FORMS.length) errs.push(`分組應為 ${FORMS.length} 組，實為 ${(d.groups || []).length}`);

for (const g of d.groups || []) {
  if (!FORMS.includes(g.id)) errs.push(`未知分組 id：${g.id}`);
  if (!g.form) errs.push(`分組 ${g.id} 缺 form`);
  if (!g.rows || !g.rows.length) errs.push(`分組 ${g.id} 沒有句型`);
  for (const r of g.rows || []) {
    rows++;
    const where = `${g.form} ${r.pat || '(缺 pat)'}`;
    if (!r.pat) errs.push(`${g.id} 有行缺 pat`);
    if (!r.ex) errs.push(`${where} 缺例句`);
    if (!r.tts) errs.push(`${where} 缺 tts 假名讀法`);
    if (!/^L([1-9]|[1-3]\d|40)$/.test(r.l || '')) errs.push(`${where} 課號不對：${r.l}`);
    /* 課號必須指到真的教這個句型的課：該課 patterns 內要有同一張句型卡。
       課本的動詞句型練習課號與 app 40 課的編排不同，照抄課本課號會指錯課。 */
    else {
      const f = path.join(ROOT, `data/lesson-L${String(r.l.slice(1)).padStart(2, '0')}.json`);
      let les = null;
      try { les = JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { errs.push(`${where} 找不到課文 ${path.basename(f)}`); }
      // 句型寫法不同的幾行：直接指定該課的句型卡原文
      const ALIAS = {
        'に行く': '～に行きます（目的）',
        '方': '～方（かた）',
        '前に、～': '～まえに',
        'ても構いません': '～てもかまいません',
        'た後で、～': '～たあとで',
      };
      if (les) {
        const clean = (s) => String(s).replace(/[～、，\s]/g, '');
        const pats = (les.patterns || []).map((p) => p.ja);
        const want = ALIAS[r.pat];
        const hit = want ? pats.includes(want)
          : pats.some((ja) => {
              const a = clean(ja), b = clean(r.pat);
              return b.length >= 2 && (a.includes(b) || b.includes(a));
            });
        if (!hit) errs.push(`${where} 課號 ${r.l} 的句型卡沒有這個句型`);
      }
    }
    if (!r.a) errs.push(`${where} 缺音檔編號`);
    else {
      if (seen.has(r.a)) errs.push(`音檔編號重複：${r.a}`);
      seen.add(r.a);
      const f = path.join(ROOT, 'audio/apps', r.a + '.mp3');
      if (!fs.existsSync(f) || fs.statSync(f).size < 2000) errs.push(`${where} 缺音檔 ${r.a}.mp3`);
    }
    /* hl＝例句內要用藍字標出的片段（句型部分）。必須是 ex 內依序出現的原文，
       否則畫面會靜靜地不標色。 */
    if (!Array.isArray(r.hl) || !r.hl.length) errs.push(`${where} 缺 hl 標示片段`);
    else {
      let rest = r.ex || '';
      for (const m of r.hl) {
        if (!m) { errs.push(`${where} hl 有空字串`); continue; }
        const i = rest.indexOf(m);
        if (i < 0) errs.push(`${where} hl「${m}」不在例句內或次序不對：${r.ex}`);
        else rest = rest.slice(i + m.length);
      }
    }
  }
}

const want = { masu: 10, dict: 4, te: 11, ta: 4, nai: 2 };
for (const g of d.groups || []) {
  if (want[g.id] && g.rows.length !== want[g.id]) {
    errs.push(`${g.form} 應有 ${want[g.id]} 個句型，實為 ${g.rows.length}`);
  }
}

if (errs.length) {
  errs.forEach((e) => console.log('錯誤：' + e));
  console.log(`\n共 ${errs.length} 個問題`);
  process.exit(1);
}
console.log(`校驗通過：${d.groups.length} 組、${rows} 個句型，音檔齊全`);
