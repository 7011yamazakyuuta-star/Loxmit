/* Local-only UI. User filenames, hints, and server messages stay text nodes. */
const $ = id => document.getElementById(id);
const MAX_UPLOAD_MB = 200;
const state = {jobs: [], selected: null, page: 0, tab: 'unlock', mode: 'recover', preview: '', polling: false, connected: true, editing: false, planValid: false};
const busy = new Set(['queued', 'preparing', 'recovering', 'pausing', 'converting', 'unlocking']);
const labels = {locked:'未解除',ready:'完了',queued:'待機',preparing:'準備中',recovering:'探索中',pausing:'停止中',paused:'一時停止',converting:'書き出し中',exhausted:'探索完了',error:'要確認',cancelled:'中止',unlocking:'照合中'};
const statusIcons = {locked:'lock-keyhole',ready:'check',queued:'clock-3',preparing:'loader-circle',recovering:'loader-circle',pausing:'pause',paused:'pause',converting:'loader-circle',exhausted:'check',error:'triangle-alert',cancelled:'square',unlocking:'loader-circle'};
const kinds = {pdf:'PDF',unlocked:'解除済みファイル',image_pdf:'画像PDF',images:'ページ画像 ZIP',word:'Word・ページ画像',text:'抽出テキスト'};
const strategies = {automatic:'おまかせ（手掛かりを優先）',guided:'手掛かり',mask:'文字数・文字種',dictionary:'候補リスト',dictionary_rules:'候補＋変形ルール',hybrid_suffix:'候補＋末尾探索',hybrid_prefix:'先頭探索＋候補'};
const charsetNames = {lower:'英小文字',upper:'英大文字',digits:'数字',symbols:'記号'};
const renderKeys = new Map();
const drafts = new Map();
let passwordResult={id:null,phase:'empty',value:'',hidden:false,message:'',error:false,copying:false},passwordRequest=0;
function icons(){lucide.createIcons({attrs:{'stroke-width':1.7}})}
function el(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n}
function icon(name){const n=el('i');n.dataset.lucide=name;return n}
function changed(key, value){const serialized=JSON.stringify(value);if(renderKeys.get(key)===serialized)return false;renderKeys.set(key,serialized);return true}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>{$('toast').hidden=true},6000)}
function bytes(n){return n>=1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB'}
function number(n){try{return BigInt(n).toLocaleString()}catch{return '—'}}
function elapsed(seconds){const n=Math.max(0,Math.floor(Number(seconds)||0));return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(v=>String(v).padStart(2,'0')).join(':')}
function date(seconds){return seconds?new Date(seconds*1000).toLocaleDateString('ja-JP'):''}
function time(seconds){return seconds?new Date(seconds*1000).toLocaleTimeString('ja-JP',{hour12:false}):''}
async function api(path,data){
  const options=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Loxmit':'1'},body:JSON.stringify(data)};
  const r=await fetch(path,options);const result=await r.json();
  if(!r.ok){const error=Error(result.error||'処理に失敗しました');error.field=result.field;throw error}return result;
}
function job(){return state.jobs.find(j=>j.id===state.selected)}
function fileType(j){
  const ext=(j.info.extension||j.name.slice(j.name.lastIndexOf('.'))).toLowerCase();
  if(ext==='.pdf')return ['pdf','file-text','PDF'];
  if(/^\.xls/.test(ext))return ['excel','file-spreadsheet',ext.slice(1).toUpperCase()];
  if(/^\.ppt/.test(ext))return ['powerpoint','presentation',ext.slice(1).toUpperCase()];
  if(/^\.doc/.test(ext))return ['word','file-text',ext.slice(1).toUpperCase()];
  return ['archive','file-archive',ext.slice(1).toUpperCase()||'FILE'];
}
function statusClass(j){return ['preparing','recovering','converting','unlocking'].includes(j.state)?' active':j.state==='error'?' warning':''}
function statusNode(j){const n=el('span','status'+statusClass(j));n.append(icon(statusIcons[j.state]||'circle'),el('span','',labels[j.state]||j.state));return n}
function setTab(tab){if(tab==='export'&&!job()?.available)return;state.tab=tab;renderDetail()}
function selectJob(id){
  if(state.selected!==id){
    const fields=[...$('recovery-form').querySelectorAll('input:not([type=file]),select,textarea')];
    if(state.selected)drafts.set(state.selected,fields.map(n=>({value:n.value,checked:n.checked})));
    state.selected=id;state.page=0;state.preview='';state.tab='unlock';state.editing=false;
    state.mode='recover';$('recovery-form').reset();state.hybrid=false;
    for(const [index,saved] of (drafts.get(id)||[]).entries()){const n=fields[index];n.value=saved.value;if(n.type==='checkbox')n.checked=saved.checked}
    state.hybrid=selectedStrategy().startsWith('hybrid_');
    strategyChanged();
    $('password').value='';$('password').type='password';resetPasswordResult();
    $('job-progress').classList.add('changed');
    requestAnimationFrame(()=>requestAnimationFrame(()=>$('job-progress').classList.remove('changed')));
  }
  render();
}
function renderList(){
  const query=$('search').value.toLowerCase(), filter=$('filter').value;
  const jobs=state.jobs.filter(j=>j.name.toLowerCase().includes(query)&&(filter==='all'||filter==='ready'&&j.available||filter==='locked'&&!j.available||filter==='active'&&busy.has(j.state)));
  $('file-count').textContent=jobs.length;
  const list=$('file-list');
  // Reuse rows while metrics poll, so keyboard focus and scroll never jump.
  const existing=new Map([...list.querySelectorAll('button[data-id]')].map(n=>[n.dataset.id,n]));
  list.querySelector('.empty-list')?.remove();
  const keep=new Set();
  for(const [index,j] of jobs.entries()){
    let row=existing.get(j.id);
    if(!row){row=el('button','file-item');row.dataset.id=j.id;row.onclick=()=>selectJob(j.id)}
    keep.add(j.id);
    const signature=[j.name,j.size,j.created,j.state,fileType(j)];
    if(changed('file-'+j.id,signature)||!row.children.length){
      const [type,glyph]=fileType(j), symbol=el('span','file-symbol '+type);symbol.append(icon(glyph));
      const wrap=el('div','file-text');wrap.append(el('span','file-name',j.name),el('span','file-detail',[bytes(j.size),date(j.created)].filter(Boolean).join(' · ')));
      row.replaceChildren(symbol,wrap,statusNode(j));
    }
    row.classList.toggle('selected',j.id===state.selected);row.setAttribute('aria-pressed',String(j.id===state.selected));
    if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);
  }
  for(const [id,row] of existing)if(!keep.has(id))row.remove();
  if(!jobs.length)list.append(el('p','empty-list','ファイルはありません'));
}
function definition(id, rows){
  if(!changed(id,rows))return;
  const nodes=[];for(const [key,value] of rows)nodes.push(el('dt','',key),el('dd','',value));$(id).replaceChildren(...nodes);
}
function renderSummary(j){
  const p=j.plan_summary;if(!p)return;
  const rows=[['方式',strategies[p.strategy]||p.strategy]];
  if(p.strategy==='mask'||p.strategy?.startsWith('hybrid_')){
    rows.push(['文字種',(p.charsets||[]).map(n=>charsetNames[n]||n).join('・')]);
    rows.push([p.strategy==='mask'?'長さ範囲':'追加文字数',`${p.min} ～ ${p.max} 文字`]);
  }
  if(p.candidates!==undefined)rows.push(['候補数',number(p.candidates)+' 通り']);
  if(p.strategy==='automatic')rows.push(['語句の長さ',p.length==='unknown'?'分からない':`${p.min} ～ ${p.max} 文字`]);
  if(p.groups?.length)rows.push(['候補グループ',p.groups.map(g=>g.name).join(' / ')]);
  definition('plan-summary',rows);
  if(changed('summary-notes',p.notes))$('summary-notes').replaceChildren(...(p.notes||[]).map(note=>el('p','',note)));
  definition('run-options-list',[
    ['時間上限',p.minutes+' 分'],['停止温度',p.temperature+' °C'],
    ['GPU負荷',p.tune?'自動測定':({'1':'低負荷','2':'標準','3':'高負荷',auto:'自動測定'}[p.workload]||p.workload)],
    ['カーネル',p.kernel==='pure'?'標準':'自動最適化'],['デバイス',p.devices||'自動']
  ]);
  $('summary-caption').textContent=busy.has(j.state)?'実行中の設定':'直前の設定';
}
function renderProgress(j){
  const m=j.metrics||{}, exporting=j.state==='converting';
  const measured=Number(m.total)>0;
  const percent=exporting?Math.max(0,Math.min(100,j.export_progress||0)):measured?Math.max(0,Math.min(100,Number(m.tested||0)/Number(m.total)*100)):0;
  $('progress-label').textContent=exporting?'書き出しの進捗':'候補範囲の進捗';
  $('progress-count').textContent=exporting?'書き出し中':measured?`${number(m.tested||0)} / ${number(m.total)}`:'—';
  $('percentage').textContent=measured||exporting?percent.toFixed(1)+'%':'—';
  $('progress-fill').style.width=percent+'%';
  $('job-progress').setAttribute('aria-valuenow',percent.toFixed(1));
  $('job-progress').setAttribute('aria-valuetext',measured||exporting?percent.toFixed(1)+'%':'計測待ち');
  updateMotion();
  const speed=Number(m.speed)||0;
  $('speed').textContent=speed>=1e9?(speed/1e9).toFixed(2)+' GH/s':speed>=1e6?(speed/1e6).toFixed(2)+' MH/s':speed?Math.round(speed).toLocaleString()+' H/s':'—';
  $('gpu-temp').textContent=m.temperature?m.temperature+' °C':'—';
  $('elapsed').textContent=j.elapsed?elapsed(j.elapsed):'00:00:00';
  const steps=exporting?['準備','書き出し','保存']:j.plan_summary?['候補準備','候補探索','開封']:['ファイル','照合','開封'];
  let current=0,done=false;
  if(j.available&&!exporting){current=2;done=true}
  else if(['recovering','paused','pausing','exhausted','converting'].includes(j.state)){current=1}
  else if(j.state==='unlocking'){current=j.plan_summary?2:1}
  else if((j.state==='cancelled'||j.state==='error')&&measured){current=1}
  for(const [index,id] of ['step-prepare','step-search','step-open'].entries()){
    const step=$(id);step.querySelector('.step-name').textContent=steps[index];
    step.classList.toggle('done',done||index<current);
    step.classList.toggle('current',!done&&index===current&&busy.has(j.state));
    if(!done&&index===current)step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');
  }
  $('stage-detail').textContent=m.phase==='tuning'&&j.state==='recovering'?'GPU負荷を測定中':m.stage&&m.stages?`探索範囲 ${m.stage} / ${m.stages}`:'';
}
function updateMotion(){
  const j=job();const fresh=j?.metrics_at&&Date.now()/1000-j.metrics_at<8;
  $('job-progress').classList.toggle('running',!!(j?.state==='recovering'&&fresh&&state.connected&&!document.hidden&&j.metrics?.total));
}
function renderEvents(j){
  if(!changed('events',[j.id,j.events]))return;
  const list=$('event-log'), atBottom=list.scrollHeight-list.scrollTop-list.clientHeight<32;
  const rows=(j.events||[]).map(event=>{const row=el('li');row.append(el('time','',time(event.time)),el('span','',event.text));return row});
  if(!rows.length)rows.push(el('li','muted','記録はありません'));
  list.replaceChildren(...rows);if(atBottom)list.scrollTop=list.scrollHeight;
}
function resetPasswordResult(){
  ++passwordRequest;passwordResult={id:null,phase:'empty',value:'',hidden:false,message:'',error:false,copying:false};
  $('password-result').value='';$('password-result').type='text';$('password-result-panel').hidden=true;
}
function renderPasswordResult(j){
  const available=!!(j?.available&&j.has_password);
  $('password-result-panel').hidden=!available;
  if(!available){if(passwordResult.id!==null)resetPasswordResult();return}
  if(passwordResult.id!==j.id){loadPasswordResult(j.id);return}
  const ready=passwordResult.phase==='ready';
  const field=$('password-result'),value=ready?passwordResult.value:'';
  if(field.value!==value)field.value=value;
  const type=passwordResult.hidden?'password':'text';if(field.type!==type)field.type=type;field.disabled=!ready;
  field.placeholder=passwordResult.phase==='loading'?'取得中…':'取得できませんでした';
  $('copy-password').disabled=!ready||passwordResult.copying;
  $('reveal-password').disabled=!ready;
  const visibilityLabel=passwordResult.hidden?'パスワードを表示':'パスワードを隠す';
  if($('reveal-password').title!==visibilityLabel){
    $('reveal-password').title=visibilityLabel;$('reveal-password').setAttribute('aria-label',visibilityLabel);
    $('reveal-password').replaceChildren(icon(passwordResult.hidden?'eye':'eye-off'));icons();
  }
  $('password-feedback').textContent=passwordResult.message;
  $('password-feedback').classList.toggle('field-error',passwordResult.error);
  $('retry-password').hidden=passwordResult.phase!=='error';
}
async function loadPasswordResult(id){
  const request=++passwordRequest;
  passwordResult={id,phase:'loading',value:'',hidden:false,message:'',error:false,copying:false};renderPasswordResult(job());
  try{
    const result=await api(`/api/jobs/${id}/password`,{});
    if(request!==passwordRequest||state.selected!==id||!job()?.has_password)return;
    if(typeof result.password!=='string'||!result.password)throw Error('No password available');
    passwordResult.value=result.password;passwordResult.phase='ready';
  }catch{
    if(request!==passwordRequest||state.selected!==id)return;
    passwordResult.phase='error';passwordResult.message='パスワードを取得できませんでした。';passwordResult.error=true;
  }
  if(request===passwordRequest&&state.selected===id)renderPasswordResult(job());
}
function renderDetail(){
  const j=job();$('empty').hidden=!!j;$('document').hidden=!j;if(!j)return;
  const [type,glyph,extension]=fileType(j);
  if(changed('document-icon',type)){$('document-icon').className='file-symbol '+type;$('document-icon').replaceChildren(icon(glyph))}
  $('document-name').textContent=j.name;$('document-type').textContent=extension;$('document-size').textContent=bytes(j.size);
  $('document-pages').textContent=j.info.pages?j.info.pages+' ページ':'';
  $('document-encryption').textContent=j.available?'開封済み':j.info.encryption||'';
  if(!j.available&&state.tab==='export')state.tab='unlock';
  for(const tab of ['unlock','export']){$('tab-'+tab).setAttribute('aria-selected',String(state.tab===tab));$('tab-'+tab).tabIndex=state.tab===tab?0:-1;$(tab+'-panel').hidden=state.tab!==tab}
  $('tab-export').disabled=!j.available;$('ready-state').hidden=!j.available;$('locked-state').hidden=j.available;
  const summary=!!j.plan_summary&&!state.editing&&state.mode==='recover';
  $('known-form').hidden=state.mode!=='known';$('recovery-form').hidden=state.mode!=='recover'||summary;$('run-summary').hidden=!summary;
  for(const mode of ['known','recover']){$(mode+'-mode').classList.toggle('selected',state.mode===mode);$(mode+'-mode').setAttribute('aria-pressed',String(state.mode===mode));$(mode+'-mode').disabled=busy.has(j.state)}
  $('edit-plan').hidden=busy.has(j.state);renderSummary(j);
  const download=`/api/jobs/${j.id}/download/unlocked${j.info.extension}`;
  $('unlocked-download').href=download;$('download-label').textContent='パスワードなしで保存';renderPasswordResult(j);
  for(const form of ['known-form','recovery-form','export-form'])for(const n of $(form).querySelectorAll('input,select,textarea,button'))n.disabled=busy.has(j.state)||form==='export-form'&&!j.available;
  recoveryControls();
  $('export-form').hidden=!j.can_convert;
  if(changed('outputs',[j.id,j.outputs])){
    const rows=(j.outputs||[]).map(out=>{
      const row=el('div','output-row');row.append(icon(out.kind==='word'?'file-text':'file-check'));
      const detail=el('div');detail.append(el('strong','',kinds[out.kind]||out.kind),el('small','',bytes(out.bytes)));
      const link=el('a','icon');link.href=`/api/jobs/${j.id}/download/${encodeURIComponent(out.file)}`;link.title=(kinds[out.kind]||out.kind)+'を保存';link.setAttribute('aria-label',link.title);link.append(icon('download'));row.append(detail,link);return row;
    });$('outputs').replaceChildren(...rows);
  }
  if(changed('status',j.state)){$('job-status-label').className='status'+statusClass(j);$('job-status-label').replaceChildren(icon(statusIcons[j.state]||'circle'),el('span','',labels[j.state]||j.state))}
  $('job-message').textContent=j.message||'';
  $('pause-job').hidden=!['preparing','recovering','queued'].includes(j.state);
  $('cancel-job').hidden=!['queued','preparing','recovering','converting','unlocking'].includes(j.state);
  $('cancel-label').textContent=j.state==='converting'?'書き出しを中止':'探索を中止';
  $('remove-file').disabled=busy.has(j.state);
  $('resume-job').hidden=!['paused','error','cancelled'].includes(j.state)||!j.can_resume;
  renderProgress(j);renderEvents(j);
  const warnings=[...(j.warnings||[]),...(j.info.recovery_note&&!j.available?[j.info.recovery_note]:[])];
  if(changed('warnings',warnings))$('warnings').replaceChildren(...warnings.map(w=>el('p','',w)));
  $('quick-download').setAttribute('aria-disabled',String(!j.available));$('quick-download').tabIndex=j.available?0:-1;
  if(j.available)$('quick-download').href=download;else $('quick-download').removeAttribute('href');
  $('export-options').disabled=!j.available;
  $('preview').hidden=!j.available||state.tab!=='unlock';
  $('page-indicator').textContent=j.has_pdf?`${state.page+1} / ${j.info.pages}`:'—';
  $('previous-page').disabled=!j.has_pdf||state.page<=0;$('next-page').disabled=!j.has_pdf||state.page>=j.info.pages-1;
  $('page-image').hidden=!j.has_pdf||!state.previewLoaded;$('contents-preview').hidden=!j.available||j.has_pdf;
  $('preview-message').hidden=!j.has_pdf||!!state.previewLoaded;$('refresh-preview').disabled=!j.has_pdf;
  if(changed('contents',[j.id,j.contents]))$('contents-preview').replaceChildren(...(j.contents||[]).map(item=>{
    const row=el('div','contents-row');row.append(icon(j.info.format==='zip'?'file':'file-text'),el('span','',item.name));if(item.size!==null)row.append(el('small','',bytes(item.size)));return row;
  }));
  if(j.has_pdf){const working=state.jobs.some(item=>['preparing','converting','unlocking'].includes(item.state));const key=`${j.id}/${state.page}/${working}`;if(key!==state.preview)loadPreview(j,key)}
  icons();
}
async function loadPreview(j,key){
  state.preview=key;state.previewLoaded=false;
  if(state.previewUrl)URL.revokeObjectURL(state.previewUrl);
  $('page-image').removeAttribute('src');$('page-image').hidden=true;
  $('preview-message').textContent='読み込み中…';$('preview-message').hidden=false;
  try{
    const response=await fetch(`/api/jobs/${j.id}/preview?page=${state.page}`);
    if(!response.ok){const error=await response.json();throw new Error(error.error||'プレビューを表示できません。')}
    const blob=await response.blob();if(state.preview!==key)return;
    state.previewUrl=URL.createObjectURL(blob);$('page-image').src=state.previewUrl;
    state.previewLoaded=true;$('page-image').hidden=false;$('preview-message').hidden=true;
  }catch(error){if(state.preview===key){$('preview-message').textContent=error.message;$('preview-message').hidden=false}}
}
$('refresh-preview').onclick=()=>{state.preview='';renderDetail()};
function render(){renderList();renderDetail();icons()}
async function refresh(){
  if(state.polling)return;state.polling=true;
  try{
    const result=await api('/api/jobs');state.jobs=result.jobs;
    if(!state.connected&&$('toast').textContent==='接続を確認しています。')$('toast').hidden=true;
    state.connected=true;$('connection-status').classList.remove('offline');
    $('connection-status').querySelector('span').textContent='ローカル動作';
    if(!state.jobs.some(j=>j.id===state.selected)){selectJob(state.jobs[0]?.id||null)}else render();
  }catch(e){if(state.connected)toast('接続を確認しています。');state.connected=false;$('connection-status').classList.add('offline');$('connection-status').querySelector('span').textContent='接続待ち';updateMotion()}
  finally{state.polling=false}
}
async function action(name,data={},id=state.selected){
  try{await api(`/api/jobs/${id}/${name}`,data);if(name==='recover'){state.editing=false;state.mode='recover'}if(name==='remove')drafts.delete(id);$('toast').hidden=true;await refresh();return true}catch(e){toast(e.message);return false}
}
function hintFields(){return {numbers:$('hint-numbers').value,separators:$('hint-symbols').value,combine:$('hint-combine').checked,typos:$('hint-typos').checked}}
let estimateVersion=0,estimateTimer;
function selectedStrategy(){return $('approach').value==='automatic'?'automatic':$('strategy').value}
function planFields(){
  const automatic=selectedStrategy()==='automatic';
  return {job_id:state.selected,strategy:selectedStrategy(),words:$('words').value,...hintFields(),
    min:Number($(automatic?'remember-min':'min-length').value),max:Number($(automatic?'remember-max':'max-length').value),
    prefix:$(automatic?'remember-prefix':'prefix').value,suffix:$(automatic?'remember-suffix':'suffix').value,
    length:$('remember-length').value,characters:$('remember-characters').value,
    charsets:[...document.querySelectorAll('[name=charset]:checked')].map(n=>n.value),
    minutes:Number($('minutes').value),temperature:Number($('temperature').value),
    workload:$('workload').value,kernel:$('kernel').value,devices:$('devices').value};
}
function recoveryControls(){
  for(const n of $('recovery-form').querySelectorAll('input,select,textarea,button'))n.disabled=busy.has(job()?.state)||!!n.closest('[hidden]');
  $('recovery-form').querySelector('button[type=submit]').disabled=busy.has(job()?.state)||!job()?.info.recoverable||!state.planValid;
}
function estimate(){
  const version=++estimateVersion;clearTimeout(estimateTimer);state.planValid=false;recoveryControls();
  $('remember-range').hidden=$('remember-length').value!=='range';recoveryControls();
  $('candidate-count').textContent='計算中';$('hint-summary').replaceChildren();$('plan-notes').replaceChildren();
  const data=planFields();
  estimateTimer=setTimeout(async()=>{
    try{const result=await api('/api/recovery/estimate',data);if(version!==estimateVersion)return;
      state.planValid=true;$('candidate-count').textContent=number(result.candidates)+' 試行';
      $('hint-summary').replaceChildren(...result.groups.map(g=>{const row=el('li');row.append(el('span','',g.name),el('span','muted',number(g.count)));return row}));
      const notes=[...(result.notes||[])];
      if(data.strategy!=='automatic')notes.push('最大127 UTF-8バイト。暗号方式によって探索できる長さは異なります。');
      $('plan-notes').replaceChildren(...notes.map(note=>el('p','',note)));
    }catch(e){if(version===estimateVersion){$('candidate-count').textContent='条件を確認';$('plan-notes').replaceChildren(el('p','field-error',e.message))}}
    finally{if(version===estimateVersion)recoveryControls()}
  },350);
}
function strategyChanged(){
  const strategy=selectedStrategy(),automatic=strategy==='automatic',hybrid=strategy.startsWith('hybrid_');
  $('manual-strategy').hidden=automatic;$('auto-questions').hidden=!automatic;$('guided-options').hidden=automatic;
  $('recovery-form').querySelector('h3').textContent=automatic?'覚えていること':'探索条件';
  $('guided-fields').hidden=!automatic&&strategy!=='guided';document.querySelector('label[for=words]').textContent=automatic?'心当たりのある語句は？（任意・1行1件）':strategy==='guided'?'覚えている単語（1行1件）':'候補リスト（1行1件）';
  $('mask-fields').hidden=strategy!=='mask'&&!hybrid;$('dictionary-fields').hidden=strategy==='mask';$('fixed-fields').hidden=hybrid;
  $('min-label').textContent=hybrid?'追加の最小文字数':'最小文字数';$('max-label').textContent=hybrid?'追加の最大文字数':'最大文字数';
  if(hybrid!==Boolean(state.hybrid)){$('min-length').value=hybrid?1:4;$('max-length').value=hybrid?2:6}state.hybrid=hybrid;estimate();
}
async function importFiles(files){
  for(const file of files){try{
    if(file.size>MAX_UPLOAD_MB*1024*1024)throw Error(`${MAX_UPLOAD_MB}MBを超えるファイルです。`);toast(file.name+' を読み込み中');
    const r=await fetch('/api/import',{method:'POST',headers:{'X-Loxmit':'1','X-Filename':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file});
    const data=await r.json();if(!r.ok)throw Error(data.error);await refresh();selectJob(data.id);$('toast').hidden=true;
  }catch(e){toast(e.message)}}$('files').value='';
}
for(const id of ['add-files','empty-add'])$(id).onclick=()=>$('files').click();
$('files').onchange=()=>importFiles($('files').files);$('search').oninput=()=>{renderList();icons()};$('filter').onchange=()=>{renderList();icons()};
$('tab-unlock').onclick=()=>setTab('unlock');$('tab-export').onclick=()=>setTab('export');$('export-options').onclick=()=>setTab('export');
document.querySelector('[role=tablist]').onkeydown=e=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();
  const tabs=[...document.querySelectorAll('[role=tab]:not(:disabled)')];let index=tabs.indexOf(document.activeElement);
  index=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  tabs[index].click();tabs[index].focus();
};
for(const mode of ['known','recover'])$(mode+'-mode').onclick=()=>{state.mode=mode;renderDetail()};
$('edit-plan').onclick=()=>{state.editing=true;renderDetail();$('approach').focus()};
$('toggle-password').onclick=()=>{$('password').type=$('password').type==='password'?'text':'password'};
$('known-form').onsubmit=async e=>{e.preventDefault();const id=state.selected;const ok=await action('unlock',{password:$('password').value},id);if(ok&&id===state.selected)$('password').value=''};
$('recovery-form').onsubmit=e=>{e.preventDefault();if(state.planValid)action('recover',planFields())};
$('approach').onchange=strategyChanged;
$('strategy').onchange=strategyChanged;$('recovery-form').oninput=estimate;$('load-words').onclick=()=>$('word-file').click();
$('word-file').onchange=async()=>{const f=$('word-file').files[0];if(f){if(f.size>12*1024*1024)return toast('候補ファイルが大きすぎます。');$('words').value=await f.text();estimate()}};
for(const [id,name] of [['pause-job','pause'],['resume-job','resume'],['cancel-job','cancel']])$(id).onclick=()=>action(name);
$('previous-page').onclick=()=>{state.page--;renderDetail()};$('next-page').onclick=()=>{state.page++;renderDetail()};
$('page-image').onerror=()=>toast('プレビューを生成できませんでした。');
$('reveal-password').onclick=()=>{if(passwordResult.phase==='ready'){passwordResult.hidden=!passwordResult.hidden;renderPasswordResult(job())}};
$('retry-password').onclick=()=>{if(job()?.has_password)loadPasswordResult(state.selected)};
$('copy-password').onclick=async()=>{
  if(passwordResult.phase!=='ready'||passwordResult.id!==state.selected||passwordResult.copying)return;
  const id=state.selected,request=passwordRequest,value=passwordResult.value;
  passwordResult.copying=true;passwordResult.message='';passwordResult.error=false;renderPasswordResult(job());
  try{
    await navigator.clipboard.writeText(value);
    if(request!==passwordRequest||state.selected!==id)return;
    passwordResult.message='コピーしました。';
  }catch{
    if(request!==passwordRequest||state.selected!==id)return;
    passwordResult.message='コピーできませんでした。';passwordResult.error=true;
    if(!passwordResult.hidden){$('password-result').focus();$('password-result').select()}
  }finally{if(request===passwordRequest&&state.selected===id){passwordResult.copying=false;renderPasswordResult(job())}}
};
const notes={pdf:'Officeの印刷レイアウト',image_pdf:'画像のみ・テキスト検索なし',word:'ページ画像・本文の文字編集なし',images:'PNG / 1ページ1枚',text:'OCRなし・元のテキスト層に依存（文字化けの可能性あり）'};
function exportNote(){$('format-note').textContent=notes[$('export-kind').value];$('image-options').hidden=['text','pdf'].includes($('export-kind').value)}
$('export-kind').onchange=exportNote;$('export-form').onsubmit=e=>{e.preventDefault();action('export',{kind:$('export-kind').value,dpi:Number($('dpi').value),grayscale:$('color').value==='gray'})};
let savedSettings={},settingsBusy=false,settingsGpuChecked=false;
function settingsDraft(){return {hashcat:$('hashcat-path').value.trim(),zip2john:$('zip2john-path').value.trim()}}
function settingsDirty(){const draft=settingsDraft();return draft.hashcat!==(savedSettings.hashcat||'')||draft.zip2john!==(savedSettings.zip2john||'')}
function settingsFeedback(message,error=false){$('settings-feedback').textContent=message;$('settings-feedback').hidden=!message;$('settings-feedback').classList.toggle('field-error',error)}
function clearSettingsErrors(){
  for(const key of ['hashcat','zip2john']){$(key+'-error').hidden=true;$(key+'-path').removeAttribute('aria-invalid')}
  settingsFeedback('');
}
function settingsError(error){
  settingsFeedback(error.message,true);
  if(['hashcat','zip2john'].includes(error.field)){
    $('engine-paths').open=true;$(error.field+'-error').textContent=error.message;$(error.field+'-error').hidden=false;
    $(error.field+'-path').setAttribute('aria-invalid','true');$(error.field+'-path').focus();
  }
}
function updateSettingsState(){
  const dirty=settingsDirty(), draft=settingsDraft(), locked=!!savedSettings.settings_locked;
  $('hashcat-status').textContent=dirty?'未保存':savedSettings.hashcat_configured?'場所を設定済み':savedSettings.hashcat?'ファイルが見つかりません':'未設定';
  const gpu=settingsGpuChecked?'デバイス照会済み':'GPU未確認';
  $('recovery-availability').textContent=dirty?'未保存':savedSettings.hashcat_configured?gpu:'Hashcat未設定';
  $('zip-availability').textContent=dirty?'未保存':!savedSettings.hashcat_configured?'Hashcat未設定':savedSettings.zip2john_configured?gpu:'zip2john未設定';
  $('settings-save-state').textContent=locked?'探索中は変更できません':dirty?'未保存':'';
  $('diagnostics-label').textContent=dirty?'保存してGPUを確認':'GPUを確認';
  for(const node of $('settings-form').querySelectorAll('input,button'))node.disabled=settingsBusy||(locked&&node.id!=='settings-close');
  $('diagnostics').disabled=settingsBusy||locked||!draft.hashcat;
}
function applySettings(s){savedSettings=s;$('hashcat-path').value=s.hashcat||'';$('zip2john-path').value=s.zip2john||'';$('output-path').textContent=s.output_dir;updateSettingsState()}
async function saveSettings(){
  clearSettingsErrors();const result=await api('/api/settings',settingsDraft());applySettings(result);return result;
}
$('settings-open').onclick=async()=>{try{
  const s=await api('/api/settings');clearSettingsErrors();settingsBusy=false;settingsGpuChecked=false;applySettings(s);
  $('engine-paths').open=false;$('diagnostics-details').hidden=true;$('diagnostics-details').open=false;
  $('gpu-status').textContent='未確認';$('settings-dialog').showModal();
}catch(e){toast(e.message)}};
$('settings-close').onclick=()=>$('settings-dialog').close();
function showSecurity(result){
  const descriptions={
    unchecked:['未確認','OS設定の照会のみ行います。暗号化の開始や回復キーの取得は行いません。'],
    protected:['保護を確認',result.method+'による保存先の保護を確認しました。'],
    unprotected:['保護が無効',result.method+'が無効、または保護が中断されています。回復キーを確保してからOSの設定を確認してください。'],
    not_detected:['暗号化経路を検出できません', 'dm-cryptは検出されませんでした。別方式の暗号化は未確認です。'],
    unknown:['確認できません','権限不足・確認コマンド未対応・外付けドライブなどが考えられます。未暗号化と断定した結果ではありません。OSの設定で確認してください。']
  };
  const [title,detail]=descriptions[result.storage.state]||descriptions.unknown;
  $('security-storage-state').textContent=title;$('security-storage-detail').textContent=detail;
  $('security-help').href=result.help_url;
  $('security-checked-at').textContent=result.checked_at?'確認日時 '+new Date(result.checked_at*1000).toLocaleString():'';
}
$('security-open').onclick=async()=>{try{showSecurity(await api('/api/security'));$('security-dialog').showModal()}catch(error){toast(error.message)}};
$('security-close').onclick=()=>$('security-dialog').close();
$('security-check').onclick=async()=>{
  $('security-check').disabled=true;$('security-storage-state').textContent='確認中…';
  try{showSecurity(await api('/api/security/check',{}))}catch(error){$('security-storage-state').textContent='確認できません';$('security-storage-detail').textContent=error.message}
  finally{$('security-check').disabled=false}
};
$('settings-dialog').addEventListener('cancel',event=>{if(settingsBusy)event.preventDefault()});
$('settings-form').oninput=()=>{clearSettingsErrors();settingsGpuChecked=false;$('gpu-status').textContent='未確認';$('diagnostics-details').hidden=true;updateSettingsState()};
$('settings-form').onsubmit=async e=>{e.preventDefault();settingsBusy=true;updateSettingsState();try{await saveSettings();$('settings-dialog').close();toast('設定を保存しました');await refresh()}catch(error){settingsError(error)}finally{settingsBusy=false;updateSettingsState();const invalid=$('settings-form').querySelector('[aria-invalid=true]');if(invalid)invalid.focus()}};
$('detect-tools').onclick=async()=>{
  settingsBusy=true;updateSettingsState();clearSettingsErrors();settingsFeedback('インストール済みの実行ファイルを確認中…');
  try{
    const result=await api('/api/settings/detect',{});let applied=0;
    for(const key of ['hashcat','zip2john'])if(!$(key+'-path').value.trim()&&result[key]){$(key+'-path').value=result[key];applied++}
    if(applied){settingsGpuChecked=false;$('gpu-status').textContent='未確認';$('engine-paths').open=true;settingsFeedback('検出した場所を入力しました。未保存です。')}
    else settingsFeedback(result.hashcat||result.zip2john?'入力済みの場所を維持しました。':'自動検出では見つかりませんでした。');
  }catch(error){settingsError(error)}finally{settingsBusy=false;updateSettingsState()}
};
$('diagnostics').onclick=async()=>{
  settingsBusy=true;updateSettingsState();$('gpu-status').textContent='確認中…';clearSettingsErrors();
  try{
    if(settingsDirty())await saveSettings();
    const result=await api('/api/diagnostics',{});$('diagnostics-result').textContent=result.text;
    $('diagnostics-details').hidden=false;$('diagnostics-details').open=result.code!==0;
    $('gpu-status').textContent=result.code===0?'照会完了':'確認できませんでした';
    settingsGpuChecked=result.code===0;
  }catch(error){$('gpu-status').textContent='未確認';settingsError(error)}
  finally{settingsBusy=false;updateSettingsState();const invalid=$('settings-form').querySelector('[aria-invalid=true]');if(invalid)invalid.focus()}
};
$('shutdown').onclick=async()=>{try{await api('/api/shutdown',{});clearInterval(poll);clearInterval(motionPoll);state.connected=false;updateMotion();toast('アプリを終了しました。');document.querySelectorAll('button').forEach(b=>b.disabled=true)}catch(e){toast(e.message)}};
let drag=0;window.addEventListener('dragenter',e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();drag++;$('drop-overlay').hidden=false}});
window.addEventListener('dragleave',()=>{if(--drag<=0){drag=0;$('drop-overlay').hidden=true}});window.addEventListener('dragover',e=>e.preventDefault());
window.addEventListener('drop',e=>{e.preventDefault();drag=0;$('drop-overlay').hidden=true;importFiles(e.dataTransfer.files)});
document.addEventListener('visibilitychange',updateMotion);
let removeId=null;$('remove-file').onclick=()=>{const j=job();if(j){removeId=j.id;$('remove-name').textContent=j.name;$('remove-dialog').showModal()}};
$('remove-cancel').onclick=()=>$('remove-dialog').close();$('remove-confirm').onclick=async()=>{if(removeId&&await action('remove',{},removeId))$('remove-dialog').close()};
if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js').catch(()=>{});
icons();strategyChanged();exportNote();refresh();const poll=setInterval(refresh,1800),motionPoll=setInterval(updateMotion,1000);
