/* 測試收音的自動停止判斷：句子有標點，中間停頓唔可以當講完。
   由 index.html 抽出 vadStep 與常數，餵合成音量序列。
   用法：node tools/test-vad.mjs */
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const num = (name) => Number(html.match(new RegExp('var ' + name + ' = ([0-9.]+)'))[1]);
const SIL = num('VAD_SILENCE_MS');
const TH = num('VAD_SPEAK_RMS');

const start = html.indexOf('function vadStep(');
const end = html.indexOf('\n  }\n', start) + 4;
const vadStep = new Function('VAD_SPEAK_RMS', 'VAD_SILENCE_MS', html.slice(start, end) + '\nreturn vadStep;')(TH, SIL);

let bad = 0;
const check = (name, ok, info) => { if (!ok) bad++; console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (info ? '  ' + info : '')); };

// 餵一段音量序列（每 100ms 一格），回傳第幾毫秒叫停（唔停回 null）
function run(frames, startAt = 0) {
  const state = { lastVoice: startAt, spoke: false };
  let t = startAt;
  for (const loud of frames) {
    if (vadStep(state, loud, t)) return t - startAt;
    t += 100;
  }
  return null;
}
const LOUD = 0.2, QUIET = 0.001;
const frames = (spec) => spec.flatMap(([v, ms]) => Array(Math.round(ms / 100)).fill(v));

// 1) 講 8 秒（超過舊版 9 秒上限一半有多）＋靜 3 秒 → 語音完結後約 2.5 秒停
const r1 = run(frames([[LOUD, 8000], [QUIET, 3000]]));
check('長句 8 秒唔會提早切斷', r1 !== null && r1 > 8000, r1 + 'ms（舊版 9000ms 硬停）');

// 2) 句子中間 1.2 秒停頓（標點位）→ 唔可以停
const r2 = run(frames([[LOUD, 3000], [QUIET, 1200], [LOUD, 3000], [QUIET, 3000]]));
check('中間停頓 1.2 秒唔會誤停', r2 !== null && r2 > 7200, r2 + 'ms');

// 3) 講完之後 2.5 秒靜音 → 停
const r3 = run(frames([[LOUD, 2000], [QUIET, 4000]]));
check('靜音 2.5 秒後自動停', r3 !== null && r3 >= 4300 && r3 <= 4700, r3 + 'ms');

// 4) 從頭到尾無聲 → 唔會停（交 45 秒上限處理）
const r4 = run(frames([[QUIET, 10000]]));
check('全程無聲不會自動停', r4 === null);

// 5) 極短一句（0.3 秒）＋靜音 → 停
const r5 = run(frames([[LOUD, 300], [QUIET, 3000]]));
check('短句照樣會停', r5 !== null && r5 < 3500, r5 + 'ms');

console.log(bad ? `\n${bad} 項不符預期` : '\n全部通過');
process.exit(bad ? 1 : 0);
