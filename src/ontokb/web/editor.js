/* A single edit session: all changes pass through the server's validation and audit log. */
(() => {
  const byId = id => document.getElementById(id);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const dialog = el('dialog'); dialog.id = 'knowledge-editor'; dialog.setAttribute('aria-labelledby', 'ke-title');
  dialog.innerHTML = '<div class="ke-shell"><header class="ke-header"><div><div class="eyebrow">CURATE YOUR KNOWLEDGE</div><h2 id="ke-title">整理知识</h2><p>修正实体、核实论断，让每一条连接更准确。</p></div><div class="ke-header-actions"><button type="button" id="ke-history">修改记录</button><button type="button" id="ke-close" aria-label="关闭知识编辑器">×</button></div></header><div class="ke-layout"><aside class="ke-sidebar"><div class="ke-search"><input id="ke-search" type="search" placeholder="搜索名称、别名或关系…" aria-label="搜索知识记录"></div><div class="ke-tabs" role="tablist" aria-label="知识类别"><button role="tab" data-kind="entities" aria-selected="true">实体</button><button role="tab" data-kind="claims" aria-selected="false">论断</button><button role="tab" data-kind="triples" aria-selected="false">关系</button></div><div id="ke-count" class="ke-count" aria-live="polite"></div><div id="ke-list" class="ke-list" aria-label="知识记录"></div></aside><section class="ke-main"><div id="ke-content" class="ke-content"></div><footer class="ke-footer" id="ke-footer"><span id="ke-dirty">选择一条记录，开始整理</span><button type="button" id="ke-delete" class="ke-danger" hidden>删除关系</button><button type="button" id="ke-reset" disabled>重置修改</button><button type="submit" form="ke-form" id="ke-save" class="primary" disabled>保存修改</button></footer></section></div><div id="ke-feedback" class="ke-feedback" role="status" aria-live="polite"></div></div>';
  document.body.append(dialog);
  const articleFilters=el('div','ke-article-filters');
  articleFilters.innerHTML='<label>文章分类<select id="ke-category" aria-label="按文章分类筛选"><option value="">全部分类</option></select></label><label>来源文章<select id="ke-article" aria-label="按来源文章筛选"><option value="">全部文章</option></select></label>';
  dialog.querySelector('.ke-tabs').before(articleFilters);
  let category='',article='',entitySources=new Map();
  function articleSources(){
    // Use the same library as the workbench, including with older running APIs.
    if(typeof DATA!=='undefined'&&Array.isArray(DATA.library))return DATA.library;
    return (data.sources||[]).filter(s=>!s.status||s.status==='processed');
  }
  function renderArticleFilters(){
    const sources=articleSources();
    const categories=[...new Set(sources.flatMap(s=>s.categories||['未分类']))];
    if(!categories.includes(category))category='';
    selectOptions(byId('ke-category'),[{value:'',label:'全部分类'},...categories.map(c=>({value:c,label:c}))],category);
    const visible=sources.filter(s=>!category||(s.categories||['未分类']).includes(category));
    if(!visible.some(s=>String(s.id)===article))article='';
    selectOptions(byId('ke-article'),[{value:'',label:'全部文章'},...visible.map(s=>({value:String(s.id),label:s.title||s.id}))],article);
  }
  function articleMatches(row){
    if(!category&&!article)return true;
    const sources=kind==='triples'?new Set([String(row.source)]):entitySources.get(String(row.id))||new Set();
    return articleSources().some(s=>sources.has(String(s.id))&&(!article||String(s.id)===article)&&(!category||(s.categories||['未分类']).includes(category)));
  }
  const filters=el('div','ke-memory-filters');
  filters.innerHTML='<select id="ke-memory-scope" aria-label="个人记忆范围"><option value="all">全部知识</option><option value="included">个人记忆</option><option value="excluded">仅资料库</option></select><select id="ke-memory-review-filter" aria-label="个人审核状态"><option value="all">全部审核状态</option><option value="reviewed">已审核</option><option value="unreviewed">未审核</option></select>';
  byId('ke-count').before(filters);
  let memoryData=null,memoryError='',memoryDirty=false,memoryBaseline='',memoryStale=false;
  const stanceLabels={unset:'未表态',agree:'认同',uncertain:'存疑',disagree:'不认同'};
  const memoryRecord=row=>memoryData?.records?.find(r=>r.current && r.snapshot.kind===(kind==='triples'?'triple':row.type==='Claim'?'claim':'entity') && String(r.current_target_id??r.snapshot.target_id)===String(row.id));
  let data = null, kind = 'entities', selected = null, baseline = '', busy = false, dirty = false, lastFocus = null, pending = null;
  const statusLabels = {unverified:'待核实',pending:'待核实',verified:'已核实',disputed:'有争议',refuted:'已否定',rejected:'已否定'};
  const typeLabel = value => (typeof TYPE_CN !== 'undefined' && TYPE_CN[value]) || value;
  const relationLabels = {mentions:'提及',about:'主题是',author:'作者',publisher:'发布者',worksFor:'任职于',citation:'引用',develops:'开发',adopts:'采用',makes:'制造',uses:'使用',competesWith:'竞争对手',relatedTo:'相关',participatesIn:'参与',doesNotParticipateIn:'不参与',makesClaim:'提出论断',supports:'支持',contradicts:'反驳'};
  const relationLabel = name => relationLabels[name] ? relationLabels[name]+' · '+name : name;
  const entity = id => data.entities.find(e => String(e.id) === String(id));
  const entityName = id => entity(id)?.name || String(id || '未知实体');
  const sourceTitle = row => (data.sources||[]).find(s=>String(s.id)===String(row.source))?.title || row.source || '未记录来源';
  const tripleTitle = row => entityName(row.subject_id) + ' → ' + row.predicate + ' → ' + entityName(row.object_id);
  function feedback(message, error = false) { const n = byId('ke-feedback'); n.replaceChildren(); n.classList.toggle('error', error); if (message) n.append(document.createTextNode(message)); }
  async function request(path, body) {
    const response = await fetch(apiUrl(path, {}), body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const result = await response.json(); if (!response.ok) {const error=new Error(result.error || '操作失败，请稍后重试。');error.status=response.status;throw error;} return result;
  }
  function setBusy(value) { busy = value; dialog.querySelectorAll('input, select, textarea, #ke-confirm button').forEach(n=>n.disabled=value); for(const id of ['ke-memory-scope','ke-memory-review-filter'])byId(id).disabled=value||!memoryData; dialog.setAttribute('aria-busy', String(value)); byId('ke-save').textContent = value ? '正在保存…' : '保存修改'; syncButtons(); }
  function syncButtons() { byId('ke-save').disabled = busy || memoryDirty || !dirty || !selected; byId('ke-reset').disabled = busy || !dirty; byId('ke-delete').disabled = busy || memoryDirty; if(byId('ke-memory-save'))byId('ke-memory-save').disabled=busy||!memoryDirty||memoryStale; byId('ke-dirty').textContent = busy ? '正在同步知识库…' : memoryDirty ? '● 请先保存或重置个人记忆设置' : dirty ? '● 有尚未保存的知识修改' : selected ? '当前表单没有待保存修改' : '选择一条记录，开始整理'; }
  function values() {
    if (!selected || !byId('ke-form')) return {};
    if (kind === 'triples') return {subject_id:Number(byId('ke-subject').value), object_id:Number(byId('ke-object').value), predicate:byId('ke-predicate').value, confidence:Number(byId('ke-confidence').value)};
    const result = {name:byId('ke-name').value.trim(), type:byId('ke-type').value, aliases:[...new Set(byId('ke-aliases').value.split(/\n/).map(s => s.trim()).filter(Boolean))]};
    if (byId('ke-review')) result.verificationStatus = byId('ke-review').value;
    return result;
  }
  function track() { dirty = JSON.stringify(values()) !== baseline; syncButtons(); }
  function guard(action) {
    if (busy) return;
    if (!dirty&&!memoryDirty) return action();
    pending = action; byId('ke-confirm')?.remove();
    const box = el('div','ke-confirm'); box.id = 'ke-confirm'; box.setAttribute('role','alertdialog'); box.setAttribute('aria-label','尚未保存的修改');
    box.append(el('p','','这条记录有未保存的修改。离开会丢弃这些修改。'));
    const stay = el('button','','继续编辑'), discard = el('button','ke-danger','放弃修改并离开');
    stay.onclick = () => {box.remove();pending=null;}; discard.onclick = () => {dirty=false;memoryDirty=false;box.remove();const next=pending;pending=null;next?.();};
    box.append(stay,discard);byId('ke-content').append(box);box.scrollIntoView({block:'nearest'});stay.focus();
  }
  function renderList() {
    const q = byId('ke-search').value.trim().toLocaleLowerCase();
    const records = (kind === 'triples' ? data.triples : data.entities.filter(e => (e.type === 'Claim') === (kind === 'claims'))).filter(articleMatches);
    const scope=byId('ke-memory-scope').value,review=byId('ke-memory-review-filter').value;
    const found = records.filter(r => {const m=memoryRecord(r);return (kind === 'triples' ? tripleTitle(r)+' '+sourceTitle(r) : r.name+' '+(r.aliases||[]).join(' ')+' '+typeLabel(r.type)).toLocaleLowerCase().includes(q)&&(scope==='all'||(!!m?.included===(scope==='included')))&&(review==='all'||(!!m?.reviewed===(review==='reviewed')));});
    byId('ke-count').textContent = `${found.length} 条${q ? '匹配记录' : '记录'} · ${kind === 'triples' ? '连接与证据' : kind === 'claims' ? '观点与事实核实' : '名称、类型与别名'}`;
    const list = byId('ke-list');list.replaceChildren();
    for (const row of found.slice(0,250)) {
      const button = el('button','ke-item');button.type='button';button.setAttribute('aria-current',String(selected?.id === row.id));
      button.append(el('strong','',kind === 'triples' ? tripleTitle(row) : row.name));
      button.append(el('small','',kind === 'triples' ? sourceTitle(row)+' · '+Math.round((row.confidence ?? 1)*100)+'% 置信度' : typeLabel(row.type)+(row.type==='Claim'?' · '+(statusLabels[row.verificationStatus]||row.verificationStatus||'待核实'):'')));
      const m=memoryRecord(row);button.append(el('small','ke-memory-badge',memoryData?`${m?.included?'个人记忆':'资料库'} · ${m?.reviewed?'已审核':'未审核'}`:'个人记忆状态暂不可用'));
      button.onclick = () => guard(() => select(row));list.append(button);
    }
    if (!found.length) list.append(el('div','ke-empty',q||category||article?'没有匹配项，试试其他分类、文章或关键词。':'还没有这类知识记录。'));
    if (found.length > 250) list.append(el('div','ke-source','显示前 250 条，请搜索以缩小范围。'));
  }
  function field(form, title, id, tag, value, help) { const label = el('label','',title);const input = el(tag);input.id=id;input.name=id;if(tag!=='select')input.value=value??'';label.append(input);if(help)label.append(el('span','ke-field-help',help));form.append(label);return input; }
  function selectOptions(input, options, selectedValue) { input.replaceChildren();for (const option of options) input.add(new Option(option.label, option.value)); if (![...input.options].some(o=>o.value===String(selectedValue)) && selectedValue) input.add(new Option(String(selectedValue),String(selectedValue))); input.value=String(selectedValue??''); }
  function searchableEndpoint(input, options, title){
    const search=el('input');search.type='search';search.placeholder='输入名称，筛选实体…';search.setAttribute('aria-label','搜索'+title);search.className='ke-endpoint-search';input.before(search);
    search.addEventListener('input',()=>{const value=input.value;const q=search.value.trim().toLocaleLowerCase();input.replaceChildren();selectOptions(input,options.filter(o=>o.value===value||o.label.toLocaleLowerCase().includes(q)),value);});
  }
  function evidence(parent, row) {const source=(data.sources||[]).find(s=>String(s.id)===String(row.source));const wrap=el('div','ke-section');wrap.append(el('h4','','原始证据 · 只读'));wrap.append(el('blockquote','ke-evidence',row.evidence||'这条关系尚未保存逐字证据。'));wrap.append(el('div','ke-source','来源：'+(source?.title||row.source||row.source_id||'未记录来源')));parent.append(wrap);}
  function select(row) {
    selected=row;dirty=false;memoryDirty=false; const content=byId('ke-content');content.replaceChildren(); byId('ke-delete').hidden=kind!=='triples';
    content.append(el('div','eyebrow',kind==='triples'?'RELATIONSHIP':'KNOWLEDGE RECORD'));if(row.manual)content.append(el('div','ke-source','人工修订 · 重新抽取时保留'));
    content.append(el('h3','',kind==='triples'?'修正一条连接':row.type==='Claim'?'核实与修正论断':'编辑实体'));
    content.append(el('p','ke-subtitle',kind==='triples'?'明确谁与谁有关，并保留这条连接的原始依据。':'修改后会同步关联关系；原始出处与证据继续保留。'));
    const form=el('form');form.id='ke-form';content.append(form);
    if (kind==='triples') {
      const options=data.entities.map(e=>({value:String(e.id),label:e.name+' · '+typeLabel(e.type)}));
      const subject=field(form,'起点实体','ke-subject','select');selectOptions(subject,options,row.subject_id);searchableEndpoint(subject,options,'起点实体');
      const predicate=field(form,'关系类型','ke-predicate','select');selectOptions(predicate,data.relations.map(r=>({value:typeof r==='string'?r:r.name,label:relationLabel(typeof r==='string'?r:r.name)})),row.predicate);
      const object=field(form,'终点实体','ke-object','select');selectOptions(object,options,row.object_id);searchableEndpoint(object,options,'终点实体');
      const conf=field(form,'置信度','ke-confidence','input',row.confidence??1,'范围 0–1，为抽取／关系置信度，不代表事实已经核实。');conf.type='number';conf.min='0';conf.max='1';conf.step='0.01';conf.required=true;
      evidence(content,row);
    } else {
      const name=field(form,row.type==='Claim'?'论断内容':'实体名称','ke-name','input',row.name);name.required=true;name.maxLength=500;name.className='ke-name';name.type='text';name.title='最多 500 个字符';name.addEventListener('input',()=>name.setCustomValidity(/[\r\n]/.test(name.value)?'名称或论断内容不能包含换行。':''));
      const type=field(form,'实体类型','ke-type','select');selectOptions(type,data.types.map(t=>({value:typeof t==='string'?t:t.name,label:typeLabel(typeof t==='string'?t:t.name)})),row.type);
      field(form,'别名','ke-aliases','textarea',(row.aliases||[]).join('\n'),'每行一个别名，用于搜索与摘要中的名称匹配。');
      const reviewWrap=el('div');form.append(reviewWrap);
      function reviewField(){reviewWrap.replaceChildren();if(type.value==='Claim'){const review=field(reviewWrap,'核实状态','ke-review','select');selectOptions(review,(data.review_statuses||['unverified','verified','disputed','refuted']).map(s=>({value:typeof s==='string'?s:s.value||s.name,label:statusLabels[typeof s==='string'?s:s.value||s.name]||s.label||s})),row.verificationStatus||'unverified');}}
      reviewField();type.addEventListener('change',()=>{reviewField();track();});
      const related=data.triples.filter(t=>String(t.subject_id)===String(row.id)||String(t.object_id)===String(row.id));
      const section=el('div','ke-section');section.append(el('h4','','关联关系 · '+related.length));
      related.slice(0,30).forEach(t=>{const b=el('button','ke-related',tripleTitle(t)+' ↗');b.type='button';b.onclick=()=>guard(()=>{kind='triples';updateTabs();select(t);});section.append(b);});
      if(!related.length)section.append(el('div','ke-source','暂时没有关联关系。'));
      form.insertBefore(section,byId('ke-aliases').parentElement);
    }
    form.addEventListener('input',track);form.addEventListener('change',track);form.addEventListener('submit',save);
    renderMemory();baseline=JSON.stringify(values());syncButtons();renderList();content.scrollTop=0;
  }
  function updateTabs(){dialog.querySelectorAll('[data-kind]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.kind===kind)));}
  async function reloadMemory(){try{memoryData=await request('/api/memory');memoryError='';}catch(error){memoryData=null;memoryError=error.message;}for(const id of ['ke-memory-scope','ke-memory-review-filter']){byId(id).disabled=!memoryData;if(!memoryData)byId(id).value='all';}}
  function memoryValues(){return {reviewed:byId('ke-memory-reviewed').value==='true',included:byId('ke-memory-included').value==='true',stance:byId('ke-memory-stance')?.value||'unset',note:byId('ke-memory-note').value,source_id:byId('ke-memory-source').value};}
  function renderMemory(){
    byId('ke-memory-section')?.remove();memoryDirty=false;memoryStale=false;
    const section=el('section','ke-section ke-memory-section');section.id='ke-memory-section';
    section.append(el('h4','','这条记录的个人记忆'),el('p','ke-field-help','审核＝已检查；收录＝愿意记住。均不代表事实已核实或立场认同，仅作用于当前记录。'));
    byId('ke-content').prepend(section);
    const row=memoryRecord(selected);
    if(!row){section.append(el('p','ke-source',memoryData?'未找到当前记录的记忆状态，请重新打开编辑器读取最新知识。':'个人记忆暂不可用：'+memoryError));syncButtons();return;}
    const form=el('form');form.id='ke-memory-form';section.append(form);
    const reviewed=field(form,'审核状态','ke-memory-reviewed','select');selectOptions(reviewed,[{value:'false',label:'未审核'},{value:'true',label:'已审核'}],String(row.reviewed));
    const included=field(form,'记忆范围','ke-memory-included','select');selectOptions(included,[{value:'false',label:'仅保留在资料库'},{value:'true',label:'纳入个人记忆'}],String(row.included));
    included.addEventListener('change',()=>{if(included.value==='true')reviewed.value='true';});
    if(row.snapshot.kind!=='entity'){const stance=field(form,'我的立场 · 与核实状态独立','ke-memory-stance','select');selectOptions(stance,Object.entries(stanceLabels).map(([value,label])=>({value,label})),row.stance);}
    for(const id of ['ke-memory-reviewed','ke-memory-included','ke-memory-stance'])byId(id)?.parentElement.classList.add('ke-memory-short');
    const note=field(form,'我的判断或适用条件','ke-memory-note','textarea',row.note);note.maxLength=4000;
    const source=field(form,'这次判断受哪篇资料影响（可选）','ke-memory-source','select');selectOptions(source,[{value:'',label:'没有指定资料'},...(memoryData.sources||[]).map(s=>({value:s.id,label:s.title||s.id}))],'');
    const actions=el('div','ke-memory-actions'),save=el('button','primary','保存个人记忆'),reset=el('button','','重置个人记忆设置');save.id='ke-memory-save';save.type='submit';reset.type='button';reset.onclick=()=>{if(!busy)renderMemory();};actions.append(save,reset);form.append(actions);
    const message=el('p','ke-memory-message');message.id='ke-memory-message';message.setAttribute('role','status');section.append(message);
    memoryBaseline=JSON.stringify(memoryValues());
    const trackMemory=()=>{memoryDirty=JSON.stringify(memoryValues())!==memoryBaseline;syncButtons();};form.addEventListener('input',trackMemory);form.addEventListener('change',trackMemory);
    form.onsubmit=async event=>{
      event.preventDefault();if(busy||!memoryDirty||memoryStale||!form.reportValidity())return;
      const payload={key:row.key,revision:row.revision,...memoryValues()};setBusy(true);message.textContent='正在保存个人记忆…';
      try{
        const result=await request('/api/memory/review',payload);memoryDirty=false;memoryBaseline=JSON.stringify(memoryValues());await reloadMemory();
        if(memoryData){renderMemory();byId('ke-memory-message').textContent=(result.changed===false?'个人记忆未发生变化，未新增变化记录。':'个人记忆已保存，判断变化已记录。')+'知识内容的修改仍需单独保存。';renderList();}
        else {memoryStale=true;message.textContent='个人记忆已保存，但最新状态读取失败。请重新打开编辑器；不要重复提交。';}
      }catch(error){
        message.textContent=error.message+' 个人记忆设置尚未保存，输入已保留。';
        if(error.status===409){memoryStale=true;const refresh=el('button','','放弃这部分输入并加载最新个人记忆');refresh.type='button';refresh.onclick=async()=>{if(busy)return;setBusy(true);await reloadMemory();if(memoryData){renderMemory();renderList();}else message.textContent='读取失败：'+memoryError+' 输入仍保留。';setBusy(false);};message.append(refresh);}
      }finally{setBusy(false);}
    };
    syncButtons();
  }
  async function reload() {data=await request('/api/editor');data.entities=data.entities||[];data.triples=data.triples||[];data.types=data.types||[];data.relations=data.relations||[];
    entitySources=new Map(data.entities.map(e=>[String(e.id),new Set((e.sources||[]).map(String))]));
    data.triples.forEach(t=>[t.subject_id,t.object_id].forEach(id=>entitySources.get(String(id))?.add(String(t.source))));
    renderArticleFilters();await reloadMemory();}
  async function refreshGraph() {try{await refreshReading(currentDoc?.id);}catch(error){feedback('修改已保存，但图谱刷新失败。请刷新页面查看最新内容。',true);}}
  async function complete(result, message, selectedId) {
    dirty=false;await reload();const rows=kind==='triples'?data.triples:data.entities;const next=rows.find(r=>String(r.id)===String(selectedId));if(next){if(kind!=='triples'){kind=next.type==='Claim'?'claims':'entities';updateTabs();}select(next);}else empty();renderList();feedback(message);
    if(result.change_id){const undo=el('button','','撤销本次');undo.onclick=()=>guard(()=>undoChange(result.change_id));byId('ke-feedback').append(undo);}
    await refreshGraph();
  }
  async function save(event) {event.preventDefault();if(busy||!dirty||!selected)return;if(memoryDirty){feedback('请先保存或重置个人记忆设置，再保存知识内容。',true);return;} if(!byId('ke-form').reportValidity())return;const id=selected.id;setBusy(true);feedback('');try{const result=await request('/api/editor/'+(kind==='triples'?'triples':'entities')+'/'+encodeURIComponent(id),{...values(),revision:selected.revision});await complete(result,'已保存，图谱与关联记录已更新。',id);}catch(error){feedback(error.message+' 你的输入已保留。',true);}finally{setBusy(false);}}
  async function undoChange(id){setBusy(true);try{const result=await request('/api/editor/changes/'+encodeURIComponent(id)+'/undo',{});await complete({},'已撤销本次修改。',selected?.id);}catch(error){feedback(error.message,true);}finally{setBusy(false);}}
  function showHistory(){
    empty();renderList();const content=byId('ke-content');content.replaceChildren(el('div','eyebrow','EDIT HISTORY'),el('h3','','修改记录'),el('p','ke-subtitle','每次人工修订都有记录。撤销前会检查数据是否已被再次修改。'));
    const records=data.history||[];
    if(!records.length)content.append(el('div','ke-empty','还没有人工修改记录。'));
    for(const row of records.slice(0,50)){
      const item=el('div','ke-history-row');item.append(el('strong','',({entity:'实体 · ',triple:'关系 · ',delete_triple:'删除关系 · '}[row.kind]||'')+(row.label||({entity:'编辑实体',triple:'编辑关系',delete_triple:'删除关系'}[row.kind]||'知识修改'))));
      item.append(el('small','',(row.created_at||'')+(row.undone?' · 已撤销':'')));
      for(const change of row.changes||[])item.append(el('p','ke-field-help',change));
      if(row.can_undo){const button=el('button','','撤销此修改');button.type='button';button.onclick=async()=>{if(busy)return;await undoChange(row.id);showHistory();};item.append(button);}
      content.append(item);
    }
  }
  function empty(){selected=null;dirty=false;memoryDirty=false;byId('ke-delete').hidden=true;byId('ke-content').replaceChildren();const n=el('div','ke-empty');n.append(el('strong','','把知识整理得更清晰。'),el('p','','从左侧选择实体、论断或关系。知识修改可以撤销，个人记忆设置单独保存并记录变化。'));byId('ke-content').append(n);syncButtons();}
  async function open(target){if(dialog.open){guard(()=>resolveTarget(target));return;}lastFocus=document.activeElement;stopTour();dialog.showModal();feedback('正在读取知识库…');empty();try{await reload();renderList();feedback('');resolveTarget(target);byId('ke-search').focus();}catch(error){feedback('无法连接知识库：'+error.message+' 请确认本地 API 服务已启动。',true);}}
  function resolveTarget(target){if(!data)return;if(target?.entity||target?.relation){category="";article="";renderArticleFilters();}if(target?.entity){const row=data.entities.find(e=>e.name===target.entity||String(e.id)===String(target.entity));if(row){kind=row.type==='Claim'?'claims':'entities';updateTabs();byId('ke-search').value='';select(row);return;}}if(target?.relation){const r=target.relation;const row=data.triples.find(t=>r.id != null ? String(r.id)===String(t.id) : entityName(t.subject_id)===(r.s||r.subject)&&entityName(t.object_id)===(r.t||r.object)&&t.predicate===(r.predicate||r.p)&&(!r.source||r.source===t.source));if(row){kind='triples';updateTabs();byId('ke-search').value='';select(row);return;}}renderList();}
  function close(){dialog.close();lastFocus?.focus();}
  byId('ke-history').onclick=()=>guard(()=>{if(data)showHistory();});
  byId('ke-close').onclick=()=>guard(close);dialog.addEventListener('cancel',e=>{e.preventDefault();guard(close);});
  byId('ke-search').addEventListener('input',()=>{if(data)renderList();});
  for(const id of ['ke-category','ke-article'])byId(id).addEventListener('change',()=>{
    const value=byId(id).value;byId(id).value=id==='ke-category'?category:article;
    guard(()=>{if(id==='ke-category'){category=value;article='';}else article=value;renderArticleFilters();empty();if(data)renderList();});
  });
  for(const id of ['ke-memory-scope','ke-memory-review-filter'])byId(id).addEventListener('change',()=>{if(data)renderList();});
  dialog.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>guard(()=>{kind=b.dataset.kind;updateTabs();empty();if(data)renderList();}));
  byId('ke-reset').onclick=()=>{if(selected&&!busy)guard(()=>{select(selected);feedback('已重置为上次保存的内容。');});};
  byId('ke-delete').onclick=()=>{if(!selected||busy)return;byId('ke-confirm')?.remove();const box=el('div','ke-confirm');box.id='ke-confirm';box.setAttribute('role','alertdialog');box.setAttribute('aria-label','确认删除关系');box.append(el('p','','确定删除「'+tripleTitle(selected)+'」？两个实体会保留。删除后可以撤销。'));const cancel=el('button','','保留关系'), confirm=el('button','ke-danger','确认删除');cancel.onclick=()=>box.remove();confirm.onclick=async()=>{if(busy)return;setBusy(true);try{const result=await request('/api/editor/triples/'+encodeURIComponent(selected.id)+'/delete',{revision:selected.revision});await complete(result,'关系已删除，实体仍然保留。');}catch(error){feedback(error.message,true);}finally{setBusy(false);}};box.append(cancel,confirm);byId('ke-content').append(box);box.scrollIntoView({block:'nearest'});cancel.focus();};
  window.addEventListener('beforeunload',event=>{if(dirty||memoryDirty||busy){event.preventDefault();event.returnValue='';}});
  dialog.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='s'){event.preventDefault();byId(event.target.closest('#ke-memory-form')?'ke-memory-form':'ke-form')?.requestSubmit();}});
  byId('editor-open')?.addEventListener('click',()=>open());
  window.KnowledgeEditor={open,openEntity:name=>open({entity:name}),openRelation:relation=>open({relation})};
})();
