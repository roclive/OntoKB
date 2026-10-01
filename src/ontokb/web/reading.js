const $ = id => document.getElementById(id);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const colors = {Organization:'#899a69',Person:'#c4936e',DefinedTerm:'#839c9b',SoftwareApplication:'#a79abb',Claim:'#b5a475',VideoObject:'#aaadb0',Book:'#a68b75',Thing:'#a8aaa0'};
const color = t => colors[t] || (TYPE_COLORS[t]||FALLBACK)[0];
const edgeKey = (s,p,t) => JSON.stringify([s,p,t]);
let nodes=[],links=[],sim=null,svg=null,g=null,node=null,link=null,edgeHit=null,edgeLabel=null,zoom=null;
let currentDoc=null,stepIndex=0,playing=false,timer=null,mode='reading',activeIds=new Set(),activeKeys=new Set();
let articleBusy=false;
const box=$('graph'), layerFilter=$('layer-filter'), typeFilter=$('type-filter'), info=$('info');
function stopTour(){playing=false;clearTimeout(timer);timer=null;if(svg)svg.interrupt();$('tour-play').textContent='▶ 开始漫游';}
// A graph edge can represent several source records. Always resolve its identity
// before editing, and let the reader choose when more than one source matches.
const graphMenu=document.createElement('div');graphMenu.id='graph-context-menu';graphMenu.className='graph-context-menu';graphMenu.hidden=true;graphMenu.setAttribute('role','menu');graphMenu.setAttribute('aria-label','编辑知识');document.body.append(graphMenu);
let menuOrigin=null,menuVersion=0,menuPoint={x:0,y:0};
function closeGraphMenu(restore=false){menuVersion++;graphMenu.hidden=true;if(menuOrigin?.hasAttribute('aria-haspopup'))menuOrigin.setAttribute('aria-expanded','false');if(restore&&menuOrigin?.isConnected)menuOrigin.focus();}
function positionGraphMenu(){const rect=graphMenu.getBoundingClientRect();graphMenu.style.left=Math.max(8,Math.min(menuPoint.x,innerWidth-rect.width-8))+'px';graphMenu.style.top=Math.max(8,Math.min(menuPoint.y,innerHeight-rect.height-8))+'px';}
function menuMessage(text){const message=document.createElement('div');message.className='graph-menu-note';message.setAttribute('role','status');message.textContent=text;graphMenu.append(message);}
function menuAction(label,action){const button=document.createElement('button');button.type='button';button.setAttribute('role','menuitem');button.textContent=label;button.onclick=()=>{closeGraphMenu(true);action();};graphMenu.append(button);return button;}
function beginGraphMenu(event){event.preventDefault();event.stopPropagation();stopTour();closeGraphMenu();menuOrigin=event.currentTarget;if(menuOrigin.hasAttribute('aria-haspopup'))menuOrigin.setAttribute('aria-expanded','true');const rect=menuOrigin.getBoundingClientRect();menuPoint=event.type==='keydown'||(!event.clientX&&!event.clientY)?{x:rect.left+rect.width/2,y:rect.top+rect.height/2}:{x:event.clientX,y:event.clientY};graphMenu.replaceChildren();graphMenu.hidden=false;return menuVersion;}
function moreMenuButton(label,action){const button=document.createElement('button');button.type='button';button.className='graph-more';button.textContent='⋯';button.setAttribute('aria-label',label+'：更多操作');button.title=label+'：更多操作 / 编辑知识';button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');button.onclick=action;return button;}
function contextKey(event){return event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10');}
const memoryInclusions=new Set();
async function includeEntityMemory(n){
  if(memoryInclusions.has(n.id))return;
  memoryInclusions.add(n.id);info.setAttribute('role','status');info.textContent='正在纳入个人记忆：'+n.id;
  try{
    const response=await fetch(apiUrl('/api/memory',{}));
    if(!response.ok)throw new Error('无法读取个人记忆，请稍后重试。');
    const data=await response.json();
    const row=(data.records||[]).find(r=>r.current&&['entity','claim'].includes(r.snapshot.kind)&&r.snapshot.title===n.id);
    if(!row)throw new Error('该实体已变更或删除，请刷新图谱后重试。');
    const saved=await fetch(apiUrl('/api/memory/review',{}),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:row.key,revision:row.revision,reviewed:true,included:true,stance:row.stance,note:row.note,source_id:''})});
    const result=await saved.json();
    if(!saved.ok)throw new Error(result.error||'保存失败，请重试。');
    info.textContent=n.id+' · 已审核，已纳入个人记忆并保存。';
  }catch(error){info.textContent=n.id+' · 纳入个人记忆失败：'+error.message;}
  finally{memoryInclusions.delete(n.id);}
}
function entityContextMenu(event,n){beginGraphMenu(event);menuMessage(n.id);menuAction('纳入个人记忆',()=>includeEntityMemory(n)).disabled=memoryInclusions.has(n.id);menuAction(n.type==='Claim'?'编辑论断 / 个人记忆':'编辑实体 / 个人记忆',()=>window.KnowledgeEditor?.openEntity(n.id));positionGraphMenu();graphMenu.querySelector('button:not(:disabled)').focus();}
async function relationContextMenu(event,relation){
  const version=beginGraphMenu(event);const s=relation.s||relation.subject||relation.source?.id,t=relation.t||relation.object||relation.target?.id,p=relation.predicate||relation.p;
  menuMessage(s+' → '+p+' → '+t);menuMessage('正在查找来源…');positionGraphMenu();graphMenu.tabIndex=-1;graphMenu.focus();
  try{
    const response=await fetch(apiUrl('/api/editor',{}));if(!response.ok)throw new Error('无法读取关系，请确认本地服务已启动。');const data=await response.json();if(version!==menuVersion)return;
    const names=new Map((data.entities||[]).map(n=>[String(n.id),n.name]));
    const candidates=(data.triples||[]).filter(r=>(relation.id==null||String(r.id)===String(relation.id))&&(r.subject||names.get(String(r.subject_id)))===s&&(r.object||names.get(String(r.object_id)))===t&&r.predicate===p&&(typeof relation.source!=='string'||r.source===relation.source));
    graphMenu.replaceChildren();menuMessage(s+' → '+p+' → '+t);
    if(!candidates.length)menuMessage('这条关系已变更或删除，请刷新图谱。');
    else if(candidates.length===1)menuAction('编辑关系 / 个人记忆',()=>window.KnowledgeEditor?.openRelation({id:candidates[0].id}));
    else{menuMessage('这条连接来自多份资料，请选择要编辑的来源：');candidates.forEach(r=>{const source=(data.sources||[]).find(d=>String(d.id)===String(r.source));menuAction((source?.title||r.source||'未记录来源')+' · #'+r.id,()=>window.KnowledgeEditor?.openRelation({id:r.id}));});}
  }catch(error){if(version!==menuVersion)return;graphMenu.replaceChildren();menuMessage(error.message);}
  positionGraphMenu();graphMenu.querySelector('button')?.focus();
}
document.addEventListener('pointerdown',event=>{if(!graphMenu.hidden&&!graphMenu.contains(event.target))closeGraphMenu();});
document.addEventListener('keydown',event=>{if(graphMenu.hidden)return;if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeGraphMenu(true);}else if(event.key==='Tab')closeGraphMenu();},true);
graphMenu.addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;event.preventDefault();const items=[...graphMenu.querySelectorAll('button')];if(!items.length)return;const index=items.indexOf(document.activeElement);items[event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();});
window.addEventListener('resize',()=>closeGraphMenu());document.addEventListener('scroll',event=>{if(!graphMenu.contains(event.target))closeGraphMenu();},true);
function schedule(){clearTimeout(timer);timer=setTimeout(()=>{if(!playing)return;if(stepIndex+1>=currentDoc.steps.length){stopTour();$('tour-play').textContent='↻ 再次漫游';return;}selectStep(stepIndex+1,true);schedule();},Number($('tour-speed').value));}
function renderGraph(){
  if(!window.d3){box.innerHTML='<div class="graph-error">图谱组件未加载。请检查网络后刷新；摘要仍可正常阅读。</div>';return;}
  closeGraphMenu();if(sim)sim.stop();box.replaceChildren();
  nodes=DATA.nodes.map(n=>({...n}));links=DATA.edges.map(e=>({source:e.s,target:e.t,p:e.p}));
  const degree={};links.forEach(e=>{degree[e.source]=(degree[e.source]||0)+1;degree[e.target]=(degree[e.target]||0)+1;});nodes.forEach(n=>n.degree=degree[n.id]||0);
  const W=box.clientWidth||800,H=box.clientHeight||500;
  svg=d3.select(box).append('svg').attr('viewBox',[0,0,W,H]).attr('aria-label','交互知识图谱');g=svg.append('g');
  zoom=d3.zoom().scaleExtent([.25,3]).on('zoom',e=>g.attr('transform',e.transform));svg.call(zoom).on('dblclick.zoom',null);
  svg.on('dblclick',()=>{stopTour();reset();fitView();});
  link=g.append('g').selectAll('line').data(links).join('line').attr('class','graph-link');
  edgeHit=g.append('g').selectAll('line').data(links).join('line').attr('class','graph-edge-hit').attr('tabindex',0).attr('role','button').attr('aria-label',e=>e.source+' → '+e.p+' → '+e.target+'，点击打开更多操作').attr('aria-haspopup','menu').attr('aria-expanded','false').on('click',(event,e)=>{if(!event.defaultPrevented)relationContextMenu(event,e);}).on('contextmenu',relationContextMenu).on('keydown',(event,e)=>{if(contextKey(event)||event.key==='Enter'||event.key===' ')relationContextMenu(event,e);});
  edgeLabel=g.append('g').selectAll('text').data(links).join('text').attr('class','edge-label').attr('text-anchor','middle').text(e=>e.p).style('opacity',0);
  node=g.append('g').selectAll('g').data(nodes).join('g').attr('class','graph-node').attr('tabindex',0).attr('role','button').attr('aria-label',n=>n.id+'，'+(TYPE_CN[n.type]||n.type));
  node.append('circle').attr('class','halo').attr('r',n=>size(n)+8);
  node.append('circle').attr('r',size).attr('fill',n=>color(n.type)).attr('stroke','#fffef9').attr('stroke-width',2);
  node.append('text').attr('text-anchor','middle').attr('dy',n=>size(n)+18).text(n=>n.id.length>17?n.id.slice(0,16)+'…':n.id);
  node.append('title').text(n=>n.id+' · '+(TYPE_CN[n.type]||n.type));
  node.on('click',(e,n)=>{stopTour();highlight(n.id);}).on('contextmenu',entityContextMenu).on('keydown',(e,n)=>{if(contextKey(e))entityContextMenu(e,n);else if(e.key==='Enter'){stopTour();highlight(n.id);}});
  node.call(d3.drag().on('start',(e,n)=>{stopTour();svg.interrupt();n.fx=n.x;n.fy=n.y;}).on('drag',(e,n)=>{n.x=e.x;n.y=e.y;n.fx=e.x;n.fy=e.y;tick();}).on('end',(e,n)=>{n.fx=null;n.fy=null;}));
  sim=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(n=>n.id).distance(110).strength(.18)).force('charge',d3.forceManyBody().strength(-240)).force('center',d3.forceCenter(W/2,H/2)).force('collide',d3.forceCollide(34)).stop();
  for(let i=0;i<180;i++)sim.tick();tick();
  function tick(){[link,edgeHit].forEach(lines=>lines.attr('x1',e=>e.source.x).attr('y1',e=>e.source.y).attr('x2',e=>e.target.x).attr('y2',e=>e.target.y));node.attr('transform',n=>'translate('+n.x+','+n.y+')');edgeLabel.attr('x',e=>(e.source.x+e.target.x)/2).attr('y',e=>(e.source.y+e.target.y)/2-7);}
  sim.on('tick',tick);
  const types=[...new Set(nodes.map(n=>n.type))];typeFilter.replaceChildren(new Option('全部类型','all'));$('legend').replaceChildren();
  types.forEach(t=>{typeFilter.add(new Option(TYPE_CN[t]||t,t));const b=document.createElement('button');const dot=document.createElement('i');dot.style.background=color(t);b.append(dot,document.createTextNode(TYPE_CN[t]||t));b.onclick=()=>{typeFilter.value=t;layerFilter.value='all';applyFilters();};$('legend').append(b);});
}
function size(n){return Math.min(7+Math.sqrt(n.degree)*1.8,17);}
function focusCamera(ids,animated=true){
  if(!svg)return;const selected=nodes.filter(n=>ids.has(n.id));if(!selected.length)return;
  const W=box.clientWidth||800,H=box.clientHeight||500;
  const xs=selected.map(n=>n.x),ys=selected.map(n=>n.y),cx=(Math.min(...xs)+Math.max(...xs))/2,cy=(Math.min(...ys)+Math.max(...ys))/2;
  const scale=Math.max(.25,Math.min(selected.length===1?1.45:1.15,(W-110)/(Math.max(...xs)-Math.min(...xs)+150),(H-70)/(Math.max(...ys)-Math.min(...ys)+120)));
  svg.interrupt();const target=d3.zoomIdentity.translate(W/2-scale*cx,H/2-scale*cy).scale(scale);
  if(animated&&!reducedMotion.matches)svg.transition().duration(1200).ease(d3.easeCubicInOut).call(zoom.transform,target);else svg.call(zoom.transform,target);
}
function paint(ids,keys){
  activeIds=ids;activeKeys=keys;if(!node)return;
  node.style('display',null).style('opacity',n=>ids.has(n.id)?1:.09).classed('active',n=>ids.has(n.id));
  link.style('display',null).style('opacity',e=>keys.has(edgeKey(e.source.id,e.p,e.target.id))?.9:.035).classed('active',e=>keys.has(edgeKey(e.source.id,e.p,e.target.id)));
  edgeHit.style('display',null);
  edgeLabel.style('opacity',e=>keys.has(edgeKey(e.source.id,e.p,e.target.id))?1:0);
}
function fitView(){if(mode==='reading'&&activeIds.size)focusCamera(activeIds);else focusCamera(new Set(nodes.filter(n=>mode!=='explore'||visibleType(n)).map(n=>n.id)));}
function reset(){
  if(!node)return;activeIds=new Set();activeKeys=new Set();node.classed('active',false).style('opacity',1);link.classed('active',false).style('opacity',.3);edgeLabel.style('opacity',0);info.textContent='点击节点后用 ⋯ 编辑，点击关系打开菜单；拖动节点，滚轮缩放。';
}
function visibleType(n){const l=layerFilter.value;return(typeFilter.value==='all'||n.type===typeFilter.value)&&(l==='all'||l==='claims'&&n.type==='Claim'||l==='documents'&&['VideoObject','Article','Book','CreativeWork','MediaObject'].includes(n.type)||l==='core'&&!['Claim','VideoObject','Article','Book','CreativeWork','MediaObject'].includes(n.type));}
function applyFilters(){
  stopTour();mode='explore';setNav();reset();if(!node)return;
  const ids=new Set(nodes.filter(visibleType).map(n=>n.id));node.style('display',n=>ids.has(n.id)?null:'none');link.style('display',e=>ids.has(e.source.id)&&ids.has(e.target.id)?null:'none');edgeHit.style('display',e=>ids.has(e.source.id)&&ids.has(e.target.id)?null:'none');edgeLabel.style('opacity',0);$('canvas-title').textContent='从一个实体，探索更多。';$('stat').textContent=ids.size+' / '+nodes.length+' 节点';fitView();
}
function highlight(id){
  const nearby=links.filter(e=>e.source.id===id||e.target.id===id);const ids=new Set([id]);nearby.forEach(e=>{ids.add(e.source.id);ids.add(e.target.id);});paint(ids,new Set(nearby.map(e=>edgeKey(e.source.id,e.p,e.target.id))));focusCamera(ids);info.textContent=id+' · '+nearby.length+' 条已有关系';const selectedNode=nodes.find(n=>n.id===id)||{id};info.append(moreMenuButton(selectedNode.type==='Claim'?'论断':'实体',event=>entityContextMenu(event,selectedNode)));
}
function highlightRelation(e){stopTour();const s=e.subject||e.s,t=e.object||e.t,p=e.predicate||e.p;paint(new Set([s,t]),new Set([edgeKey(s,p,t)]));focusCamera(new Set([s,t]));info.textContent=s+' → '+p+' → '+t;info.append(moreMenuButton('关系',event=>relationContextMenu(event,e)));}
function setNav(){$('reading-nav').classList.toggle('active',mode==='reading');$('explore-nav').classList.toggle('active',mode==='explore');}
function selectStep(index,automatic=false){
  if(!automatic)stopTour();if(!currentDoc||!currentDoc.steps.length)return;
  mode='reading';setNav();stepIndex=Math.max(0,Math.min(index,currentDoc.steps.length-1));const step=currentDoc.steps[stepIndex];
  $('summary-steps').querySelectorAll('button').forEach((b,i)=>{b.classList.toggle('active',i===stepIndex);b.setAttribute('aria-current',i===stepIndex?'step':'false');});
  const card=$('summary-steps').children[stepIndex];if(card){$('reading-body').scrollTo({top:Math.max(0,card.offsetTop-35),behavior:reducedMotion.matches?'instant':'smooth'});}
  const ids=new Set([...step.entities,...step.neighbors]);paint(ids,new Set(step.edges.map(e=>edgeKey(e.s,e.predicate,e.t))));
  if(ids.size)focusCamera(ids);else if(svg)svg.interrupt();
  $('canvas-title').textContent=step.entities.length?step.entities.slice(0,3).join(' · '):'这一段，留给思考。';
  $('tour-step').textContent=String(stepIndex+1).padStart(2,'0')+' / '+String(currentDoc.steps.length).padStart(2,'0');
  $('tour-title').textContent=step.entities.length?step.entities.slice(0,3).join(' → '):'未匹配到已记录实体';
  $('tour-note').textContent=ids.size?step.entities.length+' 个摘要实体 · '+step.neighbors.length+' 个一跳邻居 · '+step.edges.length+' 条来源内关系':'当前段落没有名称／别名匹配，不补造节点或关系。';
  $('tour-progress').style.width=((stepIndex+1)/currentDoc.steps.length*100)+'%';
  $('stat').textContent=nodes.length+' 节点';info.textContent='点击节点后用 ⋯ 编辑，点击关系打开菜单。';$('tour-prev').disabled=stepIndex===0;$('tour-next').disabled=stepIndex===currentDoc.steps.length-1;
  renderEvidence(step);$('evidence-open').disabled=!step.edges.length;
}
function renderEvidence(step){$('evidence-list').replaceChildren();if(!step.edges.length)$('evidence-panel').hidden=true;step.edges.forEach(e=>{const row=document.createElement('div');row.className='evidence-row';row.tabIndex=0;row.setAttribute('aria-label',e.s+' → '+e.predicate+' → '+e.t+'，使用更多操作编辑关系');row.oncontextmenu=event=>relationContextMenu(event,e);row.onkeydown=event=>{if(contextKey(event))relationContextMenu(event,e);};const title=document.createElement('strong');title.textContent=e.s+' → '+e.predicate+' → '+e.t;const p=document.createElement('p');p.textContent=e.evidence||'此关系没有保存逐字证据。';const edit=moreMenuButton('关系',event=>relationContextMenu(event,e));row.append(title,edit,p);$('evidence-list').append(row);});}
function chooseDocument(id){
  stopTour();currentDoc=(DATA.library||[]).find(d=>d.id===id)||null;stepIndex=0;$('evidence-panel').hidden=true;
  $('summary-steps').replaceChildren();$('key-points').replaceChildren();
  $('document-title').textContent=currentDoc?currentDoc.title:'从一篇文章开始';$('source-tag').textContent=currentDoc?(currentDoc.kind==='video'?'视频笔记':'文章笔记')+' · '+currentDoc.source:'你的阅读空间';
  $('document-categories').replaceChildren();
  (currentDoc?categoriesOf(currentDoc):[]).forEach(category=>{
    const tag=document.createElement('span');tag.className='category-tag';tag.textContent=category;
    $('document-categories').append(tag);
  });
  if(currentDoc){
    ['历史','科技','时政'].forEach(category=>{
      const button=document.createElement('button');button.type='button';button.className='category-assign';
      button.textContent=category;button.title='将当前文章分类为'+category;
      button.setAttribute('aria-label','将当前文章分类为'+category);
      button.setAttribute('aria-pressed',String(categoriesOf(currentDoc).includes(category)));
      button.disabled=categorySaving;button.onclick=()=>assignCategory(category);
      $('document-categories').append(button);
    });
  }
  $('document-title').title=currentDoc?.title||'';
  $('doc-nodes').textContent=currentDoc?.entity_count||0;$('doc-links').textContent=currentDoc?.relation_count||0;$('doc-steps').textContent=currentDoc?.steps.length||0;
  const url=currentDoc?.url||'';$('source-link').hidden=!/^https?:\/\//i.test(url);if(!$('source-link').hidden)$('source-link').href=url;
  const steps=currentDoc?.steps||[];
  steps.forEach((step,i)=>{const b=document.createElement('button');b.className='summary-step';const num=document.createElement('span');num.className='step-num';num.textContent=String(i+1).padStart(2,'0');const body=document.createElement('span');body.textContent=step.text;const matches=document.createElement('span');matches.className='matches';matches.textContent=step.entities.length?'↗ '+step.entities.slice(0,3).join(' · '):'○ 暂无实体匹配';b.append(num,body,matches);b.onclick=()=>selectStep(i);$('summary-steps').append(b);});
  if(!steps.length){const p=document.createElement('p');p.className='empty';p.textContent=currentDoc?'这篇资料还没有摘要。':'点击「新建摘要」，粘贴文章正文，开始建立你的知识连接。';$('summary-steps').append(p);reset();$('tour-step').textContent='00 / 00';$('tour-progress').style.width='0';}
  if(!steps.length){$('tour-note').textContent='添加文章后，即可沿摘要漫游图谱。';$('tour-title').textContent='摘要漫游';$('evidence-open').disabled=true;$('stat').textContent=nodes.length+' 节点';}
  (currentDoc?.key_points||[]).forEach(text=>{const p=document.createElement('div');p.className='key-point';p.textContent=text;$('key-points').append(p);});
  ['tour-play','tour-prev','tour-next'].forEach(id=>$(id).disabled=!steps.length);
  if(steps.length)selectStep(0);else fitView();$('reading-body').scrollTop=0;
}
let selectedCategory='全部',categorySaving=false;
async function assignCategory(category){
  if(!currentDoc||categorySaving)return;
  const id=currentDoc.id;categorySaving=true;
  document.querySelectorAll('.category-assign').forEach(button=>button.disabled=true);
  const status=document.createElement('span');status.className='category-status';status.setAttribute('role','status');
  status.textContent='正在保存…';$('document-categories').append(status);
  try{
    const response=await fetch(apiUrl('/api/reading/category',{}),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_id:id,category})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'保存失败');
    const doc=(DATA.library||[]).find(d=>d.id===id);if(doc)doc.categories=result.categories;
    categorySaving=false;renderLibrary(currentDoc?.id);
    if(currentDoc?.id===id){status.textContent='已分类为'+category;$('document-categories').append(status);}
  }catch(error){status.textContent='分类未保存：'+error.message;if(currentDoc?.id===id)$('document-categories').append(status);}
  finally{categorySaving=false;document.querySelectorAll('.category-assign').forEach(button=>button.disabled=false);}
}
function categoriesOf(doc){return doc.categories?.length?doc.categories:['未分类'];}
function renderLibrary(preferId){
  const library=DATA.library||[];
  const categories=[...new Set(library.flatMap(categoriesOf))];
  if(!categories.includes(selectedCategory))selectedCategory='全部';
  const requested=library.find(d=>d.id===preferId);
  if(requested&&selectedCategory!=='全部'&&!categoriesOf(requested).includes(selectedCategory))selectedCategory='全部';
  $('category-filters').replaceChildren();
  ['全部',...categories].forEach(category=>{
    const count=category==='全部'?library.length:library.filter(d=>categoriesOf(d).includes(category)).length;
    const button=document.createElement('button');button.type='button';
    button.className='category-chip';button.textContent=category+' '+count;
    button.setAttribute('aria-pressed',String(category===selectedCategory));
    button.onclick=()=>{selectedCategory=category;renderLibrary();};
    $('category-filters').append(button);
  });
  const visible=library.filter(d=>selectedCategory==='全部'||categoriesOf(d).includes(selectedCategory));
  $('library-count').textContent=(selectedCategory==='全部'?library.length:visible.length+' / '+library.length)+' 篇资料';
  $('document-select').replaceChildren();
  visible.forEach(d=>$('document-select').add(new Option('【'+categoriesOf(d).join(' · ')+'】'+d.title,d.id)));
  if(!visible.length)$('document-select').add(new Option('还没有资料',''));
  $('document-select').disabled=!visible.length;
  const preferred=preferId||currentDoc?.id;
  const id=visible.some(d=>d.id===preferred)?preferred:visible[0]?.id;
  $('document-select').value=id||'';chooseDocument(id);
}
$('document-select').onchange=e=>chooseDocument(e.target.value);
$('tour-play').onclick=()=>{if(playing)return stopTour();if(!currentDoc?.steps.length)return;if(stepIndex===currentDoc.steps.length-1)selectStep(0);mode='reading';selectStep(stepIndex,true);playing=true;$('tour-play').textContent='Ⅱ 暂停漫游';schedule();};
$('tour-prev').onclick=()=>selectStep(stepIndex-1);$('tour-next').onclick=()=>selectStep(stepIndex+1);$('tour-speed').onchange=()=>{if(playing)schedule();};
$('reading-nav').onclick=()=>selectStep(stepIndex);$('explore-nav').onclick=()=>{layerFilter.value='all';typeFilter.value='all';applyFilters();};
$('fit-view').onclick=fitView;$('filter-toggle').onclick=()=>$('filters').classList.toggle('open');layerFilter.onchange=applyFilters;typeFilter.onchange=applyFilters;
$('search').oninput=e=>{stopTour();const q=e.target.value.trim().toLowerCase();if(!q){if(mode==='reading')selectStep(stepIndex);else applyFilters();return;}const ids=new Set(nodes.filter(n=>n.id.toLowerCase().includes(q)).map(n=>n.id));paint(ids,new Set());if(ids.size)focusCamera(ids);info.textContent='匹配 '+ids.size+' 个实体';};
$('evidence-open').onclick=()=>$('evidence-panel').hidden=!$('evidence-panel').hidden;$('evidence-close').onclick=()=>$('evidence-panel').hidden=true;
$('assistant-open').onclick=()=>{stopTour();$('query-panel').hidden=false;};$('assistant-close').onclick=()=>$('query-panel').hidden=true;
$('article-open').onclick=()=>{stopTour();$('article-dialog').showModal();};$('article-close').onclick=()=>$('article-dialog').close();
$('chat-open').onclick=()=>{
  stopTour();
  $('query-panel').hidden=false;
  document.querySelector('.panel-tab[data-panel="chat-view"]').click();
  $('chat-input').focus();
};
$('article-dialog').addEventListener('close',()=>{if(articleBusy)$('article-status').textContent='正在后台生成，请勿重复提交。';});
const resizer=$('workspace-resizer');const savedPanelWidth=Number(localStorage.getItem('graphPanelWidth'));if(savedPanelWidth>=300)$('query-panel').style.setProperty('--panel-width',savedPanelWidth+'px');
function resizePanel(width){const size=Math.max(300,Math.min(innerWidth*.9,width));$('query-panel').style.setProperty('--panel-width',size+'px');localStorage.setItem('graphPanelWidth',String(size));}
resizer.onpointerdown=e=>resizer.setPointerCapture(e.pointerId);resizer.onpointermove=e=>{if(resizer.hasPointerCapture(e.pointerId))resizePanel(innerWidth-e.clientX);};resizer.onpointerup=e=>resizer.releasePointerCapture(e.pointerId);resizer.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key))resizePanel($('query-panel').clientWidth+(e.key==='ArrowLeft'?20:-20));};
new ResizeObserver(()=>{if(svg){svg.attr('viewBox',[0,0,box.clientWidth,box.clientHeight]);focusCamera(activeIds.size?activeIds:new Set(nodes.map(n=>n.id)),false);}}).observe(box);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopTour();});
renderGraph();renderLibrary();
async function refreshReading(contentId){const response=await fetch(apiUrl('/api/reading',{}));if(!response.ok)throw new Error('刷新资料失败，请刷新页面查看。');stopTour();DATA=await response.json();renderGraph();renderLibrary(contentId);}
$('article-form').addEventListener('submit',async e=>{e.preventDefault();if(articleBusy)return;articleBusy=true;$('article-submit').disabled=true;$('article-status').textContent='正在生成摘要和提取知识… 完成后会自动打开新资料。';try{const response=await fetch(apiUrl('/api/articles',{}),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('article-title').value,text:$('article-text').value,url:$('article-url').value})});const result=await response.json();if(!response.ok)throw new Error(result.error||'生成失败');const fresh=await fetch(apiUrl('/api/reading',{}));if(!fresh.ok)throw new Error('已保存，但刷新资料失败，请刷新页面查看。');stopTour();DATA=await fresh.json();renderGraph();renderLibrary(result.content_id);$('article-form').reset();$('article-status').textContent='';$('article-dialog').close();}catch(error){$('article-status').textContent='未能完成：'+error.message+' 正文已保留，可稍后重试。';}finally{articleBusy=false;$('article-submit').disabled=false;}});
