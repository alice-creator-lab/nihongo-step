/* 驗證階段測驗題目（data/exam-*.json）：
   四選一、選項不重複、答案索引有效、題號不重複、音檔真的存在。
   用法：node tools/validate-exam.mjs [1 2 3 4] */
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const stages = process.argv.slice(2).length ? process.argv.slice(2) : ['1'];

let bad = 0;
const fail = (msg) => { bad++; console.log('FAIL  ' + msg); };

for (const stage of stages) {
  const file = join(root, 'data', 'exam-' + stage + '.json');
  if (!existsSync(file)) { fail('找不到 ' + file); continue; }
  const d = JSON.parse(readFileSync(file, 'utf8'));

  if (!Array.isArray(d.parts) || !d.parts.length) fail('stage ' + stage + ': parts 缺失');
  if (!Array.isArray(d.items) || !d.items.length) fail('stage ' + stage + ': items 缺失');
  if (Number(d.stage) !== Number(stage)) fail('stage ' + stage + ': stage 欄位不符（' + d.stage + '）');

  const partKeys = new Set((d.parts || []).map((p) => p.key));
  const ids = new Set();
  const counts = {};

  for (const it of d.items || []) {
    const tag = 'stage ' + stage + ' / ' + it.id;
    if (ids.has(it.id)) fail(tag + ': id 重複');
    ids.add(it.id);
    if (!partKeys.has(it.part)) fail(tag + ': part「' + it.part + '」不在 parts');
    counts[it.part] = (counts[it.part] || 0) + 1;

    if (!it.kind) fail(tag + ': 缺 kind');
    if (!it.q) fail(tag + ': 缺題目 q');
    if (!it.why) fail(tag + ': 缺解釋 why');
    if (!Array.isArray(it.options) || it.options.length !== 4) fail(tag + ': 選項不是四個');
    else {
      if (new Set(it.options).size !== 4) fail(tag + ': 選項有重複');
      if (it.options.some((o) => !String(o || '').trim())) fail(tag + ': 有空選項');
    }
    if (!Number.isInteger(it.answer) || it.answer < 0 || it.answer > 3) fail(tag + ': answer 不是 0–3');

    /* 並べ替え：order 是正確語序（選項索引），★ 是第三格 → 一定要等於 answer。
       只寫 answer 很容易把「第幾個位置」同「第幾個選項」搞亂。 */
    if (it.kind === '文の組み立て') {
      if (!Array.isArray(it.order) || it.order.length !== 4 || new Set(it.order).size !== 4 ||
          it.order.some((v) => !Number.isInteger(v) || v < 0 || v > 3)) {
        fail(tag + ': 並べ替え要有 order（四個選項索引的正確語序）');
      } else if (it.order[2] !== it.answer) {
        fail(tag + ': ★ 應是 order[2]＝' + it.order[2] + '，但 answer＝' + it.answer);
      }
    }
    if (it.audio) {
      if (!existsSync(join(root, it.audio))) fail(tag + ': 音檔不存在 ' + it.audio);
      if (!it.script) fail(tag + ': 有音檔但缺 script（檢討時要看原文）');
    }
    if (!it.lesson) fail(tag + ': 缺 lesson 出處');
  }

  const total = (d.items || []).length;
  console.log('stage ' + stage + '  ' + d.title + '  ' + total + ' 題  ' +
    Object.keys(counts).map((k) => k + ' ' + counts[k]).join(' · '));
  for (const p of d.parts || []) {
    if (!counts[p.key]) fail('stage ' + stage + ': 部分「' + p.label + '」沒有任何題目');
  }
}

console.log(bad ? '有 ' + bad + ' 項未通過' : '全部通過');
process.exit(bad ? 1 : 0);
