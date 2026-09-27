/* Setup stays opt-in. Rendering never starts a diagnostic or a download. */
(() => {
  const views=['guide','diagnostic','components'];
  let snapshot=null, pending=false, timer=null, componentKey='', reportKey='';
  function tab(view){
    $('setup-dialog').scrollTop=0;
    for(const name of views){
      $('setup-'+name).hidden=name!==view;
      const button=$('setup-tab-'+name);button.setAttribute('aria-selected',String(name===view));button.tabIndex=name===view?0:-1;
    }
  }
  function failure(error){$('setup-error').textContent=error.message;$('setup-error').hidden=false}
  function clearError(){$('setup-error').hidden=true;$('setup-error').textContent=''}
  function active(){return ['downloading','verifying','extracting','configuring','cancelling'].includes(snapshot?.operation.phase)}
  function computing(){return ['running','cancelling'].includes(snapshot?.compute?.state)}
  function renderCompute(){
    const value=snapshot.compute||{state:'idle'},select=$('setup-compute-device');
    const devices=(snapshot.report?.backend.devices||[]).filter(d=>d.type.includes('GPU'));
    $('setup-compute').hidden=!snapshot.compute_eligible&&!computing();
    const key=JSON.stringify(devices);
    if(select.dataset.devices!==key){
      const selected=select.value;select.replaceChildren();
      for(const device of devices){const option=el('option','',`${device.name} / ${device.backend} #${device.id}`);option.value=device.id;select.append(option)}
      if(devices.some(d=>String(d.id)===selected))select.value=selected;
      select.dataset.devices=key;
    }
    select.disabled=pending||snapshot.locked||computing();
    $('setup-compute-start').disabled=pending||snapshot.locked||!snapshot.compute_eligible||!devices.length;
    $('setup-compute-start').hidden=computing();
    $('setup-compute-cancel').hidden=!computing();
    $('setup-compute-cancel').disabled=pending||value.state==='cancelling';
    $('setup-compute-result').textContent=value.state==='passed'?t`計算確認済み：${value.device.name} / ${value.device.backend}（${value.seconds}秒・準備込み）`:i18n.message(value.message)||t('未実施');
    $('setup-compute-result').classList.toggle('field-error',['error','timeout'].includes(value.state));
    $('setup-compute-details').hidden=!value.details;$('setup-compute-log').textContent=value.details||'';
  }
  function row(label,value){const n=el('div','diagnosis-row');n.append(el('span','muted',label),el('strong','',value));return n}
  function renderReport(report){
    const key=JSON.stringify([report,snapshot?.compute]);if(key===reportKey)return;reportKey=key;
    const root=$('setup-diagnostic-result');root.replaceChildren();
    if(!report){root.append(el('p','muted',t('未診断')));$('setup-diagnostic-details').hidden=true;return}
    const hardware=report.hardware,backend=report.backend;
    const names={recognized:t('HashcatでGPUを認識'),cpu_only:t('CPUのみを認識'),missing:t('Hashcat未設定'),unavailable:t('計算デバイスを確認できません'),error:t('Hashcatの照会に失敗')};
    root.append(row(t('OSのGPU情報'),hardware.status==='detected'?t('ディスプレイアダプターを検出'):t('確認できませんでした')));
    const list=el('ul','diagnosis-devices');for(const device of hardware.devices)list.append(el('li','',device.name));root.append(list);
    if(hardware.status!=='detected')root.append(el('p','setup-note',t('未検出でも、GPU非搭載とは限りません。権限や仮想環境によって確認できない場合があります。')));
    root.append(row(t('探索エンジン'),names[backend.status]||t('未確認')));
    const devices=el('ul','diagnosis-devices');
    for(const device of backend.devices)devices.append(el('li','',`${device.name} / ${device.backend} ${device.type}`));root.append(devices);
    root.append(row(t('計算動作・速度'),snapshot?.compute?.state==='passed'?t('計算確認済み（速度は未測定）'):t('未検証（デバイス照会のみ）')));
    if(backend.nvrtc_missing)root.append(el('p','setup-note',t('CUDA初期化に必要なNVRTCを確認できません。「追加部品」で導入可否を確認できます。')));
    $('setup-diagnostic-details').hidden=!backend.text;$('setup-diagnostic-log').textContent=backend.text||'';
  }
  function renderComponents(){
    const key=JSON.stringify([snapshot.components,pending,active(),snapshot.locked]);if(key===componentKey)return;componentKey=key;
    const list=$('setup-component-list');list.replaceChildren();
    for(const item of snapshot.components){
      const section=el('section','setup-component'),head=el('div','setup-component-heading');
      head.append(el('h4','',item.name),el('span','muted',item.version));section.append(head);
      section.append(el('p','setup-note',item.id==='hashcat'?(item.delivery==='bundled'?t('パスワード探索エンジン / 公式ソースからの同梱ビルド'):t('パスワード探索エンジン / 公式配布一式')): t('NVIDIA向け実行時コンパイラー / DLL 2個とライセンスのみ')));
      if(item.id==='nvrtc')section.append(el('p','setup-note',t('CUDA実行用の任意部品です。OpenCLで利用できる場合は、追加せずに使うこともできます。')));
      section.append(el('p','muted',`${t(item.delivery==='bundled'?'同梱済み・追加通信なし':'ダウンロード')} ${(item.size/1048576).toFixed(1)} MB`));
      const license=el('a','',i18n.message(item.license));license.href=item.license_url;license.target='_blank';license.rel='noopener noreferrer';section.append(license);
      if(item.reason)section.append(el('p','setup-note',i18n.message(item.reason)));
      const enabled=item.eligible&&!snapshot.locked&&!pending&&!active();
      if(item.eligible){
        const label=el('label','setup-consent'),check=el('input');check.type='checkbox';check.id='consent-'+item.id;check.disabled=!enabled;
        label.append(check,el('span','',item.id==='nvrtc'?t('NVIDIAの利用規約を確認し、同意してこの部品を導入する'):t('利用条件を確認し、この部品の導入を許可する')));
        section.append(label);
        const button=el('button','primary');button.type='button';button.id='install-'+item.id;button.disabled=true;button.append(icon('download'),el('span','',t('{0}を導入',item.name)));
        check.onchange=()=>button.disabled=!enabled||!check.checked;
        button.onclick=()=>install(item.id);section.append(button);
      }
      list.append(section);
    }
  }
  function render(){
    if(!snapshot)return;
    $('setup-destination').textContent=snapshot.destination;
    $('setup-diagnose').disabled=pending||snapshot.locked||active();
    const progress=snapshot.operation;$('setup-progress').hidden=!active();
    $('setup-download-progress').value=progress.total?Math.min(100,progress.received/progress.total*100):0;
    $('setup-progress-text').textContent=`${(progress.received/1048576).toFixed(1)} / ${(progress.total/1048576).toFixed(1)} MB`;
    $('setup-cancel').disabled=progress.phase==='cancelling'||pending;
    $('setup-operation-message').textContent=i18n.message(progress.message)||'';
    $('setup-operation-message').classList.toggle('field-error',progress.phase==='error');
    $('setup-check-again').hidden=progress.phase!=='complete';
    renderReport(snapshot.report);renderCompute();renderComponents();icons();
  }
  function schedule(){clearTimeout(timer);if(active()||computing())timer=setTimeout(refreshSetup,700)}
  async function refreshSetup(){try{snapshot=await api('/api/setup');render();schedule()}catch(error){failure(error)}}
  async function open(view='guide'){
    try{
      if($('settings-dialog').open){if(settingsDirty()){toast(t('先に設定を保存してください。'));return}$('settings-dialog').close()}
      snapshot=await api('/api/setup');clearError();tab(view);render();if(!$('setup-dialog').open)$('setup-dialog').showModal();schedule();
    }catch(error){toast(error.message)}
  }
  async function close(){
    try{await api('/api/setup/dismiss',{});$('setup-dialog').close()}catch(error){failure(error)}
  }
  async function install(component){
    if(!snapshot||!$('consent-'+component)?.checked)return;
    pending=true;clearError();render();
    try{snapshot=await api('/api/setup/install',{component,consent:true,catalog_revision:snapshot.catalog_revision})}catch(error){failure(error)}
    finally{pending=false;render();schedule()}
  }
  async function diagnose(){
    pending=true;clearError();render();$('setup-diagnostic-result').replaceChildren(el('p','muted',t('GPUと探索エンジンを照会中…')));reportKey='';
    try{snapshot=await api('/api/setup/diagnose',{})}catch(error){failure(error)}finally{pending=false;render()}
  }
  for(const name of views){
    const button=$('setup-tab-'+name);button.onclick=()=>tab(name);
    button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const index=views.indexOf(name),next=event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3;tab(views[next]);$('setup-tab-'+views[next]).focus()};
  }
  $('guide-open').onclick=()=>open();$('setup-open').onclick=()=>open('diagnostic');
  $('guide-next').onclick=()=>tab('diagnostic');$('diagnostic-next').onclick=()=>tab('components');
  $('setup-check-again').onclick=()=>tab('diagnostic');$('setup-diagnose').onclick=diagnose;
  $('setup-close').onclick=close;$('setup-finish').onclick=close;
  $('setup-dialog').addEventListener('cancel',event=>{event.preventDefault();close()});
  $('setup-cancel').onclick=async()=>{try{snapshot=await api('/api/setup/cancel',{});render();schedule()}catch(error){failure(error)}};
  async function compute(cancel=false){
    pending=true;clearError();render();
    try{snapshot=await api(cancel?'/api/setup/compute-cancel':'/api/setup/compute',cancel?{}:{consent:true,device:Number($('setup-compute-device').value)})}catch(error){failure(error)}
    finally{pending=false;render();schedule()}
  }
  $('setup-compute-start').onclick=()=>compute();$('setup-compute-cancel').onclick=()=>compute(true);
  document.addEventListener('loxmit-language',()=>{componentKey='';reportKey='';clearError();render()});
  i18n.ready.then(()=>api('/api/setup')).then(result=>{if(!result.guide_seen)open()}).catch(()=>{});
})();
