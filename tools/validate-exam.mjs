/* 驗證階段測驗題目（data/exam-*.json）：
   四選一、選項不重複、答案索引有效、題號不重複、音檔真的存在。
   用法：node tools/validate-exam.mjs [1 2 3 4] */
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const stages = process.argv.slice(2).length ? process.argv.slice(2) : ['1', '2', '3', '4'];

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
    /* 熟字訓（整詞固定讀法）不可以逐字當成通則教：解釋要說明這一點。 */
    if (it.part === 'moji' && it.q) {
      const word = (it.q.match(/「(.+?)」/) || [])[1] || '';
      const JUKUJIKUN = ['浴衣', '眼鏡', '今日', '昨日', '明日', '今朝', '一人', '二人', '大人',
                         '田舎', '梅雨', '相撲', '土産', '紅葉', '上手', '下手'];
      if (JUKUJIKUN.includes(word) && !String(it.why).includes('熟字訓')) {
        fail(tag + ': 「' + word + '」是熟字訓，解釋要說明整詞讀法，不能逐字當通則');
      }
    }
    if (it.audio) {
      if (!existsSync(join(root, it.audio))) fail(tag + ': 音檔不存在 ' + it.audio);
      if (!it.script) fail(tag + ': 有音檔但缺 script（檢討時要看原文）');
    }
    if (!it.lesson) fail(tag + ': 缺 lesson 出處');

    /* 漢字読み題：解釋若逐字列出讀音（「生」は しょう…），串起來必須等於正確答案。
       讀音寫錯（例如「誕生日」的「生」寫成 しょう 而不是 じょう）就在這裡擋住。
       只在「每個漢字都講到」且沒有「ではなく」否定句時檢查，其餘留給人手看。 */
    if (it.part === 'moji' && it.why && it.options) {
      const KANA = /^[ぁ-ゖァ-ヺー]+$/;
      const ans = String(it.options[it.answer] || '').replace(/\s/g, '');
      const head = it.why.split('＝')[0];
      const kanji = (head.match(/[\u4e00-\u9fff]/g) || []).length;
      const pairs = [...it.why.matchAll(/「(.+?)」は\s*([ぁ-ゖァ-ヺー]+)(?:\s*が\s*濁って\s*([ぁ-ゖァ-ヺー]+))?/g)];
      if (KANA.test(ans) && !it.why.includes('ではなく') && pairs.length && pairs.length === kanji) {
        const rebuilt = pairs.map((m) => m[3] || m[2]).join('');
        if (rebuilt !== ans) {
          fail(tag + ': 解釋的逐字讀音串起來是「' + rebuilt + '」，與答案「' + ans + '」不符');
        }
      }
    }
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
