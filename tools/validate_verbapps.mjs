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
    if (!r.a) errs.push(`${where} 缺音檔編號`);
    else {
      if (seen.has(r.a)) errs.push(`音檔編號重複：${r.a}`);
      seen.add(r.a);
      const f = path.join(ROOT, 'audio/apps', r.a + '.mp3');
      if (!fs.existsSync(f) || fs.statSync(f).size < 2000) errs.push(`${where} 缺音檔 ${r.a}.mp3`);
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
