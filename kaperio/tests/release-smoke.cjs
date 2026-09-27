// Optional browser acceptance test; only synthetic documents are used.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const {chromium} = require(require.resolve('playwright', {paths: [process.env.KAPERIO_NODE_MODULES || process.cwd()]}));
const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const executable = process.env.KAPERIO_EXECUTABLE || python;
const entry = process.env.KAPERIO_EXECUTABLE ? [] : ['app.py'];
const data = path.join(root, '.test-data', 'release-browser-' + process.pid);
fs.mkdirSync(data, {recursive: true});
const source = path.join(data, 'Sample.pdf');
execFileSync(python, ['-c', "import sys; from pathlib import Path; sys.path.insert(0,'tests'); from test_core import make_pdf; make_pdf(Path(sys.argv[1]),'Test42')", source], {cwd: root, windowsHide: true});
const child = spawn(executable, [...entry, '--port', '0', '--data', data, '--no-browser'], {cwd: root, windowsHide: true, stdio: 'ignore'});
const exited = new Promise(resolve => child.once('exit', resolve));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function setupChecks(page, context, base, data) {
  await page.locator('#setup-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('.file-item').count(),0);
  await page.locator('#guide-next').click();
  assert.ok(await page.locator('#setup-diagnostic-result').filter({hasText:'未診断'}).isVisible());
  const original=await (await context.request.get(base+'/api/setup')).json();
  const fixture=JSON.parse(JSON.stringify(original));fixture.locked=false;
  fixture.components[0].eligible=true;fixture.components[0].reason='';fixture.components[1].eligible=false;
  fixture.report={hardware:{status:'detected',devices:[{name:'Synthetic NVIDIA GPU',vendor:'NVIDIA',driver:'fixture'}]},backend:{status:'missing',devices:[],compute_tested:false,nvrtc_missing:false,text:''}};
  let diagnoses=0,installs=0;
  await page.route('**/api/setup',route=>route.fulfill({json:fixture}));
  await page.route('**/api/setup/diagnose',route=>{diagnoses++;return route.fulfill({json:fixture})});
  await page.route('**/api/setup/install',route=>{
    const request=route.request().postDataJSON();assert.equal(request.component,'hashcat');assert.equal(request.consent,true);assert.equal(request.catalog_revision,fixture.catalog_revision);
    installs++;fixture.operation=installs===1?{phase:'error',message:'Synthetic download failure',received:0,total:19682772}:{phase:'downloading',message:'Synthetic download',received:5000000,total:20000000};
    if(installs>1){fixture.locked=true;fixture.components[0].eligible=false}
    return route.fulfill({json:fixture});
  });
  await page.route('**/api/setup/cancel',route=>{
    fixture.operation={phase:'cancelled',message:'Synthetic cancelled',received:5000000,total:20000000};
    fixture.locked=false;fixture.components[0].eligible=true;return route.fulfill({json:fixture});
  });
  assert.equal(diagnoses,0);assert.equal(installs,0);
  await page.locator('#setup-diagnose').click();
  await page.locator('#setup-diagnostic-result').filter({hasText:'Synthetic NVIDIA GPU'}).waitFor();
  assert.match(await page.locator('#setup-diagnostic-result').textContent(),/未検証/);
  assert.equal(diagnoses,1);
  await page.locator('#diagnostic-next').click();
  assert.equal(await page.locator('#install-hashcat').isEnabled(),false);
  assert.equal(await page.locator('#consent-nvrtc').count(),0);
  await page.locator('#consent-hashcat').check();
  await page.locator('#install-hashcat').click();
  await page.locator('#setup-operation-message').filter({hasText:'Synthetic download failure'}).waitFor();
  assert.equal(installs,1);
  assert.equal(await page.locator('#consent-hashcat').isChecked(),false);
  assert.equal(await page.locator('#install-hashcat').isEnabled(),false);
  await page.locator('#consent-hashcat').check();await page.locator('#install-hashcat').click();
  await page.locator('#setup-progress').waitFor();
  assert.equal(await page.locator('#setup-download-progress').evaluate(n=>n.value),25);
  await page.locator('#setup-cancel').click();
  await page.locator('#setup-operation-message').filter({hasText:'Synthetic cancelled'}).waitFor();
  assert.equal(await page.locator('#setup-progress').isVisible(),false);
  fixture.report.backend={status:'recognized',devices:[{name:'Synthetic NVIDIA GPU',backend:'OpenCL',type:'GPU'}],compute_tested:false,nvrtc_missing:true,text:'Synthetic diagnostic log'};
  fixture.components[0].eligible=false;fixture.components[0].reason='設定済み';fixture.components[1].eligible=true;fixture.components[1].reason='';
  await page.locator('#setup-tab-diagnostic').click();await page.locator('#setup-diagnose').click();
  await page.locator('#setup-diagnostic-result').filter({hasText:'NVRTC'}).waitFor();
  await page.locator('#setup-tab-components').click();
  assert.equal(await page.locator('#install-nvrtc').isEnabled(),false);
  assert.equal(await page.locator('#consent-nvrtc').isChecked(),false);
  fixture.components[0].delivery='bundled';fixture.components[0].eligible=true;fixture.components[0].reason='';
  fixture.components[1].eligible=false;
  await page.locator('#setup-tab-diagnostic').click();await page.locator('#setup-diagnose').click();
  await page.locator('#setup-tab-components').click();
  assert.match(await page.locator('#setup-component-list').textContent(),/同梱済み・追加通信なし/);
  assert.equal(await page.locator('#install-hashcat').isEnabled(),false);
  assert.equal(await page.locator('#consent-hashcat').isChecked(),false);
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});
    for(const view of ['guide','diagnostic','components']){
      await page.locator('#setup-tab-'+view).click();
      assert.ok(await page.locator('#setup-dialog').evaluate(n=>n.scrollWidth<=n.clientWidth),'setup overflow '+width+' '+view);
      await page.screenshot({path:path.join(data,'setup-'+view+'-'+width+'.png'),fullPage:true});
    }
  }
  await page.locator('#setup-finish').click();
  await page.locator('#setup-dialog').waitFor({state:'hidden'});
  await page.unroute('**/api/setup');await page.unroute('**/api/setup/diagnose');await page.unroute('**/api/setup/install');await page.unroute('**/api/setup/cancel');
  assert.equal((await (await context.request.get(base+'/api/setup')).json()).guide_seen,true);
  await page.reload();await page.locator('#empty').waitFor();
  assert.equal(await page.locator('#setup-dialog').isVisible(),false);
  await page.locator('#guide-open').click();await page.locator('#setup-dialog').waitFor();
  await page.locator('#setup-close').click();await page.locator('#setup-dialog').waitFor({state:'hidden'});
  await page.setViewportSize({width:1440,height:1000});
  console.log(JSON.stringify({setupPassed:true,checks:['first-run-guide','optional-component-consent','gpu-inventory-vs-backend','setup-download-error','setup-progress-cancel','native-bundle-consent','responsive-setup','guide-reopen','no-automatic-network']}));
}

async function settingsChecks(page, context, base, data) {
  assert.equal(await page.locator('#file-count').textContent(), '0');
  assert.equal(await page.locator('.file-item').count(), 0);
  assert.ok(await page.locator('#empty').isVisible());
  await page.screenshot({path:path.join(data,'first-run-empty.png'),fullPage:true});
  await page.locator('#settings-open').click();
  await page.locator('#settings-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#hashcat-path').isVisible(),false);
  assert.equal(await page.locator('#diagnostics').isEnabled(),false);
  assert.match(await page.locator('#recovery-availability').textContent(),/Hashcat未設定/);
  await page.screenshot({path:path.join(data,'settings-unconfigured.png'),fullPage:true});
  await page.locator('#security-open').click();
  await page.locator('#security-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#security-storage-state').textContent(),'未確認');
  let storageChecks=0;
  await page.route('**/api/security/check',route=>{
    storageChecks++;
    return route.fulfill({json:{storage:{state:['protected','unprotected','unknown','not_detected'][storageChecks-1]},method:'BitLocker',help_url:'https://learn.microsoft.com/windows/',checked_at:1790000000}});
  });
  assert.equal(storageChecks,0);
  for(const expected of ['保護を確認','保護が無効','確認できません','暗号化経路を検出できません']){
    await page.locator('#security-check').click();
    await page.locator('#security-storage-state').filter({hasText:expected}).waitFor();
  }
  assert.match(await page.locator('#security-storage-detail').textContent(),/別方式/);
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.locator('#security-dialog').evaluate(n=>n.scrollWidth<=n.clientWidth),'security overflow '+width);
    await page.screenshot({path:path.join(data,'security-'+width+'.png'),fullPage:true});
  }
  await page.locator('#security-close').click();await page.unroute('**/api/security/check');
  await page.setViewportSize({width:1440,height:1000});
  console.log(JSON.stringify({securityPassed:true,checks:['explicit-read-only-probe','four-storage-states','responsive-security','honest-sandbox-boundary']}));
  await page.locator('#detect-tools').click();
  await page.waitForFunction(()=>!document.getElementById('detect-tools').disabled);
  assert.ok(await page.locator('#settings-feedback').isVisible());
  assert.equal((await (await context.request.get(base+'/api/settings')).json()).hashcat,'');
  await page.locator('#engine-paths').evaluate(n=>n.open).then(async open=>{if(!open)await page.locator('#engine-paths summary').click()});
  await page.locator('#hashcat-path').fill('not-an-absolute-path');
  await page.locator('#settings-save').click();
  await page.locator('#hashcat-error').waitFor({state:'visible'});
  assert.equal(await page.locator('#hashcat-path').getAttribute('aria-invalid'),'true');
  assert.ok(await page.locator('#settings-dialog').isVisible());
  assert.equal((await (await context.request.get(base+'/api/settings')).json()).hashcat,'');
  // This placeholder executable is never run. The GPU reply is a browser fixture.
  const fake=path.join(data,process.platform==='win32'?'hashcat.exe':'hashcat');
  fs.writeFileSync(fake,'synthetic settings fixture, not executable');
  await page.locator('#hashcat-path').fill(fake);
  assert.match(await page.locator('#diagnostics-label').textContent(),/保存して/);
  let diagnosticCalls=0;
  await page.route('**/api/diagnostics',async route=>{
    const saved=await (await context.request.get(base+'/api/settings')).json();
    assert.equal(saved.hashcat,fake);diagnosticCalls++;
    return route.fulfill({json:{code:0,text:'Synthetic device query fixture'}});
  });
  await page.locator('#diagnostics').click();
  await page.locator('#gpu-status').filter({hasText:'照会完了'}).waitFor();
  assert.equal(diagnosticCalls,1);
  assert.equal(await page.locator('#recovery-availability').textContent(),'デバイス照会済み');
  await page.unroute('**/api/diagnostics');
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:844});
    const bounds=await page.locator('#settings-dialog').boundingBox();
    assert.ok(bounds.x>=0&&bounds.x+bounds.width<=width);
    assert.ok(await page.locator('#settings-dialog').evaluate(n=>n.scrollWidth<=n.clientWidth));
    await page.screenshot({path:path.join(data,'settings-'+width+'.png'),fullPage:true});
  }
  await page.locator('#hashcat-path').fill('');
  await page.locator('#zip2john-path').fill('');
  await page.locator('#settings-save').click();
  await page.locator('#settings-dialog').waitFor({state:'hidden'});
  await page.setViewportSize({width:1440,height:1000});
}

// Deterministic visual states are browser-only fixtures, never recovery evidence.
async function designChecks(page, data) {
  const now = Date.now() / 1000;
  const names = ['Sample.pdf', '決算_2025_Q2.xlsx', '営業提案_改訂版.pptx', '契約書_雛形.docx', '写真アーカイブ_2019.zip'];
  const states = ['recovering', 'paused', 'ready', 'locked', 'error'];
  const jobs = names.map((name, i) => ({
    id: 'design-' + i, name, size: (3.2 - i * .2) * 1048576, created: now - i * 86400,
    state: states[i], available: i === 2, has_password: false, can_resume: i === 1,
    has_pdf: false, can_convert: i !== 4, outputs: [], warnings: [], elapsed: 767,
    info: {extension: name.slice(name.lastIndexOf('.')), format: i === 0 ? 'pdf' : i === 4 ? 'zip' : 'office', pages: 0, encryption: 'パスワード保護', recoverable: true},
    plan_summary: i < 2 ? {strategy:'guided',candidates:'8000000',groups:[{name:'元の単語'},{name:'英字大小・数字'},{name:'文字の入れ替え'}],minutes:10,temperature:80,workload:1,kernel:'auto',devices:''} : null,
    metrics: i === 0 ? {tested:1280000,total:8000000,speed:148220,temperature:67,stage:2,stages:3} : {}, metrics_at: now,
    message: i === 0 ? '段階 2/3: 英字大小・数字' : '',
    events: ['ファイルを追加しました。','探索を開始しました。','段階 1/3: 元の単語','段階 2/3: 英字大小・数字'].map((text,k)=>({time:now-300+k*60,text}))
  }));
  let disconnected = false;
  await page.route('**/api/jobs', route => disconnected ? route.abort() : route.fulfill({json:{jobs}}));
  await page.route('**/api/jobs/design-0/pause', route => {jobs[0].state='paused';jobs[0].can_resume=true;return route.fulfill({json:{ok:true}})});
  await page.route('**/api/jobs/design-0/resume', route => {jobs[0].state='recovering';jobs[0].metrics_at=Date.now()/1000;return route.fulfill({json:{ok:true}})});
  await page.setViewportSize({width:1586,height:992});
  await page.evaluate(() => refresh());
  await page.locator('#run-summary').waitFor();
  assert.equal(await page.locator('#job-progress').getAttribute('aria-valuenow'),'16.0');
  const progress = await page.locator('#progress-fill').boundingBox();
  const track = await page.locator('#job-progress').boundingBox();
  assert.ok(Math.abs(progress.width/track.width-.16)<.01);
  assert.match(await page.locator('#job-progress').getAttribute('class'),/running/);
  const beforeMotion = await page.locator('.progress-sheen').evaluate(n=>getComputedStyle(n).transform);
  await delay(250);
  assert.notEqual(await page.locator('.progress-sheen').evaluate(n=>getComputedStyle(n).transform),beforeMotion);
  const colours = await page.locator('.file-item .file-symbol').evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n).color));
  assert.deepEqual(colours,['rgb(217, 35, 46)','rgb(16, 124, 65)','rgb(196, 62, 28)','rgb(24, 90, 189)','rgb(100, 108, 120)']);
  for (const i of [1,2]) assert.equal(await page.locator('.file-item .status').nth(i).evaluate(n=>getComputedStyle(n).color),'rgb(91, 97, 106)');
  assert.ok(await page.locator('.brand img').evaluate(n=>n.complete&&n.naturalWidth===64));
  assert.equal(await page.locator('#preview').isVisible(),false);
  await page.screenshot({path:path.join(data,'dashboard-active.png'),fullPage:true});
  await page.locator('.file-item').first().focus();
  await delay(2100);
  assert.equal(await page.locator('.file-item').first().evaluate(n=>n===document.activeElement),true);
  await page.locator('#pause-job').click();
  await page.locator('#resume-job').waitFor();
  assert.doesNotMatch(await page.locator('#job-progress').getAttribute('class'),/running/);
  await page.screenshot({path:path.join(data,'dashboard-paused.png'),fullPage:true});
  await page.locator('#resume-job').click();
  await page.locator('#pause-job').waitFor();
  jobs[0].metrics_at = now - 100;
  await page.evaluate(() => refresh());
  assert.doesNotMatch(await page.locator('#job-progress').getAttribute('class'),/running/);
  jobs[0].metrics_at=Date.now()/1000;
  await page.evaluate(() => refresh());
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.progress-sheen').evaluate(n=>getComputedStyle(n).display),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  disconnected=true;await page.evaluate(() => refresh());
  assert.doesNotMatch(await page.locator('#job-progress').getAttribute('class'),/running/);
  disconnected=false;await page.evaluate(() => refresh());
  for(const width of [320,390,768,1024,1440,1920]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow at '+width);
    await page.screenshot({path:path.join(data,'dashboard-'+width+'.png'),fullPage:true});
  }
  jobs[0].name='とても長いファイル名_'+('長い名前'.repeat(15))+'_2026.pdf';
  for(const width of [320,1440]){
    await page.setViewportSize({width,height:900});await page.evaluate(() => refresh());
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'long name overflow');
    await page.screenshot({path:path.join(data,'long-name-'+width+'.png'),fullPage:true});
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('.file-item').nth(2).click();
  await page.locator('#tab-unlock').focus();await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#tab-export').getAttribute('aria-selected'),'true');
  assert.equal(await page.locator('#tab-export').evaluate(n=>n===document.activeElement),true);
  await page.unroute('**/api/jobs');
}

async function passwordResultChecks(page, context, base, data) {
  await page.waitForFunction(()=>document.getElementById('password-result').value==='Test42');
  assert.equal(await page.locator('#password-result').getAttribute('type'),'text');
  assert.ok(await page.locator('#password-result').evaluate(n=>n.readOnly));
  await page.evaluate(()=>{
    // Test clipboard only: never replace or read the user's actual clipboard.
    window.copiedFixture='';window.denyFixtureCopy=false;
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{
      if(window.denyFixtureCopy)throw new DOMException('Test permission denial','NotAllowedError');
      window.copiedFixture=value;
    }}});
  });
  await page.locator('#copy-password').click();
  await page.locator('#password-feedback').filter({hasText:'コピーしました'}).waitFor();
  assert.equal(await page.evaluate(()=>window.copiedFixture),'Test42');
  await page.locator('#reveal-password').click();
  assert.equal(await page.locator('#password-result').getAttribute('type'),'password');
  await page.evaluate(()=>refresh());
  assert.equal(await page.locator('#password-result').getAttribute('type'),'password');
  await page.locator('#copy-password').click();
  assert.equal(await page.evaluate(()=>window.copiedFixture),'Test42');
  await page.evaluate(()=>{window.denyFixtureCopy=true});
  await page.locator('#copy-password').click();
  await page.locator('#password-feedback').filter({hasText:'コピーできません'}).waitFor();
  assert.equal(await page.locator('#password-result').getAttribute('type'),'password');
  await page.locator('#reveal-password').click();
  await page.locator('#copy-password').click();
  await page.waitForFunction(()=>!document.getElementById('copy-password').disabled);
  assert.equal(await page.locator('#password-result').evaluate(n=>n.selectionEnd-n.selectionStart),6);
  await page.evaluate(()=>{window.denyFixtureCopy=false});
  await page.locator('#copy-password').click();
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'password result overflow '+width);
    const field=await page.locator('#password-result').boundingBox(),button=await page.locator('#copy-password').boundingBox();
    assert.ok(button.y>=field.y+field.height||button.x>=field.x+field.width,'copy overlaps password');
    await page.screenshot({path:path.join(data,'password-result-'+width+'.png'),fullPage:true});
  }
  const current=(await (await context.request.get(base+'/api/jobs')).json()).jobs[0];
  const other={...current,id:'password-other',name:'Other.docx',has_pdf:false,can_convert:false,contents:[],info:{extension:'.docx',format:'office'}};
  const jobs=[current,other];let mode='error',pendingOther=null,requests=0;
  const longPassword='  <tag>日本語'+ 'x'.repeat(90)+'  ';
  await page.route('**/api/jobs',route=>route.fulfill({json:{jobs}}));
  await page.route('**/api/jobs/*/password',async route=>{
    requests++;
    if(route.request().url().includes('/password-other/')){pendingOther=route;return}
    if(mode==='error')return route.fulfill({status:503,json:{error:'Synthetic failure'}});
    if(mode==='long')return route.fulfill({json:{password:longPassword}});
    return route.continue();
  });
  await page.evaluate(()=>refresh());
  await page.evaluate(()=>refresh());
  assert.equal(requests,0,'polling must not fetch passwords repeatedly');
  await page.locator('.file-item[data-id="password-other"]').click();
  for(let i=0;i<100&&!pendingOther;i++)await delay(10);
  assert.ok(pendingOther);
  assert.equal(await page.locator('#password-result').inputValue(),'');
  assert.equal(await page.locator('#copy-password').isEnabled(),false);
  await page.locator('.file-item').first().click();
  await page.locator('#retry-password').waitFor();
  await pendingOther.fulfill({json:{password:'NeverShowOtherSecret'}});
  await delay(50);
  assert.equal(await page.locator('#password-result').inputValue(),'');
  mode='long';await page.locator('#retry-password').click();
  await page.waitForFunction(value=>document.getElementById('password-result').value===value,longPassword);
  assert.equal(await page.locator('#password-result').getAttribute('type'),'text');
  await page.locator('#copy-password').click();
  assert.equal(await page.evaluate(()=>window.copiedFixture),longPassword);
  await page.setViewportSize({width:320,height:900});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(data,'password-long-320.png'),fullPage:true});
  current.has_password=false;await page.evaluate(()=>refresh());
  assert.equal(await page.locator('#password-result-panel').isVisible(),false);
  assert.equal(await page.locator('#password-result').inputValue(),'');
  mode='real';await page.unroute('**/api/jobs');await page.evaluate(()=>refresh());
  await page.waitForFunction(()=>document.getElementById('password-result').value==='Test42');
  await page.unroute('**/api/jobs/*/password');
  await page.setViewportSize({width:1440,height:1000});
}

(async () => {
  let browser, context, base;
  try {
    for (let i = 0; i < 100 && !fs.existsSync(path.join(data, 'launch.json')); i++) {
      if (child.exitCode !== null) throw Error('Server exited before launch');
      await delay(100);
    }
    const launch = JSON.parse(fs.readFileSync(path.join(data, 'launch.json'), 'utf8'));
    base = new URL(launch.url).origin;
    browser = await chromium.launch({channel: process.env.KAPERIO_BROWSER || 'msedge', headless: true});
    context = await browser.newContext({viewport: {width: 1440, height: 1000}, serviceWorkers: 'block'});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(launch.url);
    await setupChecks(page,context,base,data);
    await page.locator('#empty').waitFor();
    await settingsChecks(page,context,base,data);
    await page.locator('#settings-open').click();
    await page.locator('#settings-dialog').waitFor({state: 'visible'});
    assert.equal(await page.locator('#hashcat-path').inputValue(), '');
    assert.equal(await page.locator('#zip2john-path').inputValue(), '');
    const licenses = await context.request.get(base + '/api/licenses');
    assert.equal(licenses.status(), 200);
    assert.match(await licenses.text(), /Lucide Icons/);
    await page.locator('#settings-form button[type=submit]').click();
    await page.locator('#settings-dialog').waitFor({state:'hidden'});
    await page.locator('#files').setInputFiles(source);
    await page.locator('#document-name').filter({hasText: 'Sample.pdf'}).waitFor();
    assert.equal(await page.locator('#recover-mode').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#known-form').isVisible(),false);
    assert.equal(await page.locator('#approach').inputValue(),'automatic');
    assert.equal(await page.locator('#strategy').isVisible(),false);
    await page.waitForFunction(()=>document.getElementById('candidate-count').textContent.includes('試行'));
    assert.match(await page.locator('#plan-notes').textContent(),/網羅/);
    await page.locator('#words').fill('RememberedLongPhrase');
    await page.locator('#remember-length').selectOption('range');
    await page.locator('#remember-min').fill('19');
    await page.locator('#remember-max').fill('22');
    await page.waitForFunction(()=>document.getElementById('candidate-count').textContent.includes('試行'));
    assert.match(await page.locator('#hint-summary').textContent(),/語句/);
    for(const width of [320,390,768,1440]){
      await page.setViewportSize({width,height:1000});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'interview overflow '+width);
      await page.screenshot({path:path.join(data,'interview-'+width+'.png'),fullPage:true});
    }
    await page.locator('#words').fill('');
    await page.waitForFunction(()=>document.getElementById('candidate-count').textContent.includes('条件を確認'));
    assert.equal(await page.locator('#recovery-form button[type=submit]').isEnabled(),false);
    await page.locator('#auto-questions details summary').click();
    await page.locator('#remember-prefix').fill('RememberedLongPart');
    await page.locator('#remember-min').fill('19');
    await page.locator('#remember-max').fill('19');
    await page.locator('#remember-characters').selectOption('digits');
    await page.waitForFunction(()=>document.getElementById('candidate-count').textContent==='10 試行');
    await page.locator('#remember-length').selectOption('unknown');
    await page.locator('#remember-characters').selectOption('unknown');
    await page.locator('#remember-prefix').fill('');
    await page.setViewportSize({width:1440,height:1000});
    await page.locator('#recover-mode').click();
    await page.locator('#approach').selectOption('manual');
    await page.locator('#strategy').selectOption('dictionary');
    await page.locator('#words').fill('test');
    for (const strategy of ['dictionary_rules', 'hybrid_suffix', 'hybrid_prefix', 'dictionary', 'mask']) {
      await page.locator('#strategy').selectOption(strategy);
      assert.equal(await page.locator('#dictionary-fields').isVisible(), strategy !== 'mask');
      assert.equal(await page.locator('#mask-fields').isVisible(), strategy === 'mask' || strategy.startsWith('hybrid_'));
      await page.waitForFunction(()=>document.getElementById('candidate-count').textContent.includes('試行'));
      assert.doesNotMatch(await page.locator('#candidate-count').textContent(), /条件を確認/);
    }
    await page.locator('#strategy').selectOption('guided');
    await page.locator('#hint-numbers').fill('2024');
    await page.locator('#hint-combine').check();
    await page.locator('#hint-typos').check();
    await page.waitForFunction(() => document.getElementById('hint-summary').textContent.includes('数字'));
    assert.ok(await page.locator('#guided-fields').isVisible());
    await page.locator('#recovery-form > details > summary').click();
    await page.locator('#workload').selectOption('auto');
    await page.locator('#recovery-form > details > summary').click();
    await page.waitForFunction(() => document.getElementById('candidate-count').textContent.includes('試行'));
    await page.screenshot({path: path.join(data, 'recovery-desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path: path.join(data, 'recovery-mobile.png'), fullPage: true});
    await page.setViewportSize({width: 1440, height: 1000});
    await page.locator('#known-mode').click();
    await page.locator('#password').fill('wrong');
    await page.locator('#known-form button[type=submit]').click();
    await page.locator('#toast').filter({hasText: '一致しません'}).waitFor();
    await page.locator('#password').fill('Test42');
    await page.locator('#known-form button[type=submit]').click();
    await page.locator('#ready-state').waitFor();
    await passwordResultChecks(page,context,base,data);
    await page.waitForFunction(() => document.getElementById('page-image').naturalWidth > 0);
    await page.route('**/api/jobs/*/preview?*', route=>route.fulfill({status:400,json:{error:'Synthetic preview busy'}}));
    await page.locator('#refresh-preview').click();
    await page.locator('#preview-message').filter({hasText:'Synthetic preview busy'}).waitFor();
    assert.equal(await page.locator('#page-image').isVisible(),false);
    await page.unroute('**/api/jobs/*/preview?*');
    await page.locator('#refresh-preview').click();
    await page.waitForFunction(() => document.getElementById('page-image').naturalWidth > 0 && !document.getElementById('page-image').hidden);
    console.log(JSON.stringify({previewResiliencePassed:true,checks:['preview-error-retry']}));
    await page.locator('#tab-export').click();
    await page.locator('#export-kind').selectOption('image_pdf');
    await page.locator('#export-form button[type=submit]').click();
    await page.locator('#outputs a').nth(1).waitFor();
    await page.screenshot({path: path.join(data, 'desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('#settings-open').click();
    await page.locator('#settings-dialog').waitFor({state: 'visible'});
    const bounds = await page.locator('#settings-dialog').boundingBox();
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 390);
    await page.screenshot({path: path.join(data, 'mobile-settings.png'), fullPage: true});
    await page.locator('#settings-close').click();
    await page.locator('#remove-file').click();
    await page.locator('#remove-confirm').click();
    await page.locator('#empty').waitFor();
    assert.ok(fs.existsSync(source));
    const second = execFileSync(executable, [...entry, '--data', data, '--no-browser'], {cwd: root, windowsHide: true, encoding: 'utf8'});
    if (!process.env.KAPERIO_EXECUTABLE) assert.match(second, /already running/);
    await designChecks(page, data);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({passed: true, checks: ['empty-first-run', 'settings-availability', 'read-only-detect', 'field-validation', 'save-before-gpu-query', 'responsive-settings', 'fresh-no-engine', 'licenses', 'six-strategy-controls', 'guided-estimate', 'auto-workload-control', 'unlock', 'preview', 'export', 'mobile', 'delete', 'single-instance', 'six-responsive-widths', 'office-colours', 'neutral-states', 'pause-resume-motion', 'stale-offline-motion', 'reduced-motion', 'focus-stability', 'keyboard-tabs', 'recovery-first', 'unknown-answers', 'long-hint', 'bounded-empty-plan', 'long-fixed-part', 'responsive-interview', 'password-visible-result', 'password-copy-feedback', 'password-copy-denied', 'password-stale-response', 'password-retry', 'password-long-text', 'password-no-secret'], screenshots: data}));
  } finally {
    if (context && base) await context.request.post(base + '/api/shutdown', {headers: {'X-Kaperio': '1'}, data: {}}).catch(() => {});
    if (browser) await browser.close();
    await Promise.race([exited, delay(3000)]);
    if (child.exitCode === null) child.kill();
    await exited;
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
