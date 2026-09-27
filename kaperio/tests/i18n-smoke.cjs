const assert = require('node:assert/strict');
const path = require('node:path');

module.exports = async function bilingualChecks(page, context, base, data) {
  const switchTo = async language => {
    await page.locator('#language').selectOption(language);
    await page.waitForFunction(value => document.documentElement.lang === value, language);
    await page.waitForFunction(() => !document.getElementById('language').disabled);
  };
  const onlyEnglish = async selector => {
    await page.locator(selector).waitFor({state:'visible'});
    const text = await page.locator(selector).innerText();
    assert.doesNotMatch(text.replaceAll('日本語', ''), /[\u3040-\u30ff\u3400-\u9fff]/, selector + ' contains untranslated text: ' + text);
  };
  const hints = '完了\n秘密の語句 <img src=x onerror=alert(1)>';
  await page.locator('#words').fill(hints);
  await switchTo('en');
  assert.equal(await page.locator('#words').inputValue(), hints);
  assert.equal(await page.locator('#recover-mode').innerText(), 'Find password');
  await page.waitForFunction(() => document.getElementById('candidate-count').textContent.includes('attempts'));
  await onlyEnglish('#hint-summary');
  await onlyEnglish('#plan-notes');
  const config = await (await context.request.get(base + '/api/language')).json();
  assert.deepEqual(config, {language:'en'});
  assert.equal((await context.request.post(base + '/api/language', {headers:{'X-Loxmit':'1'},data:{language:'fr'}})).status(), 400);
  assert.equal((await context.request.post(base + '/api/language', {data:{language:'ja'}})).status(), 403);
  assert.equal(await page.evaluate(() => t('{0}を導入', '$&秘密')), 'Install $&秘密');
  assert.equal(await page.evaluate(() => i18n.message('段階 2/3: 数字 / 全体4文字')), 'Stage 2/3: Digits / 4 characters total');
  assert.equal(await page.evaluate(() => i18n.message('開封エラー: パスワードが一致しません。')), 'Unlock error: The password does not match.');
  assert.equal(await page.evaluate(() => i18n.message('時間上限に達したため停止しました。 保存地点から再開できます。')), 'Stopped at the time limit. You can resume from the checkpoint.');
  await page.locator('#words').fill('SamplePhrase');
  await page.locator('#approach').selectOption('manual');
  for (const method of ['guided','mask','dictionary','dictionary_rules','hybrid_suffix','hybrid_prefix']) {
    await page.locator('#strategy').selectOption(method);
    await page.waitForFunction(() => document.getElementById('candidate-count').textContent.includes('attempts'));
    await onlyEnglish('#unlock-panel');
  }
  await page.locator('#approach').selectOption('automatic');
  await page.waitForFunction(() => document.getElementById('candidate-count').textContent.includes('attempts'));
  await page.evaluate(() => document.getElementById('toast').hidden=true);
  for (const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:1000});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'English overflow ' + width);
    await page.screenshot({path:path.join(data,'english-'+width+'.png'),fullPage:true});
  }
  await page.locator('#known-mode').click();
  await page.locator('#password').fill('wrong');
  await page.locator('#known-form button[type=submit]').click();
  await page.locator('#toast').filter({hasText:'The password does not match.'}).waitFor();
  await page.locator('#recover-mode').click();
  await page.locator('#settings-open').click();
  await onlyEnglish('#settings-dialog');
  await page.locator('#security-open').click();
  await onlyEnglish('#security-dialog');
  await page.locator('#security-close').click();
  await page.locator('#settings-close').click();
  await page.locator('#guide-open').click();
  for (const view of ['guide','diagnostic','components']) {
    await page.locator('#setup-tab-'+view).click();
    await onlyEnglish('#setup-dialog');
    for (const width of [320,768,1440]) {
      await page.setViewportSize({width,height:1000});
      const bounds = await page.locator('#setup-dialog').boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width, 'English dialog overflow');
      assert.ok(await page.locator('#setup-dialog').evaluate(node => node.scrollWidth <= node.clientWidth), 'English dialog content overflow: '+view+' '+width);
    }
  }
  await page.locator('#setup-finish').click();
  await page.reload();
  await page.waitForFunction(() => document.documentElement.lang === 'en');
  assert.equal(await page.locator('#language').inputValue(), 'en');
  await switchTo('ja');
  assert.equal(await page.locator('#recover-mode').innerText(), 'パスワードを探す');
  await page.locator('#language').selectOption('auto');
  await page.waitForFunction(() => !document.getElementById('language').disabled);
  assert.equal(await page.locator('html').getAttribute('lang'), 'ja');
  const englishContext = await context.browser().newContext({locale:'fr-FR',storageState:await context.storageState(),serviceWorkers:'block'});
  try {
    const englishPage = await englishContext.newPage();
    await englishPage.goto(base);
    await englishPage.waitForFunction(() => document.documentElement.lang === 'en' && document.getElementById('recover-mode').textContent === 'Find password');
    assert.equal(await englishPage.locator('#language').inputValue(), 'auto');
  } finally { await englishContext.close(); }
  await page.locator('#words').fill('');
  console.log(JSON.stringify({bilingualPassed:true,checks:['live-switch','preserved-input','saved-preference','reload','browser-default','invalid-language','csrf','placeholder-safety','nested-events','checkpoint-message','english-error','six-methods','english-layout','settings-security-guide']}));
};
