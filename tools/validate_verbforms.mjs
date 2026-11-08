/* 驗證動詞詳細表（data/verbforms.json）：
   三組齊、五形齊全、全假名、指定例外正確、音檔存在、示範音檔只有兩行。
   用法：node tools/validate_verbforms.mjs */
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const d = JSON.parse(readFileSync(join(root, 'data/verbforms.json'), 'utf8'));

let bad = 0;
const fail = (msg) => { bad++; console.log('FAIL  ' + msg); };
const ok = (msg) => console.log('OK    ' + msg);

const KANA = /^[ぁ-ゖァ-ヺー]+$/;
const rows = [];
for (const s of d.sets || []) {
  if (!s.blocks?.length) fail(`${s.id}: blocks 缺失`);
  const n = (s.blocks || []).reduce((a, b) => a + b.rows.length, 0);
  if (n !== s.total) fail(`${s.id}: total ${s.total} ≠ 行數 ${n}`);
  for (const b of s.blocks || []) for (const r of b.rows) rows.push({ ...r, group: s.id, block: b.title });
}

if (d.sets?.length !== 3) fail(`sets 應為 3，實為 ${d.sets?.length}`);
if (rows.length !== 181) fail(`總行數應為 181，實為 ${rows.length}`);
else ok(`三組共 ${rows.length} 行（五段 ${d.sets[0].total}、一段 ${d.sets[1].total}、不規則 ${d.sets[2].total}）`);

const seen = new Set();
for (const r of rows) {
  const tag = `${r.group}/${r.kana}`;
  for (const f of ['kana', 'masu', 'te', 'ta', 'nai']) {
    if (typeof r[f] !== 'string' || !r[f]) fail(`${tag}: ${f} 空白`);
    else if (!KANA.test(r[f])) fail(`${tag}: ${f} 不是假名（${r[f]}）`);
  }
  if (r.kanji === r.kana) fail(`${tag}: kanji 與 kana 相同`);
  if (!Array.isArray(r.lessons) || !r.lessons.length) fail(`${tag}: lessons 空白`);
  const sig = r.group + '|' + r.kana + '|' + (r.kanji || '');
  if (seen.has(sig)) fail(`${tag}: 重複行（${r.kanji || '無漢字'}）`);
  seen.add(sig);
  for (const [name, rel] of Object.entries(r.audio || {})) {
    if (!existsSync(join(root, rel))) fail(`${tag}: 音檔不存在 ${name} → ${rel}`);
  }
}
if (!bad) ok('每行五形齊全、全假名、課號與音檔都在');

const find = (kana, kanji) => rows.find((r) => r.kana === kana && (!kanji || r.kanji === kanji));
const EXPECT = [
  ['いく', '行く', 'いきます', 'いって', 'いった', 'いかない'],
  ['ある', '', 'あります', 'あって', 'あった', 'ない'],
  ['くる', '来る', 'きます', 'きて', 'きた', 'こない'],
  ['する', '', 'します', 'して', 'した', 'しない'],
  ['たべる', '食べる', 'たべます', 'たべて', 'たべた', 'たべない'],
  ['かう', '買う', 'かいます', 'かって', 'かった', 'かわない'],
  ['はなす', '話す', 'はなします', 'はなして', 'はなした', 'はなさない'],
  ['しぬ', '死ぬ', 'しにます', 'しんで', 'しんだ', 'しなない'],
  ['あそぶ', '', 'あそびます', 'あそんで', 'あそんだ', 'あそばない'],
  ['よむ', '読む', 'よみます', 'よんで', 'よんだ', 'よまない'],
  ['かく', '書く', 'かきます', 'かいて', 'かいた', 'かかない'],
  ['およぐ', '', 'およぎます', 'およいで', 'およいだ', 'およがない'],
  ['いらっしゃる', '', 'いらっしゃいます', 'いらっしゃって', 'いらっしゃった', 'いらっしゃらない'],
  ['コピーする', '', 'コピーします', 'コピーして', 'コピーした', 'コピーしない'],
];
let expBad = 0;
for (const [kana, kanji, masu, te, ta, nai] of EXPECT) {
  const r = find(kana, kanji);
  if (!r) { fail(`找不到 ${kana}`); expBad++; continue; }
  const got = [r.masu, r.te, r.ta, r.nai].join('/');
  const want = [masu, te, ta, nai].join('/');
  if (got !== want) { fail(`${kana}: ${got} ≠ ${want}`); expBad++; }
}
if (!expBad) ok(`指定例外與規則範例 ${EXPECT.length} 條全部正確`);

/* 漢字：書上有的照書（歌う、習う…）；書上用假名的保留空白。 */
const KANJI = [
  ['うたう', '歌う'], ['ならう', '習う'], ['はたらく', '働く'], ['まにあう', '間に合う'],
  ['みがく', '磨く'], ['いそぐ', '急ぐ'], ['およぐ', '泳ぐ'], ['やすむ', '休む'],
  ['おわる', '終わる'], ['しる', '知る'], ['とおる', '通る'], ['とまる', '止まる'],
  ['のぼる', '登る'], ['のる', '乗る'], ['はしる', '走る'], ['ふる', '降る'],
  ['ねる', '寝る'], ['おしえる', '教える'], ['あける', '開ける'], ['しめる', '閉める'],
  ['すてる', '捨てる'], ['わすれる', '忘れる'], ['おぼえる', '覚える'], ['とめる', '止める'],
  ['なれる', '慣れる'], ['でる', '出る'], ['みせる', '見せる'], ['おきる', '起きる'],
  ['つく', '点く'], ['つく', '着く'], ['とる', '取る'], ['とる', '撮る'],
  ['よやくする', '予約する'], ['そうじする', '掃除する'], ['れんしゅうする', '練習する'],
];
let kbad = 0;
for (const [kana, kanji] of KANJI) {
  if (!rows.some((r) => r.kana === kana && r.kanji === kanji)) {
    fail(`找不到 ${kanji}（${kana}）`);
    kbad++;
  }
}
for (const kana of ['ある', 'いる', 'する', 'なる', 'わかる', 'あげる', 'くれる', 'もらう', 'つける', 'かける', 'できる', 'いらっしゃる']) {
  if (rows.some((r) => r.kana === kana && r.kanji)) { fail(`${kana} 應保留假名`); kbad++; }
}
if (!kbad) ok(`漢字 ${KANJI.length} 條與假名保留 ${12} 條全部符合`);

const withTe = rows.filter((r) => r.audio?.te);
const srcs = withTe.map((r) => r.src).sort().join(',');
if (srcs !== 'L06-0,L07-0') fail(`示範音檔應只有 L06-0、L07-0，實為 ${srcs}`);
else ok('示範音檔為行く（L06-0）與食べる（L07-0）兩行');

const badRows = rows.filter((r) => !r.audio?.dict).length;
if (badRows) console.log(`NOTE  ${badRows} 行沒有辞書形音檔`);

console.log(bad ? `\n${bad} 項未通過` : '\n全部通過');
process.exit(bad ? 1 : 0);
