const { chromium } = require('playwright');
const URL = process.argv[2];

(async () => {
  const browser = await chromium.launch({ args: ['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--single-process'] });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(400);

  let bad = 0;
  const check = (name, pass, info) => { if (!pass) bad++; console.log((pass ? 'PASS' : 'FAIL') + '  ' + name + (info ? '  ' + info : '')); };

  const labels = await page.evaluate(() => [...document.querySelectorAll('#modeSeg button')].map(b => b.textContent.trim()));
  check('四個模式標籤', JSON.stringify(labels) === JSON.stringify(['羅馬拼音', '聽音選字', '手寫', '鍵盤輸入']), JSON.stringify(labels));

  await page.click('#modeSeg button[data-mode="speak"]');
  await page.waitForTimeout(300);

  const state = () => page.evaluate(() => ({
    kana: document.getElementById('speakKana').textContent.trim(),
    fbClass: document.getElementById('fbSpeak').className,
    fbText: document.getElementById('fbSpeak').textContent.replace(/\s+/g, ' ').trim(),
    note: document.getElementById('speakNote').textContent.trim(),
    val: document.getElementById('speakInput').value,
    correct: document.getElementById('statCorrect').textContent,
    wrong: document.getElementById('statWrong').textContent,
    checkLabel: document.getElementById('speakCheck').textContent.trim(),
  }));

  let s = await state();
  check('入題時輸入框清空、按鈕是「檢查」', s.val === '' && s.checkLabel === '檢查', JSON.stringify(s));
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  check('入題不自動聚焦（鍵盤不會自己彈出）', focused !== 'speakInput', 'activeElement=' + focused);

  // 打表外的字 → 不判錯
  const before = s;
  await page.fill('#speakInput', '目');
  await page.click('#speakCheck');
  await page.waitForTimeout(200);
  s = await state();
  check('輸入「目」不判錯', s.correct === before.correct && s.wrong === before.wrong && !s.fbClass.includes('show'), JSON.stringify(s.note));

  // 打錯的和音 → 判錯，並顯示你輸入了什麼
  const target = s.kana;
  const wrongKana = target === 'あ' ? 'い' : 'あ';
  await page.fill('#speakInput', wrongKana);
  await page.click('#speakCheck');
  await page.waitForTimeout(200);
  s = await state();
  check('打錯音判錯並顯示輸入內容', s.fbClass.includes('no') && s.fbText.includes(wrongKana), JSON.stringify(s.fbText));
  check('判錯後按鈕變「下一題」', /下一題/.test(s.checkLabel), s.checkLabel);

  await page.click('#speakCheck');   // 下一題
  await page.waitForTimeout(300);
  s = await state();
  check('下一題清空輸入框', s.val === '' && s.fbText === '' && s.checkLabel === '檢查', JSON.stringify(s));
  const focused2 = await page.evaluate(() => document.activeElement && document.activeElement.id);
  check('下一題亦不自動聚焦', focused2 !== 'speakInput', 'activeElement=' + focused2);

  // 打對 → 判對
  const k = s.kana;
  await page.fill('#speakInput', k);
  await page.click('#speakCheck');
  await page.waitForTimeout(200);
  s = await state();
  check('打對判對', s.fbClass.includes('ok') && s.fbText.includes('答對了'), JSON.stringify(s.fbText));

  await page.click('#speakCheck');   // 下一題
  await page.waitForTimeout(300);
  s = await state();
  // 用羅馬拼音回答（用假名表反查）
  const rom = await page.evaluate(() => {
    const kana = document.getElementById('speakKana').textContent.trim();
    return kana;
  });
  await page.screenshot({ path: '/tmp/kana-kbd.png' });

  check('頁面無 JS 錯誤', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log(bad ? `\n${bad} 項不符預期` : '\n全部通過');
  process.exit(bad ? 1 : 0);
})();
