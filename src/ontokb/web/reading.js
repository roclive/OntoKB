const $ = id => document.getElementById(id);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const colors = {Organization:'#899a69',Person:'#c4936e',DefinedTerm:'#839c9b',SoftwareApplication:'#a79abb',Claim:'#b5a475',VideoObject:'#aaadb0',Book:'#a68b75',Thing:'#a8aaa0'};
const color = t => colors[t] || (TYPE_COLORS[t]||FALLBACK)[0];
const edgeKey = (s,p,t) => JSON.stringify([s,p,t]);
let nodes=[],links=[],sim=null,svg=null,g=null,node=null,link=null,edgeLabel=null,zoom=null;
let currentDoc=null,stepIndex=0,playing=false,timer=null,mode='reading',activeIds=new Set(),activeKeys=new Set();
let articleBusy=false;
const box=$('graph'), layerFilter=$('layer-filter'), typeFilter=$('type-filter'), info=$('info');
function stopTour(){playing=false;clearTimeout(timer);timer=null;if(svg)svg.interrupt();$('tour-play').textContent='▶ 开始漫游';}
function schedule(){clearTimeout(timer);timer=setTimeout(()=>{if(!playing)return;if(stepIndex+1>=currentDoc.steps.length){stopTour();$('tour-play').textContent='↻ 再次漫游';return;}selectStep(stepIndex+1,true);schedule();},Number($('tour-speed').value));}
function renderGraph(){
  if(!window.d3){box.innerHTML='<div class="graph-error">图谱组件未加载。请检查网络后刷新；摘要仍可正常阅读。</div>';return;}
  if(sim)sim.stop();box.replaceChildren();
  nodes=DATA.nodes.map(n=>({...n}));links=DATA.edges.map(e=>({source:e.s,target:e.t,p:e.p}));
  const degree={};links.forEach(e=>{degree[e.source]=(degree[e.source]||0)+1;degree[e.target]=(degree[e.target]||0)+1;});nodes.forEach(n=>n.degree=degree[n.id]||0);
  const W=box.clientWidth||800,H=box.clientHeight||500;
  svg=d3.select(box).append('svg').attr('viewBox',[0,0,W,H]).attr('aria-label','交互知识图谱');g=svg.append('g');
  zoom=d3.zoom().scaleExtent([.25,3]).on('zoom',e=>g.attr('transform',e.transform));svg.call(zoom).on('dblclick.zoom',null);
  svg.on('dblclick',()=>{stopTour();reset();fitView();});
  link=g.append('g').selectAll('line').data(links).join('line').attr('class','graph-link');
  edgeLabel=g.append('g').selectAll('text').data(links).join('text').attr('class','edge-label').attr('text-anchor','middle').text(e=>e.p).style('opacity',0);
  node=g.append('g').selectAll('g').data(nodes).join('g').attr('class','graph-node').attr('tabindex',0).attr('role','button').attr('aria-label',n=>n.id+'，'+(TYPE_CN[n.type]||n.type));
  node.append('circle').attr('class','halo').attr('r',n=>size(n)+8);
  node.append('circle').attr('r',size).attr('fill',n=>color(n.type)).attr('stroke','#fffef9').attr('stroke-width',2);
  node.append('text').attr('text-anchor','middle').attr('dy',n=>size(n)+18).text(n=>n.id.length>17?n.id.slice(0,16)+'…':n.id);
  node.append('title').text(n=>n.id+' · '+(TYPE_CN[n.type]||n.type));
  node.on('click',(e,n)=>{stopTour();highlight(n.id);}).on('keydown',(e,n)=>{if(e.key==='Enter'){stopTour();highlight(n.id);}});
  node.call(d3.drag().on('start',(e,n)=>{stopTour();svg.interrupt();n.fx=n.x;n.fy=n.y;}).on('drag',(e,n)=>{n.x=e.x;n.y=e.y;n.fx=e.x;n.fy=e.y;tick();}).on('end',(e,n)=>{n.fx=null;n.fy=null;}));
  sim=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(n=>n.id).distance(110).strength(.18)).force('charge',d3.forceManyBody().strength(-240)).force('center',d3.forceCenter(W/2,H/2)).force('collide',d3.forceCollide(34)).stop();
  for(let i=0;i<180;i++)sim.tick();tick();
  function tick(){link.attr('x1',e=>e.source.x).attr('y1',e=>e.source.y).attr('x2',e=>e.target.x).attr('y2',e=>e.target.y);node.attr('transform',n=>'translate('+n.x+','+n.y+')');edgeLabel.attr('x',e=>(e.source.x+e.target.x)/2).attr('y',e=>(e.source.y+e.target.y)/2-7);}
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
  edgeLabel.style('opacity',e=>keys.has(edgeKey(e.source.id,e.p,e.target.id))?1:0);
}
function fitView(){if(mode==='reading'&&activeIds.size)focusCamera(activeIds);else focusCamera(new Set(nodes.filter(n=>mode!=='explore'||visibleType(n)).map(n=>n.id)));}
function reset(){
  if(!node)return;activeIds=new Set();activeKeys=new Set();node.classed('active',false).style('opacity',1);link.classed('active',false).style('opacity',.3);edgeLabel.style('opacity',0);info.textContent='点击实体查看关联，拖动节点，滚轮缩放。';
}
function visibleType(n){const l=layerFilter.value;return(typeFilter.value==='all'||n.type===typeFilter.value)&&(l==='all'||l==='claims'&&n.type==='Claim'||l==='documents'&&['VideoObject','Article','Book','CreativeWork','MediaObject'].includes(n.type)||l==='core'&&!['Claim','VideoObject','Article','Book','CreativeWork','MediaObject'].includes(n.type));}
function applyFilters(){
  stopTour();mode='explore';setNav();reset();if(!node)return;
  const ids=new Set(nodes.filter(visibleType).map(n=>n.id));node.style('display',n=>ids.has(n.id)?null:'none');link.style('display',e=>ids.has(e.source.id)&&ids.has(e.target.id)?null:'none');edgeLabel.style('opacity',0);$('canvas-title').textContent='从一个实体，探索更多。';$('stat').textContent=ids.size+' / '+nodes.length+' 节点';fitView();
}
function highlight(id){
  const nearby=links.filter(e=>e.source.id===id||e.target.id===id);const ids=new Set([id]);nearby.forEach(e=>{ids.add(e.source.id);ids.add(e.target.id);});paint(ids,new Set(nearby.map(e=>edgeKey(e.source.id,e.p,e.target.id))));focusCamera(ids);info.textContent=id+' · '+nearby.length+' 条已有关系';
}
function highlightRelation(e){stopTour();const s=e.subject||e.s,t=e.object||e.t,p=e.predicate||e.p;paint(new Set([s,t]),new Set([edgeKey(s,p,t)]));focusCamera(new Set([s,t]));info.textContent=s+' → '+p+' → '+t;}
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
  $('stat').textContent=nodes.length+' 节点';info.textContent='';$('tour-prev').disabled=stepIndex===0;$('tour-next').disabled=stepIndex===currentDoc.steps.length-1;
  renderEvidence(step);$('evidence-open').disabled=!step.edges.length;
}
function renderEvidence(step){$('evidence-list').replaceChildren();if(!step.edges.length)$('evidence-panel').hidden=true;step.edges.forEach(e=>{const row=document.createElement('div');row.className='evidence-row';const title=document.createElement('strong');title.textContent=e.s+' → '+e.predicate+' → '+e.t;const p=document.createElement('p');p.textContent=e.evidence||'此关系没有保存逐字证据。';row.append(title,p);$('evidence-list').append(row);});}
function chooseDocument(id){
  stopTour();currentDoc=(DATA.library||[]).find(d=>d.id===id)||null;stepIndex=0;$('evidence-panel').hidden=true;
  $('summary-steps').replaceChildren();$('key-points').replaceChildren();
  $('document-title').textContent=currentDoc?currentDoc.title:'从一篇文章开始';$('source-tag').textContent=currentDoc?(currentDoc.kind==='video'?'视频笔记':'文章笔记')+' · '+currentDoc.source:'你的阅读空间';
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
function renderLibrary(preferId){const library=DATA.library||[];$('library-count').textContent=library.length+' 篇资料';$('document-select').replaceChildren();library.forEach(d=>$('document-select').add(new Option(d.title,d.id)));if(!library.length)$('document-select').add(new Option('还没有资料',''));const id=library.some(d=>d.id===preferId)?preferId:library[0]?.id;$('document-select').value=id||'';chooseDocument(id);}
$('document-select').onchange=e=>chooseDocument(e.target.value);
$('tour-play').onclick=()=>{if(playing)return stopTour();if(!currentDoc?.steps.length)return;if(stepIndex===currentDoc.steps.length-1)selectStep(0);mode='reading';selectStep(stepIndex,true);playing=true;$('tour-play').textContent='Ⅱ 暂停漫游';schedule();};
$('tour-prev').onclick=()=>selectStep(stepIndex-1);$('tour-next').onclick=()=>selectStep(stepIndex+1);$('tour-speed').onchange=()=>{if(playing)schedule();};
$('reading-nav').onclick=()=>selectStep(stepIndex);$('explore-nav').onclick=()=>{layerFilter.value='all';typeFilter.value='all';applyFilters();};
$('fit-view').onclick=fitView;$('filter-toggle').onclick=()=>$('filters').classList.toggle('open');layerFilter.onchange=applyFilters;typeFilter.onchange=applyFilters;
$('search').oninput=e=>{stopTour();const q=e.target.value.trim().toLowerCase();if(!q){if(mode==='reading')selectStep(stepIndex);else applyFilters();return;}const ids=new Set(nodes.filter(n=>n.id.toLowerCase().includes(q)).map(n=>n.id));paint(ids,new Set());if(ids.size)focusCamera(ids);info.textContent='匹配 '+ids.size+' 个实体';};
$('evidence-open').onclick=()=>$('evidence-panel').hidden=!$('evidence-panel').hidden;$('evidence-close').onclick=()=>$('evidence-panel').hidden=true;
$('assistant-open').onclick=()=>{stopTour();$('query-panel').hidden=false;};$('assistant-close').onclick=()=>$('query-panel').hidden=true;
$('article-open').onclick=()=>{stopTour();$('article-dialog').showModal();};$('article-close').onclick=()=>$('article-dialog').close();
$('article-dialog').addEventListener('close',()=>{if(articleBusy)$('article-status').textContent='正在后台生成，请勿重复提交。';});
const resizer=$('workspace-resizer');const savedPanelWidth=Number(localStorage.getItem('graphPanelWidth'));if(savedPanelWidth>=300)$('query-panel').style.setProperty('--panel-width',savedPanelWidth+'px');
function resizePanel(width){const size=Math.max(300,Math.min(innerWidth*.9,width));$('query-panel').style.setProperty('--panel-width',size+'px');localStorage.setItem('graphPanelWidth',String(size));}
resizer.onpointerdown=e=>resizer.setPointerCapture(e.pointerId);resizer.onpointermove=e=>{if(resizer.hasPointerCapture(e.pointerId))resizePanel(innerWidth-e.clientX);};resizer.onpointerup=e=>resizer.releasePointerCapture(e.pointerId);resizer.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key))resizePanel($('query-panel').clientWidth+(e.key==='ArrowLeft'?20:-20));};
new ResizeObserver(()=>{if(svg){svg.attr('viewBox',[0,0,box.clientWidth,box.clientHeight]);focusCamera(activeIds.size?activeIds:new Set(nodes.map(n=>n.id)),false);}}).observe(box);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopTour();});
renderGraph();renderLibrary();
async function refreshReading(contentId){const response=await fetch(apiUrl('/api/reading',{}));if(!response.ok)throw new Error('刷新资料失败，请刷新页面查看。');stopTour();DATA=await response.json();renderGraph();renderLibrary(contentId);}
$('article-form').addEventListener('submit',async e=>{e.preventDefault();if(articleBusy)return;articleBusy=true;$('article-submit').disabled=true;$('article-status').textContent='正在生成摘要和提取知识… 完成后会自动打开新资料。';try{const response=await fetch(apiUrl('/api/articles',{}),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('article-title').value,text:$('article-text').value,url:$('article-url').value})});const result=await response.json();if(!response.ok)throw new Error(result.error||'生成失败');const fresh=await fetch(apiUrl('/api/reading',{}));if(!fresh.ok)throw new Error('已保存，但刷新资料失败，请刷新页面查看。');stopTour();DATA=await fresh.json();renderGraph();renderLibrary(result.content_id);$('article-form').reset();$('article-status').textContent='';$('article-dialog').close();}catch(error){$('article-status').textContent='未能完成：'+error.message+' 正文已保留，可稍后重试。';}finally{articleBusy=false;$('article-submit').disabled=false;}});
