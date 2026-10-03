/* A short video edit and a longer screenshot/audio tour, both using original source audio. */
(()=>{
  const entry=document.createElement('div');entry.className='media-entry-options';
  entry.innerHTML='<button id="media-open" class="media-entry" type="button"><span class="media-entry-icon" aria-hidden="true">▷</span><span><strong>视频精剪</strong><small>完整短片 · 约 1–2 分钟</small></span></button><button id="media-audio-open" class="media-entry" type="button"><span class="media-entry-icon" aria-hidden="true">♫</span><span><strong>原声漫游</strong><small>截图配原声 · 约原视频 1/3</small></span></button>';
  document.querySelector('.doc-metrics').after(entry);
  const surface=document.createElement('div');surface.id='media-surface';
  surface.innerHTML=`<header class="media-head"><div><div class="eyebrow">WATCH · LISTEN · UNDERSTAND</div><h2 id="media-heading">多媒体摘要</h2><p id="media-method" class="media-method" hidden></p></div><button id="media-close" aria-label="关闭多媒体摘要，返回图谱">返回图谱</button></header>
    <div class="media-mode-bar" role="group" aria-label="摘要展示方式"><button id="media-mode-video" aria-pressed="true"><strong>视频精剪</strong><small>约 1–2 分钟 · 完整视频</small></button><button id="media-mode-audio" aria-pressed="false"><strong>原声漫游</strong><small>约原视频 1/3 · 截图配原声</small></button></div>
    <section id="media-status" class="media-status" role="status"><span class="media-status-icon" aria-hidden="true">◌</span><p id="media-message"></p><button id="media-retry" hidden>重新准备</button></section>
    <section id="media-video-player" hidden><div class="media-compilation-frame"><video id="media-compilation" controls playsinline preload="metadata" aria-label="完整视频精剪"></video></div><footer class="media-footer"><div class="media-video-footer"><div><strong>原视频画面与声音，连成一段短片</strong><p id="media-video-duration" class="media-method"></p></div><a id="media-video-download" class="media-download" download>↓ 下载完整 MP4</a></div><p id="media-video-notice" class="media-notice" aria-live="polite">点击视频播放键，观看完整精剪。</p></footer></section>
    <section id="media-player" hidden><div id="media-layout" class="media-layout"><div class="media-frame"><img id="media-image" alt="当前原声片段的视频截图"><span class="media-image-missing">此片段截图暂不可用，仍可收听原声。</span><audio id="media-audio" preload="metadata"></audio></div><div class="media-caption"><span id="media-counter" class="media-counter"></span><h3 id="media-title"></h3><span class="media-text-label">字幕 · 原视频声音</span><p id="media-text"></p><a id="media-source" target="_blank" rel="noopener noreferrer">回到原视频 ↗</a></div></div><footer class="media-footer"><input id="media-progress" class="media-timeline" type="range" min="0" max="100" step="0.1" value="0" aria-label="拖动定位原声漫游进度"><div class="media-controls"><button id="media-prev" aria-label="上一张">←</button><button id="media-play" class="primary">▶ 播放原声</button><button id="media-next" aria-label="下一张">→</button><div id="media-dots" class="media-dots"></div><span id="media-time" class="media-time"></span></div><div class="media-audio-download-row"><span id="media-audio-duration" class="media-method"></span><a id="media-audio-download" class="media-download" download>↓ 下载完整音频</a></div><p id="media-notice" class="media-notice" aria-live="polite"></p></footer></section>`;
  const graphStage=document.querySelector('.graph-stage'),inline=document.createElement('section');
  inline.id='media-inline';inline.className='media-inline';inline.hidden=true;inline.setAttribute('aria-label','多媒体与摘要同步阅读');inline.append(surface);graphStage.append(inline);
  const el=id=>document.getElementById('media-'+id),audio=el('audio'),compilation=el('compilation');
  const headerActions=document.createElement('div');headerActions.className='media-header-actions';
  headerActions.append(surface.querySelector('.media-mode-bar'),el('close'));
  surface.querySelector('.media-head').append(headerActions);
  let sourceVideoUrl='';
  const sourceLinks=document.createElement('span');sourceLinks.className='media-source-links';el('source').before(sourceLinks);sourceLinks.append(el('source'));
  for(const [id,parent] of [['local-source',sourceLinks],['video-local-source',surface.querySelector('.media-video-footer')]]){
    const link=document.createElement('a');link.id='media-'+id;link.textContent='本地原视频 ↗';link.target='_blank';link.rel='noopener noreferrer';link.hidden=true;link.className='media-local-source';parent.append(link);
  }
  function updateLocalSource(url,start=0){
    if(url!==undefined)sourceVideoUrl=url||'';
    for(const id of ['local-source','video-local-source']){const link=el(id);link.hidden=!sourceVideoUrl;link.removeAttribute('href');if(sourceVideoUrl)link.href=asset(sourceVideoUrl)+(id==='local-source'?'#t='+Math.max(0,Number(start)||0):'');}
  }
  const subtitle=el('text'),subtitleStyleKey='ontokb.media.subtitleStyle';
  const subtitleDefaults={size:22,font:'sans',color:'#283324',bold:false,lineHeight:1.7};
  const subtitleFonts={sans:'"Segoe UI","Microsoft YaHei",sans-serif',serif:'SimSun,"Songti SC",serif',mono:'Consolas,"Microsoft YaHei",monospace'};
  let subtitleStyle={...subtitleDefaults};
  try{const saved=JSON.parse(localStorage.getItem(subtitleStyleKey)||'null');if(saved){
    if(Number.isFinite(saved.size)&&saved.size>=14&&saved.size<=40)subtitleStyle.size=saved.size;
    if(Object.hasOwn(subtitleFonts,saved.font))subtitleStyle.font=saved.font;
    if(/^#[0-9a-f]{6}$/i.test(saved.color))subtitleStyle.color=saved.color;
    subtitleStyle.bold=saved.bold===true;
    if([1.4,1.7,2].includes(saved.lineHeight))subtitleStyle.lineHeight=saved.lineHeight;
  }}catch(_){}
  function applySubtitleStyle(){subtitle.style.fontSize=subtitleStyle.size+'px';subtitle.style.fontFamily=subtitleFonts[subtitleStyle.font];subtitle.style.color=subtitleStyle.color;subtitle.style.fontWeight=subtitleStyle.bold?'600':'400';subtitle.style.lineHeight=String(subtitleStyle.lineHeight);}
  applySubtitleStyle();
  const volumeKey='ontokb.media.audioVolume',volumeControls=document.createElement('div');volumeControls.className='media-volume-controls';
  volumeControls.innerHTML='<button id="media-mute" type="button" aria-label="静音原声" aria-pressed="false">静音</button><label for="media-volume">音量</label><input id="media-volume" type="range" min="0" max="100" step="1" value="100" aria-label="原声音量"><output id="media-volume-value" for="media-volume">100%</output>';
  subtitle.after(volumeControls);
  try{const saved=JSON.parse(localStorage.getItem(volumeKey)||'null');if(saved&&Number.isFinite(saved.volume)&&saved.volume>=0&&saved.volume<=1){audio.volume=saved.volume;audio.muted=saved.muted===true;}}catch(_){}
  function syncVolume(){const muted=audio.muted||audio.volume===0;el('volume').value=String(Math.round(audio.volume*100));el('volume-value').textContent=muted?'0%':Math.round(audio.volume*100)+'%';el('mute').textContent=muted?'取消静音':'静音';el('mute').setAttribute('aria-label',muted?'取消原声静音':'静音原声');el('mute').setAttribute('aria-pressed',String(muted));}
  function saveVolume(){syncVolume();try{localStorage.setItem(volumeKey,JSON.stringify({volume:audio.volume,muted:audio.muted}));}catch(_){}}
  el('volume').addEventListener('input',()=>{audio.volume=Number(el('volume').value)/100;audio.muted=false;saveVolume();});
  el('mute').onclick=()=>{if(audio.muted||audio.volume===0){if(audio.volume===0)audio.volume=.5;audio.muted=false;}else audio.muted=true;saveVolume();};
  audio.addEventListener('volumechange',saveVolume);syncVolume();
  const subtitleMenu=document.createElement('div');subtitleMenu.id='media-subtitle-settings';subtitleMenu.className='media-subtitle-settings';subtitleMenu.hidden=true;subtitleMenu.setAttribute('role','dialog');subtitleMenu.setAttribute('aria-label','字幕显示设置');
  subtitleMenu.innerHTML='<strong>字幕显示设置</strong><label>字号 <output id="media-subtitle-size-value"></output><input id="media-subtitle-size" type="range" min="14" max="40" step="1"></label><label>字体<select id="media-subtitle-font"><option value="sans">黑体／无衬线</option><option value="serif">宋体／衬线</option><option value="mono">等宽字体</option></select></label><label>文字颜色<input id="media-subtitle-color" type="color"></label><label>行距<select id="media-subtitle-lineHeight"><option value="1.4">紧凑</option><option value="1.7">标准</option><option value="2">宽松</option></select></label><label class="media-subtitle-bold"><input id="media-subtitle-bold" type="checkbox">加粗字幕</label><div class="media-subtitle-actions"><button id="media-subtitle-reset" type="button">恢复默认</button><button id="media-subtitle-done" type="button">完成</button></div>';
  document.body.append(subtitleMenu);
  function syncSubtitleSettings(){for(const key of ['size','font','color','lineHeight'])el('subtitle-'+key).value=String(subtitleStyle[key]);el('subtitle-bold').checked=subtitleStyle.bold;el('subtitle-size-value').textContent=subtitleStyle.size+' px';}
  function closeSubtitleSettings(restore=false){subtitleMenu.hidden=true;subtitle.setAttribute('aria-expanded','false');if(restore)subtitle.focus();}
  function openSubtitleSettings(event){event.preventDefault();event.stopPropagation();syncSubtitleSettings();subtitleMenu.hidden=false;subtitle.setAttribute('aria-expanded','true');const rect=subtitle.getBoundingClientRect(),bounds=subtitleMenu.getBoundingClientRect();const keyboard=event.type==='keydown';subtitleMenu.style.left=Math.max(8,Math.min(keyboard?rect.left:event.clientX,innerWidth-bounds.width-8))+'px';subtitleMenu.style.top=Math.max(8,Math.min(keyboard?rect.top:event.clientY,innerHeight-bounds.height-8))+'px';el('subtitle-size').focus();}
  subtitle.tabIndex=0;subtitle.title='右键调整字幕字号、字体和颜色';subtitle.setAttribute('aria-haspopup','dialog');subtitle.setAttribute('aria-expanded','false');subtitle.addEventListener('contextmenu',openSubtitleSettings);
  subtitle.addEventListener('keydown',event=>{if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10'))openSubtitleSettings(event);});
  subtitleMenu.addEventListener('input',()=>{subtitleStyle={size:Number(el('subtitle-size').value),font:el('subtitle-font').value,color:el('subtitle-color').value,bold:el('subtitle-bold').checked,lineHeight:Number(el('subtitle-lineHeight').value)};applySubtitleStyle();el('subtitle-size-value').textContent=subtitleStyle.size+' px';try{localStorage.setItem(subtitleStyleKey,JSON.stringify(subtitleStyle));}catch(_){}});
  el('subtitle-reset').onclick=()=>{subtitleStyle={...subtitleDefaults};applySubtitleStyle();syncSubtitleSettings();try{localStorage.removeItem(subtitleStyleKey);}catch(_){}};
  el('subtitle-done').onclick=()=>closeSubtitleSettings(true);
  document.addEventListener('pointerdown',event=>{if(!subtitleMenu.hidden&&!subtitleMenu.contains(event.target))closeSubtitleSettings();});
  document.addEventListener('keydown',event=>{if(!subtitleMenu.hidden&&event.key==='Escape'){event.preventDefault();closeSubtitleSettings(true);}});
  window.addEventListener('resize',()=>closeSubtitleSettings());
  const heightDivider=document.createElement('div');heightDivider.id='media-height-divider';heightDivider.tabIndex=0;
  heightDivider.setAttribute('role','separator');heightDivider.setAttribute('aria-orientation','horizontal');heightDivider.setAttribute('aria-label','调整截图与字幕区域高度');heightDivider.setAttribute('aria-controls','media-layout');el('layout').after(heightDivider);
  const heightStorageKey='ontokb.media.layoutHeight';let preferredHeight=null,heightDrag=null;
  try{const saved=Number(localStorage.getItem(heightStorageKey));if(Number.isFinite(saved)&&saved>=160)preferredHeight=saved;}catch(_){}
  function resizeBlock(target,label,key,axis='height',parent=target){
    const divider=document.createElement('div');divider.className='media-block-divider '+(axis==='width'?'vertical':'horizontal');divider.tabIndex=0;
    divider.setAttribute('role','separator');divider.setAttribute('aria-orientation',axis==='width'?'vertical':'horizontal');divider.setAttribute('aria-label',label);divider.title=label+' · 双击恢复默认';
    target.after(divider);let drag=null;
    function apply(value,save=false){
      if(!target.getBoundingClientRect().width)return;
      const available=axis==='width'?parent.clientWidth:surface.clientHeight;
      const videoFrame=target.classList.contains('media-compilation-frame');
      const min=axis==='width'||videoFrame?120:target.classList.contains('media-footer')?68:32;
      const max=videoFrame?Math.max(min,parent.clientHeight-(parent.querySelector('.media-footer')?.getBoundingClientRect().height||100)-10):Math.max(min,available*(axis==='width'?.85:.45));
      const size=Math.round(Math.max(min,Math.min(max,value)));
      if(axis==='width')parent.style.gridTemplateColumns=`${size}px 8px minmax(0,1fr)`;
      else{target.style.height=size+'px';target.style.flex='0 0 '+size+'px';}
      divider.setAttribute('aria-valuemin',min);divider.setAttribute('aria-valuemax',Math.round(max));divider.setAttribute('aria-valuenow',size);
      if(save)try{localStorage.setItem(key,String(size));}catch(_){}
    }
    try{const saved=Number(localStorage.getItem(key));if(saved>0){const observer=new ResizeObserver(()=>{if(target.getBoundingClientRect().width>0){apply(saved);observer.disconnect();}});observer.observe(target);}}catch(_){}
    divider.onpointerdown=event=>{if(event.button!==0)return;event.preventDefault();divider.focus();drag={point:axis==='width'?event.clientX:event.clientY,size:target.getBoundingClientRect()[axis]};divider.setPointerCapture(event.pointerId);};
    divider.onpointermove=event=>{if(drag)apply(drag.size+(axis==='width'?event.clientX:event.clientY)-drag.point,true);};
    const finish=event=>{drag=null;if(divider.hasPointerCapture(event.pointerId))divider.releasePointerCapture(event.pointerId);};divider.onpointerup=finish;divider.onpointercancel=finish;divider.onlostpointercapture=()=>drag=null;
    divider.onkeydown=event=>{const keys=axis==='width'?['ArrowLeft','ArrowRight']:['ArrowUp','ArrowDown'];if(!keys.includes(event.key))return;event.preventDefault();apply(target.getBoundingClientRect()[axis]+(event.key===keys[0]?-10:10),true);};
    divider.ondblclick=()=>{target.style.height='';target.style.flex='';if(axis==='width')parent.style.gridTemplateColumns='';try{localStorage.removeItem(key);}catch(_){}};
    window.addEventListener('resize',()=>{if(axis==='width'&&parent.style.gridTemplateColumns)apply(target.getBoundingClientRect().width);else if(target.style.height)apply(parseFloat(target.style.height));});
  }
  resizeBlock(surface.querySelector('.media-head'),'调整标题区高度','ontokb.media.headerHeight');
  resizeBlock(el('layout').querySelector('.media-frame'),'调整截图与字幕宽度','ontokb.media.frameWidth','width',el('layout'));
  resizeBlock(el('player').querySelector('.media-footer'),'调整播放控制区高度','ontokb.media.footerHeight');
  resizeBlock(el('video-player').querySelector('.media-compilation-frame'),'调整精剪视频高度','ontokb.media.videoHeight','height',el('video-player'));
  const takeaways=document.createElement('section');takeaways.id='media-takeaways';takeaways.className='media-takeaways';takeaways.setAttribute('aria-labelledby','media-takeaways-heading');
  takeaways.innerHTML='<div class="media-takeaways-head"><h3 id="media-takeaways-heading">值得记住</h3><span id="media-takeaways-count"></span></div><div id="media-takeaways-list" class="media-takeaways-list"></div>';
  el('player').append(takeaways);
  function renderTakeaways(){
    const points=(currentDoc?.key_points||[]).filter(text=>typeof text==='string'&&text.trim());
    const list=el('takeaways-list');list.replaceChildren();el('takeaways-count').textContent=points.length+' 条 · 当前文章';
    for(const text of points){const item=document.createElement('div');item.className='key-point';item.textContent=text;list.append(item);}
    if(!points.length){const empty=document.createElement('p');empty.className='media-takeaways-empty';empty.textContent='这篇文章暂无“值得记住”条目。';list.append(empty);}
    list.scrollTop=0;
  }
  const summaryLabel=document.createElement('div');summaryLabel.id='media-current-summary';summaryLabel.className='media-current-summary';el('title').after(summaryLabel);
  const coverage=document.createElement('p');coverage.id='media-coverage';coverage.className='media-coverage';el('notice').before(coverage);
  const videoSummaryLabel=document.createElement('div');videoSummaryLabel.id='media-video-current-summary';videoSummaryLabel.className='media-current-summary';el('video-notice').before(videoSummaryLabel);
  const videoSubtitle=document.createElement('p');videoSubtitle.id='media-video-caption';videoSubtitle.className='media-video-caption';videoSubtitle.setAttribute('aria-live','polite');videoSummaryLabel.after(videoSubtitle);
  let generation=0,controller=null,poll=null,doc=null,slides=[],videoSlides=[],index=0,finished=false,clipGeneration=0,mode='video',summaryMap=[],activeSummary=null,pendingSeek=null,pendingVideoSeek=null,returnPoint=null,entranceTarget=null,audioLocationActive=false,scrub=null;
  const summaryList=document.getElementById('summary-steps'),isOpen=()=>!inline.hidden;
  const graphAudio=document.createElement('button');graphAudio.id='media-graph-audio';graphAudio.type='button';graphAudio.textContent='定位本段原声';graphAudio.title='在原声漫游中定位当前摘要段落';document.querySelector('.tour-controls').append(graphAudio);
  function updateGraphEntry(){graphAudio.disabled=currentDoc?.kind!=='video'||!currentDoc?.steps?.length;}
  updateGraphEntry();
  const clock=value=>{const n=Math.max(0,Math.floor(Number(value)||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');};
  const length=s=>Math.max(0,Number(s.duration)||Number(s.end)-Number(s.start)||0);
  const total=()=>slides.reduce((sum,s)=>sum+length(s),0);
  function heightBounds(){const min=typeof matchMedia==='function'&&matchMedia('(max-width:1000px)').matches?280:160;return {min,max:Math.max(360,Math.min(900,Math.round((el('player').getBoundingClientRect().height||400)*2)))};}
  function describeHeight(height){const bounds=heightBounds();heightDivider.setAttribute('aria-valuemin',bounds.min);heightDivider.setAttribute('aria-valuemax',bounds.max);heightDivider.setAttribute('aria-valuenow',Math.round(height));heightDivider.setAttribute('aria-valuetext','截图和字幕区域高度 '+Math.round(height)+' 像素');}
  function applyHeight(value,persist=false){
    const bounds=heightBounds();preferredHeight=Math.max(bounds.min,Math.min(bounds.max,value));el('player').classList.add('media-height-custom');el('player').style.setProperty('--media-layout-height',Math.round(preferredHeight)+'px');describeHeight(preferredHeight);
    if(persist)try{localStorage.setItem(heightStorageKey,String(Math.round(preferredHeight)));}catch(_){}
  }
  function refreshHeight(){if(mode!=='audio'||!isOpen()||el('player').hidden)return;if(preferredHeight!==null)applyHeight(preferredHeight);else describeHeight(el('layout').getBoundingClientRect().height||260);}
  function finishHeightDrag(){if(!heightDrag)return;const token=heightDrag.generation;heightDrag=null;document.body.classList.remove('media-height-resizing');if(token===generation&&preferredHeight!==null)applyHeight(preferredHeight,true);}
  function asset(path){
    if(typeof path!=='string'||!path)throw new Error('媒体地址不可用。');
    const url=new URL(path,new URL(apiUrl('/',{}),location.href));
    if(!['http:','https:'].includes(url.protocol))throw new Error('媒体地址不可用。');return url.href;
  }
  function cleanup(){
    generation++;clipGeneration++;clearTimeout(poll);poll=null;controller?.abort();controller=null;pendingSeek=null;pendingVideoSeek=null;audioLocationActive=false;scrub=null;heightDrag=null;document.body.classList.remove('media-height-resizing');highlightSummary(null);
    for(const media of [audio,compilation]){media.pause();media.removeAttribute('src');media.load();}compilation.removeAttribute('poster');
  }
  function highlightSummary(next){
    if(Number.isInteger(next)&&next>=0&&next<(doc?.steps?.length||0)&&doc.id===currentDoc?.id&&isOpen())returnPoint={id:doc.id,index:next};
    if(activeSummary===next&&next!==null)return;activeSummary=next;
    [...summaryList.children].forEach((button,i)=>{button.classList.toggle('media-current',i===next);button.setAttribute('aria-current',i===next?'step':'false');});
    if(next!==null){const card=summaryList.children[next];if(card)document.getElementById('reading-body').scrollTo({top:Math.max(0,card.offsetTop-35),behavior:'smooth'});}
  }
  function restoreSummary(){
    highlightSummary(null);[...summaryList.children].forEach(button=>button.setAttribute('aria-current',button.classList.contains('active')?'step':'false'));
  }
  function mappedIndex(value){return Number.isInteger(value)&&Number.isInteger(summaryMap[value])?summaryMap[value]:null;}
  function setSummaryMap(result){
    summaryMap=(result.summary_steps||[]).map((text,i)=>{
      const steps=doc.steps||[];if(steps[i]?.text===text)return i;
      const matches=steps.map((step,j)=>step.text===text?j:-1).filter(j=>j>=0);return matches.length===1?matches[0]:null;
    });
  }
  function videoSummaryIndex(slide){return slide?mappedIndex(slide.summary_index??slide.summary_indices?.[0]):null;}
  function normalizeCaptions(slide){slide.captions=(slide.captions||[]).filter(c=>c&&typeof c.text==='string'&&Number.isFinite(Number(c.start))&&Number(c.end)>Number(c.start)).sort((a,b)=>Number(a.start)-Number(b.start));return slide;}
  function syncVideoSummary(time){
    if(mode!=='video'||!isOpen())return;
    const slide=[...videoSlides].reverse().find(s=>Number(s.timeline_start)<=time&&time<Number(s.timeline_end));
    const relative=slide?time-Number(slide.timeline_start):0;
    const cue=[...(slide?.captions||[])].reverse().find(c=>Number(c.start)<=relative&&relative<Number(c.end));
    const mapped=slide?.captions?.length?(cue?mappedIndex(cue.summary_index):null):videoSummaryIndex(slide);highlightSummary(mapped);
    el('video-caption').textContent=cue?.text||'';
    el('video-current-summary').textContent=mapped===null?'当前片段未关联摘要段落':'当前片段 · 左侧摘要第 '+(mapped+1)+' 段';
  }
  function syncCaption(time){
    if(mode!=='audio'||!slides[index]||!audioLocationActive)return;
    const cue=[...(slides[index].captions||[])].reverse().find(c=>Number(c.start)<=time&&time<Number(c.end));
    el('text').textContent=cue?.text||'';
    const mapped=cue?mappedIndex(cue.summary_index):null;highlightSummary(mapped);
    el('current-summary').textContent=mapped===null?'此处未关联摘要段落':'正在讲述 · 左侧摘要第 '+(mapped+1)+' 段';
  }
  const currentTime=()=>scrub?Math.max(0,scrub.time-slides.slice(0,index).reduce((sum,s)=>sum+length(s),0)):pendingSeek?pendingSeek.offset:(audio.currentTime||0);
  function message(text,retry=false){el('status').hidden=false;el('player').hidden=true;el('video-player').hidden=true;el('message').textContent=text;el('retry').hidden=!retry;}
  function progress(){
    const elapsed=scrub?scrub.time:slides.slice(0,index).reduce((sum,s)=>sum+length(s),0)+Math.min(currentTime(),length(slides[index]||{}));
    if(!scrub)el('progress').value=total()?100*elapsed/total():0;el('time').textContent=clock(elapsed)+' / '+clock(total());
    el('progress').setAttribute('aria-valuetext',clock(elapsed)+' / '+clock(total()));
  }
  async function play(){
    if(pendingSeek){pendingSeek.autoplay=true;el('play').textContent='Ⅱ 暂停';return;}
    const token=clipGeneration;
    try{await audio.play();if(token!==clipGeneration||!isOpen())return;el('notice').textContent='原声、字幕和左侧摘要同步播放。点击摘要可跳到已收录的原声。';}
    catch(error){if(token!==clipGeneration||!isOpen())return;el('notice').textContent='点击「播放原声」开始收听；浏览器可能需要你手动启动声音。';}
  }
  function showSlide(next,autoplay=false,offset=0){
    clipGeneration++;audio.pause();index=next;finished=false;const slide=slides[index];pendingSeek=null;audioLocationActive=true;
    el('counter').textContent=String(index+1).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');
    el('title').textContent=slide.title||'原声片段 '+(index+1);
    el('image').hidden=!slide.image_url;el('image').removeAttribute('src');if(slide.image_url)el('image').src=asset(slide.image_url);
    el('source').hidden=true;try{const source=new URL(doc.url);if(['http:','https:'].includes(source.protocol)){source.searchParams.set('t',Math.floor(Number(slide.start)||0)+'s');el('source').href=source.href;el('source').textContent='原视频 '+clock(slide.start)+'–'+clock(slide.end)+' ↗';el('source').hidden=false;}}catch(_){}
    updateLocalSource(undefined,slide.start);
    el('prev').disabled=index===0;el('next').disabled=index===slides.length-1;el('play').textContent='▶ 播放原声';el('notice').textContent='画面将停留到这一段原声结束，再切换到下一张。';
    [...el('dots').children].forEach((dot,i)=>dot.setAttribute('aria-current',String(i===index)));
    audio.src=asset(slide.audio_url);audio.load();
    if(offset>0){pendingSeek={token:clipGeneration,offset:Math.min(offset,length(slide)),autoplay};if(autoplay)el('play').textContent='Ⅱ 暂停';}
    progress();syncCaption(offset);if(autoplay&&!pendingSeek)play();
  }
  function seekTimeline(time){
    let next=0,offset=Math.max(0,Math.min(time,total()));
    while(next<slides.length-1&&offset>=length(slides[next])){offset-=length(slides[next]);next++;}
    if(next!==index||!audioLocationActive||!audio.getAttribute('src'))showSlide(next,false,offset);
    else{
      clipGeneration++;audio.pause();pendingSeek=null;finished=false;
      if(audio.readyState>=1)audio.currentTime=offset;
      else pendingSeek={token:clipGeneration,offset,autoplay:false};
      progress();syncCaption(offset);
    }
    finished=time>=total();el('play').textContent=finished?'↻ 再听一次':'▶ 播放原声';
  }
  function beginScrub(){
    if(scrub||mode!=='audio'||!isOpen()||!slides.length)return;
    scrub={generation,wasPlaying:pendingSeek?.autoplay??!audio.paused,time:Math.max(0,Math.min(100,Number(el('progress').value)||0))*total()/100};
    clipGeneration++;if(pendingSeek){pendingSeek.token=clipGeneration;pendingSeek.autoplay=false;}audio.pause();
  }
  function previewScrub(){
    beginScrub();if(!scrub||scrub.generation!==generation)return;
    scrub.time=Math.max(0,Math.min(100,Number(el('progress').value)||0))*total()/100;seekTimeline(scrub.time);
  }
  function finishScrub(){
    const previous=scrub;if(!previous)return;
    if(previous.generation!==generation||!isOpen()||mode!=='audio'){scrub=null;return;}
    seekTimeline(previous.time);scrub=null;progress();if(previous.wasPlaying&&!finished)play();
  }
  function setDownload(id,url){el(id).hidden=!url;el(id).removeAttribute('href');if(url)el(id).href=asset(url);}
  function durationText(result){return '本次 '+clock(Number(result.duration)||total())+(Number(result.source_duration)>0?' · 原视频 '+clock(result.source_duration):'');}
  function ready(result,target){
    if(result.mode&&result.mode!==mode)throw new Error('返回了另一种摘要，请重试。');
    setSummaryMap(result);
    el('method').textContent=typeof result.message==='string'?result.message:'';el('method').hidden=!el('method').textContent;el('status').hidden=true;
    if(mode==='video'){
      videoSlides=(result.slides||[]).filter(s=>Number.isFinite(Number(s.timeline_start))&&Number(s.timeline_end)>Number(s.timeline_start)).map(normalizeCaptions);
      compilation.src=asset(result.video_url);const poster=(result.slides||[]).find(s=>s.image_url)?.image_url;if(poster)compilation.setAttribute('poster',asset(poster));compilation.load();
      setDownload('video-download',result.download_url||result.video_url);el('video-duration').textContent=durationText(result);
      el('video-notice').textContent='播放精剪时会高亮已关联的左侧摘要；点击摘要可跳到已收录片段。';
      el('player').hidden=true;el('video-player').hidden=false;syncVideoSummary(0);return;
    }
    slides=(result.slides||[]).filter(s=>s&&s.audio_url&&Number.isFinite(Number(s.start))&&Number(s.end)>Number(s.start));
    if(!slides.length)throw new Error('暂时没有可以播放的原声片段，请重试。');
    slides.forEach(normalizeCaptions);
    const mapped=new Set(slides.flatMap(slide=>slide.captions.map(c=>mappedIndex(c.summary_index))).filter(i=>i!==null));
    el('coverage').textContent='已关联 '+mapped.size+' / '+(doc.steps||[]).length+' 段摘要 · 点击左侧摘要跳转，未收录段落会单独提示。';
    el('dots').replaceChildren();slides.forEach((s,i)=>{const dot=document.createElement('button');dot.className='media-dot';dot.setAttribute('aria-label','跳到第 '+(i+1)+' 张');dot.onclick=()=>showSlide(i,!audio.paused);el('dots').append(dot);});
    el('audio-duration').textContent=durationText(result);setDownload('audio-download',result.download_url||result.audio_url);
    el('video-player').hidden=true;el('player').hidden=false;refreshHeight();
    if(target&&target.id===doc.id&&target.generation===generation){
      if(!seekSummary(target.index,{autoplay:false})){
        audioLocationActive=false;finished=true;index=0;el('counter').textContent='—';el('image').hidden=true;el('source').hidden=true;el('title').textContent='这段摘要未收录原声';
        el('text').textContent='请选择另一段摘要，或从头收听已收录内容。';el('current-summary').textContent='左侧摘要第 '+(target.index+1)+' 段 · 未收录';
        el('prev').disabled=true;el('next').disabled=true;el('play').textContent='▶ 从头收听';el('progress').value=0;el('time').textContent='0:00 / '+clock(total());
      }
    }else showSlide(0);
  }
  async function prepare(){
    cleanup();el('method').textContent='';el('method').hidden=true;slides=[];videoSlides=[];summaryMap=[];
    const token=generation,requestedMode=mode;doc=currentDoc?{...currentDoc}:null;
    updateLocalSource('');
    renderTakeaways();
    const target=entranceTarget?.id===doc?.id?{...entranceTarget,generation:token}:null;
    el('mode-video').setAttribute('aria-pressed',String(mode==='video'));el('mode-audio').setAttribute('aria-pressed',String(mode==='audio'));
    if(!doc){message('请先选择一篇视频资料。');return;}
    el('heading').replaceChildren();
    if(/^https?:\/\//i.test(doc.url||'')){
      const titleLink=document.createElement('a');titleLink.href=doc.url;titleLink.target='_blank';titleLink.rel='noopener noreferrer';titleLink.textContent=doc.title||'多媒体摘要';titleLink.title='在新标签页打开原文：'+(doc.title||doc.url);el('heading').append(titleLink);
    }else el('heading').textContent=doc.title||'多媒体摘要';
    if(doc.kind!=='video'){message('这篇资料没有可用的视频原声。视频精剪与原声漫游适用于视频资料，你仍可关闭此窗口继续摘要与知识图谱漫游。');return;}
    message(mode==='video'?'Codex 正在根据摘要组织约 1–2 分钟的视频剪辑…\n原视频画面和声音将拼接成一段可下载的完整短片。':'Codex 正在根据摘要组织原声漫游与字幕…\n保留约原视频三分之一时长，原声、画面和左侧摘要同步展示。');
    controller=new AbortController();const sessionController=controller,started=Date.now();
    async function request(first){
      if(token!==generation||!isOpen())return;
      const requestController=new AbortController(),cancel=()=>requestController.abort();sessionController.signal.addEventListener('abort',cancel,{once:true});const deadline=setTimeout(cancel,45000);
      try{
        const response=await fetch(apiUrl(first?'/api/media/prepare':'/api/media/status',first?{}:{content_id:doc.id,mode:requestedMode}),{method:first?'POST':'GET',headers:first?{'Content-Type':'application/json'}:undefined,body:first?JSON.stringify({content_id:doc.id,mode:requestedMode}):undefined,signal:requestController.signal});
        const result=await response.json();if(token!==generation||!isOpen())return;
        if(!response.ok)throw new Error(result.error||result.message||'媒体服务暂时不可用。');
        updateLocalSource(result.source_video_url);
        if(result.status==='ready'){ready(result,target);return;}
        if(result.status==='error'||result.status==='unavailable'){message(result.message||'暂时无法准备这种多媒体摘要。',true);return;}
        if(Date.now()-started>300000){message('准备仍在后台进行。稍后点击「重新准备」查看结果。',true);return;}
        message(result.message||'正在准备媒体片段，请稍候…');poll=setTimeout(()=>request(false),1800);
      }catch(error){if(token===generation&&isOpen())message(error.name==='AbortError'?'连接超时，请重试。':'无法准备多媒体摘要：'+error.message,true);}
      finally{clearTimeout(deadline);sessionController.signal.removeEventListener('abort',cancel);}
    }
    request(true);
  }
  function close(navigate=true){
    closeSubtitleSettings();
    const target=returnPoint;
    cleanup();inline.hidden=true;graphStage.classList.remove('media-inline-active');document.body.classList.remove('media-reading-active');
    restoreSummary();
    if(navigate&&target?.id===currentDoc?.id&&Number.isInteger(target.index)&&target.index>=0&&target.index<(currentDoc?.steps?.length||0))selectStep(target.index,true);
    entranceTarget=null;
  }
  function open(nextMode,requested=null){
    if(returnPoint?.id!==currentDoc?.id)returnPoint=null;
    if(Number.isInteger(requested)&&requested>=0&&requested<(currentDoc?.steps?.length||0)){
      entranceTarget={id:currentDoc.id,index:requested};returnPoint={...entranceTarget};
    }else{
      entranceTarget=null;
      if(!isOpen()&&Number.isInteger(stepIndex)&&stepIndex>=0&&stepIndex<(currentDoc?.steps?.length||0))returnPoint={id:currentDoc.id,index:stepIndex};
    }
    cleanup();mode=nextMode;stopTour();
    inline.hidden=false;graphStage.classList.add('media-inline-active');document.body.classList.add('media-reading-active');
    document.getElementById('reading-body').scrollTo({top:Math.max(0,summaryList.offsetTop-45),behavior:'instant'});
    prepare();
  }
  el('open').onclick=()=>open('video');el('audio-open').onclick=()=>open('audio');
  graphAudio.onclick=()=>{if(!graphAudio.disabled)open('audio',stepIndex);};
  el('mode-video').onclick=()=>{if(mode!=='video')open('video');};el('mode-audio').onclick=()=>{if(mode!=='audio')open('audio');};
  el('retry').onclick=prepare;el('close').onclick=()=>close();
  heightDivider.addEventListener('pointerdown',event=>{
    if(mode!=='audio'||!isOpen()||el('player').hidden||(event.button!==undefined&&event.button!==0))return;
    event.preventDefault();heightDrag={generation,y:event.clientY,height:el('layout').getBoundingClientRect().height||260};heightDivider.setPointerCapture?.(event.pointerId);document.body.classList.add('media-height-resizing');
  });
  heightDivider.addEventListener('pointermove',event=>{if(heightDrag&&heightDrag.generation===generation){event.preventDefault();applyHeight(heightDrag.height+event.clientY-heightDrag.y);}});
  for(const event of ['pointerup','pointercancel','lostpointercapture'])heightDivider.addEventListener(event,finishHeightDrag);
  heightDivider.addEventListener('keydown',event=>{
    const bounds=heightBounds(),height=preferredHeight??(el('layout').getBoundingClientRect().height||260),step=event.shiftKey?50:20;
    const next={ArrowUp:height-step,ArrowDown:height+step,Home:bounds.min,End:bounds.max}[event.key];
    if(next!==undefined){event.preventDefault();applyHeight(next,true);}
  });
  heightDivider.addEventListener('dblclick',()=>{preferredHeight=null;el('player').classList.remove('media-height-custom');el('player').style.removeProperty('--media-layout-height');try{localStorage.removeItem(heightStorageKey);}catch(_){}refreshHeight();});
  if(typeof ResizeObserver==='function')new ResizeObserver(refreshHeight).observe(el('player'));
  el('progress').addEventListener('pointerdown',event=>{beginScrub();if(scrub)el('progress').setPointerCapture?.(event.pointerId);});
  el('progress').addEventListener('input',previewScrub);
  for(const event of ['change','pointerup','pointercancel','blur'])el('progress').addEventListener(event,finishScrub);
  el('prev').onclick=()=>showSlide(index-1,!audio.paused);el('next').onclick=()=>showSlide(index+1,!audio.paused);
  el('play').onclick=()=>{if(pendingSeek){pendingSeek.autoplay=!pendingSeek.autoplay;el('play').textContent=pendingSeek.autoplay?'Ⅱ 暂停':'▶ 播放原声';return;}if(finished){showSlide(0,true);return;}if(audio.paused)play();else audio.pause();};
  surface.addEventListener('keydown',event=>{if(mode!=='audio'||el('player').hidden||event.target.closest('button,a,input,select,textarea,summary'))return;if(event.key==='ArrowLeft'&&index>0){event.preventDefault();showSlide(index-1,!audio.paused);}if(event.key==='ArrowRight'&&index<slides.length-1){event.preventDefault();showSlide(index+1,!audio.paused);}});
  function seekSummary(requested,options={}){
    if(!isOpen()||doc?.id!==currentDoc?.id||!Number.isInteger(requested))return false;
    if(mode==='video'){
      let target=null;
      videoSlides.some(slide=>{const cue=slide.captions.find(c=>mappedIndex(c.summary_index)===requested);if(cue){target=Number(slide.timeline_start)+Number(cue.start);return true;}if(!slide.captions.length&&videoSummaryIndex(slide)===requested){target=Number(slide.timeline_start);return true;}return false;});
      if(target===null){el('video-notice').textContent='未收录：本次精剪未包含摘要第 '+(requested+1)+' 段，播放位置未改变。';return false;}
      pendingVideoSeek={time:target,autoplay:options.autoplay??!compilation.paused};compilation.pause();syncVideoSummary(target);
      if(compilation.readyState>=1)applyVideoSeek();
      el('video-notice').textContent='已定位到摘要第 '+(requested+1)+' 段对应的视频片段。';return true;
    }
    let match=null;slides.some((slide,i)=>{const cue=slide.captions.find(c=>mappedIndex(c.summary_index)===requested);if(cue){match={index:i,time:Number(cue.start)};return true;}return false;});
    if(!match){el('notice').textContent='未收录：本次原声未包含摘要第 '+(requested+1)+' 段，播放位置未改变。';return false;}
    const autoplay=options.autoplay??!audio.paused;showSlide(match.index,autoplay,match.time);
    el('notice').textContent='已跳到摘要第 '+(requested+1)+' 段对应的原声'+(autoplay?'。':'，点击播放可继续收听。');
    return true;
  }
  summaryList.addEventListener('click',event=>{
    if(!isOpen()||(mode==='audio'?el('player').hidden:el('video-player').hidden))return;
    const button=event.target.closest('.summary-step'),requested=[...summaryList.children].indexOf(button);if(requested<0)return;
    event.stopPropagation();seekSummary(requested);
  },true);
  audio.addEventListener('loadedmetadata',()=>{
    const seek=pendingSeek;if(!seek||seek.token!==clipGeneration||!isOpen())return;
    audio.currentTime=seek.offset;pendingSeek=null;progress();syncCaption(seek.offset);if(seek.autoplay)play();
  });
  audio.addEventListener('play',()=>{el('play').textContent='Ⅱ 暂停';});audio.addEventListener('pause',()=>{el('play').textContent=finished?'↻ 再听一次':'▶ 播放原声';});
  audio.addEventListener('timeupdate',()=>{progress();if(mode==='audio'&&isOpen())syncCaption(currentTime());});
  audio.addEventListener('seeked',()=>{if(mode==='audio'&&isOpen()){progress();syncCaption(currentTime());}});
  audio.addEventListener('ended',()=>{if(!isOpen()||mode!=='audio'||!audioLocationActive||scrub)return;if(index<slides.length-1)showSlide(index+1,true);else{finished=true;syncCaption(Math.max(0,length(slides[index])-.001));el('progress').value=100;el('time').textContent=clock(total())+' / '+clock(total());el('play').textContent='↻ 再听一次';el('notice').textContent='漫游结束。可点击已收录的摘要段落重听，或返回知识图谱。';}});
  audio.addEventListener('error',()=>{if(isOpen()&&audio.getAttribute('src'))el('notice').textContent='这个原声片段无法播放。可切换下一张，或重新准备。';});
  function applyVideoSeek(){const seek=pendingVideoSeek,token=generation;if(!seek||!isOpen()||mode!=='video')return;compilation.currentTime=seek.time;pendingVideoSeek=null;syncVideoSummary(seek.time);if(seek.autoplay)compilation.play().catch(()=>{if(token===generation&&mode==='video'&&isOpen())el('video-notice').textContent='已定位，请点击视频播放键继续。';});}
  compilation.addEventListener('loadedmetadata',applyVideoSeek);
  compilation.addEventListener('timeupdate',()=>syncVideoSummary(pendingVideoSeek?.time??compilation.currentTime));
  compilation.addEventListener('seeked',()=>syncVideoSummary(pendingVideoSeek?.time??compilation.currentTime));
  compilation.addEventListener('error',()=>{if(isOpen()&&compilation.getAttribute('src'))el('video-notice').textContent='视频无法在浏览器播放，可尝试下载完整 MP4，或重新准备。';});
  compilation.addEventListener('ended',()=>{if(isOpen()&&mode==='video'){syncVideoSummary(Math.max(0,(Number(compilation.duration)||Number(videoSlides.at(-1)?.timeline_end)||0)-.001));el('video-notice').textContent='精剪已播完。可以点击已收录的摘要段落重看，或切换原声漫游听更长的内容。';}});
  el('image').onerror=()=>{el('image').hidden=true;};
  new MutationObserver(()=>{
    updateGraphEntry();
    renderTakeaways();
    if(doc&&currentDoc?.id!==doc.id){if(isOpen())close(false);returnPoint=null;entranceTarget=null;}
  }).observe(document.getElementById('document-title'),{childList:true,subtree:true,characterData:true});
})();
