/* 測試「跟讀評分」的比對前處理：目標句與辨識結果都要化成同一個形式。
   直接由 index.html 抽出 toHira／kanjiToKana／cleanKana／similarity，用真實對照表跑。
   用法：node tools/test-score.mjs */
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dict = JSON.parse(readFileSync(new URL('../data/kanji-readings.json', import.meta.url), 'utf8')).dict;

function grab(name, endMarker) {
  const start = html.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('找不函式 ' + name);
  const end = html.indexOf(endMarker, start);
  if (end < 0) throw new Error('找不尾 ' + name);
  return html.slice(start, end + endMarker.length);
}

const src = [
  grab('toHira', '\n  }'),
  grab('kanjiToKana', '\n  }'),
  grab('cleanKana', '\n  }'),
  grab('lcsTable', '\n  }'),
  grab('similarity', '\n  }'),
  grab('markTarget', '\n  }'),
  'return { toHira, kanjiToKana, cleanKana, similarity, markTarget };',
].join('\n');

const api = new Function('KANJI_READ', 'esc', src)(dict, s => String(s));
// 未加漢字對照時的舊行為，用來證明有改善
const raw = new Function('KANJI_READ', 'esc', src)({}, s => String(s));

let bad = 0;
const check = (name, ok, info) => {
  if (!ok) bad++;
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (info ? '  ' + info : ''));
};

// 片假名 → 平假名
check('片假名轉平假名', api.cleanKana('リーレー') === 'りれ', api.cleanKana('リーレー'));

// 漢字 → 讀音
check('漢字換讀音', api.kanjiToKana('始まって') === 'はじまって', api.kanjiToKana('始まって'));
check('詞組換讀音', api.kanjiToKana('会社員') === 'かいしゃいん', api.kanjiToKana('会社員'));

// 完全一樣 → 100
check('相同句子 100 分', api.similarity('あのう、はじめまして。りです。', 'あのう、はじめまして。りです。') === 100);

// 只有片假名差異 → 100
check('片假名／標點不扣分', api.similarity('あのう、はじめまして。りです。', 'アノウ、ハジメマシテ。リデス。') === 100);

// 用戶回報的個案
const target = 'あのう、はじめまして。りです。';
const heard = 'あのー始まってリーレー';
const score = api.similarity(target, heard);
const before = raw.similarity(target, heard);
check('回報個案：漢字換讀音後分數提高', score >= 50 && score - before >= 10,
  before + ' 分 → ' + score + ' 分 / 正規化後：' + api.cleanKana(heard));

// 全錯 → 0
check('完全無關的分數偏低', api.similarity('あのう、はじめまして。りです。', 'きょうはさむいですね') < 40,
  api.similarity('あのう、はじめまして。りです。', 'きょうはさむいですね') + ' 分');

// 紅字標示用同一套正規化
const marked = api.markTarget('はじめまして', 'ハジメマシテ');
check('標示不應有紅字', !marked.includes('miss'), marked);

console.log(bad ? `\n${bad} 項不符預期` : '\n全部通過');
process.exit(bad ? 1 : 0);
