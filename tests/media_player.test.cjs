const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function harness(fetchImpl, {kind = 'video', fakeTimers = false,storedHeight=null} = {}) {
  const nodes = new Map(), timers = new Map(), createdTags=[],selections=[]; let timerId = 0;
  const storage=new Map(storedHeight===null?[]:[['ontokb.media.layoutHeight',String(storedHeight)]]);
  class Element {
    constructor() {
      this.children = []; this.listeners = {}; this.attrs = {}; this.hidden = false; this.paused = true; this.currentTime = 0;this.open=false;this.offsetTop=0;this.volume=1;this.muted=false;
      const classes=new Set();this.classList={add:(...names)=>names.forEach(n=>classes.add(n)),remove:(...names)=>names.forEach(n=>classes.delete(n)),contains:n=>classes.has(n),toggle:(n,on)=>{if(on===undefined)on=!classes.has(n);if(on)classes.add(n);else classes.delete(n);return on;}};
      const styles=new Map();this.style={setProperty:(key,value)=>styles.set(key,value),removeProperty:key=>styles.delete(key),getPropertyValue:key=>styles.get(key)||''};
    }
    set id(value) { this._id = value; nodes.set(value, this); }
    get id() { return this._id; }
    set innerHTML(value) { for (const match of value.matchAll(/id="([^"]+)"/g)) get(match[1]); }
    set src(value) { this.attrs.src = value;(this.loadedSources||=[]).push(value); }
    get src() { return this.attrs.src; }
    set href(value) { this.attrs.href = value; }
    get href() { return this.attrs.href; }
    setAttribute(key, value) { this.attrs[key] = value; }
    getAttribute(key) { return this.attrs[key]; }
    removeAttribute(key) { delete this.attrs[key]; }
    append(child) { child.remove();this.children.push(child);child.parent=this; }
    remove() {if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);this.parent=null;}
    after() {}
    before() {}
    getBoundingClientRect(){return this.rect||{height:this.id==='media-player'?400:260,width:900,left:0,top:0};}
    scrollTo(value) {this.lastScroll=value;this.scrollCount=(this.scrollCount||0)+1;}
    closest(selector) {return selector.includes('.summary-step')&&this.classList.contains('summary-step')?this:null;}
    querySelector(selector) {this.selected ||= new Map();if(!this.selected.has(selector))this.selected.set(selector,new Element());return this.selected.get(selector);}
    replaceChildren() { this.children = []; }
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
    fire(name,event={}) { for (const callback of this.listeners[name] || []) callback(event); }
    showModal() { this.open = true; }
    close() { this.open = false; this.fire('close'); }
    load() { this.currentTime = 0;this.readyState=0;this.loadCount=(this.loadCount||0)+1; }
    async play() { this.paused = false; this.fire('play'); }
    pause() { this.paused = true; this.fire('pause'); }
  }
  function get(id) { if (!nodes.has(id)) { const el = new Element(); el.id = id; } return nodes.get(id); }
  let observer;
  const context = {
    document: { createElement: tag => {createdTags.push(tag);return new Element();}, getElementById: get, querySelector: () => new Element(), body: new Element(), addEventListener() {} },
    window: {addEventListener() {}},
    currentDoc: { id: 'video-1', kind, title: 'An example', summary: 'A concise overview',steps:[{text:'第一段摘要'},{text:'第二段摘要'},{text:'未收录的第三段'}], url: 'https://youtube.com/watch?v=example' },
    stepIndex:0,
    selectStep(index){context.stepIndex=index;selections.push({id:context.currentDoc?.id,index});get('summary-steps').children.forEach((button,i)=>{button.classList.toggle('active',i===index);button.setAttribute('aria-current',i===index?'step':'false');});},
    stopTour() {}, apiUrl: (p, query) => 'http://127.0.0.1:8765' + p + '?' + new URLSearchParams(query),
    location: { href: 'file:///C:/graph.html' }, URL, AbortController, fetch: fetchImpl,
    localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value)),removeItem:key=>storage.delete(key)},
    setTimeout: fakeTimers ? (fn, delay) => { const id=++timerId;timers.set(id,{fn,delay});return id; } : setTimeout,
    clearTimeout: fakeTimers ? id => timers.delete(id) : clearTimeout,
    MutationObserver: class { constructor(fn) { observer = fn; } observe() {} },
  };
  for(let i=0;i<3;i++){const button=new Element();button.classList.add('summary-step');if(i===0)button.classList.add('active');button.offsetTop=100*i;get('summary-steps').append(button);}
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../src/ontokb/web/media.js'), 'utf8'), context);
  return { get: name => get('media-' + name), context, changed: () => observer(), summary:get('summary-steps'),reading:get('reading-body'),
    clickSummary:i=>get('summary-steps').fire('click',{target:get('summary-steps').children[i],stopPropagation(){}}),
    poll: () => { const found=[...timers.entries()].find(([,t])=>t.delay===1800);assert.ok(found,'scheduled poll');timers.delete(found[0]);found[1].fn(); },
    timers,createdTags,selections,storage,
  };
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const audioReady = { status: 'ready', mode: 'audio', duration: 300, source_duration: 900, target_duration: 300,
  summary_steps:['第一段摘要','第二段摘要','未收录的第三段'],
  audio_url: '/api/media/assets/highlight.m4a?mode=audio', download_url: '/api/media/assets/highlight.m4a?mode=audio&download=1', slides: [
    { title: '<script>hello</script>', text: '第一段原声', start: 40, end: 160, image_url: '/api/media/assets/a.jpg?mode=audio', audio_url: '/api/media/assets/a.m4a?mode=audio',captions:[{start:0,end:60,text:'第一条中文字幕',summary_index:0},{start:59,end:110,text:'第二条中文字幕',summary_index:1}] },
    { title: 'Second', text: '第二段原声', start: 200, end: 380, image_url: '/api/media/assets/b.jpg?mode=audio', audio_url: '/api/media/assets/b.m4a?mode=audio',summary_index:1,captions:[{start:10,end:80,text:'第二段原声中文字幕',summary_index:1},{start:90,end:180,text:'不关联内容',summary_index:null}] },
  ],
};
const videoReady = { status: 'ready', mode: 'video', duration: 90, source_duration: 900, target_duration: 90,
  summary_steps:['第一段摘要','第二段摘要','未收录的第三段'],
  video_url: '/api/media/assets/highlight.mp4?mode=video', download_url: '/api/media/assets/highlight.mp4?mode=video&download=1',
  slides: [{ image_url: '/api/media/assets/a.jpg?mode=video',start:500,end:545,timeline_start:0,timeline_end:45,summary_index:0,captions:[{start:0,end:45,text:'视频第一条中文字幕',summary_index:0}] },
    {start:1000,end:1045,timeline_start:45,timeline_end:90,summary_index:1,captions:[{start:5,end:25,text:'视频第二条中文字幕',summary_index:1},{start:30,end:45,text:'没有关联摘要的结尾',summary_index:null}]}],
};
const response = payload => ({ ok: true, json: async () => payload });

test('video mode requests a short edit and presents a complete downloadable MP4', async () => {
  let body;
  const h=harness(async (_,options)=>{body=JSON.parse(options.body);return response(videoReady);});
  h.get('open').onclick();await flush();
  assert.deepEqual(body,{content_id:'video-1',mode:'video'});
  assert.equal(h.get('video-player').hidden,false);
  assert.equal(h.get('inline').hidden,false);
  assert.equal(h.createdTags.includes('dialog'),false,'media shares the reading workspace without a modal');
  assert.equal(h.get('player').hidden,true);
  assert.equal(h.get('compilation').src,'http://127.0.0.1:8765'+videoReady.video_url);
  assert.equal(h.get('video-download').href,'http://127.0.0.1:8765'+videoReady.download_url);
  assert.equal(h.get('video-duration').textContent,'本次 1:30 · 原视频 15:00');
  assert.equal(h.get('compilation').paused,true);
  h.get('compilation').fire('error');
  assert.match(h.get('video-notice').textContent,/下载完整 MP4/);
  h.get('close').onclick();
  assert.equal(h.get('compilation').src,undefined);
});

test('audio tour holds screenshots for longer original audio and advances only when a clip ends', async () => {
  let body;
  const h=harness(async (_,options)=>{body=JSON.parse(options.body);return response(audioReady);});
  h.get('audio-open').onclick();await flush();
  assert.deepEqual(body,{content_id:'video-1',mode:'audio'});
  assert.equal(h.get('title').textContent,'<script>hello</script>');
  assert.equal(h.get('audio').src,'http://127.0.0.1:8765/api/media/assets/a.m4a?mode=audio');
  assert.match(h.get('source').href,/t=40s/);
  assert.equal(h.get('audio-duration').textContent,'本次 5:00 · 原视频 15:00');
  assert.equal(h.get('audio-download').href,'http://127.0.0.1:8765'+audioReady.download_url);
  assert.equal(h.get('text').textContent,'第一条中文字幕');
  assert.equal(h.get('dialog').open,false);
  assert.equal(h.get('inline').hidden,false);
  h.get('play').onclick();await flush();
  h.get('audio').currentTime=110;h.get('audio').fire('timeupdate');
  assert.equal(h.get('time').textContent,'1:50 / 5:00');
  assert.equal(h.get('title').textContent,'<script>hello</script>');
  h.get('audio').fire('ended');await flush();
  assert.equal(h.get('title').textContent,'Second');
  assert.equal(h.get('audio').paused,false);
  h.get('audio').fire('ended');assert.equal(h.get('progress').value,100);
  h.get('play').onclick();await flush();
  assert.equal(h.get('title').textContent,'<script>hello</script>');
  h.get('close').onclick();assert.equal(h.get('audio').src,undefined);
});

for (const caption of ['Original English captions.', 'English 与中文混合字幕']) {
  test('audio tour plays without rejecting caption language: ' + caption, async () => {
    const data = JSON.parse(JSON.stringify(audioReady));
    data.subtitle_language = 'mixed';
    data.slides[0].captions[0].text = caption;
    const h = harness(async () => response(data));
    h.get('audio-open').onclick();await flush();
    assert.equal(h.get('text').textContent, caption);
    assert.equal(h.get('player').hidden, false);
    h.get('play').onclick();await flush();
    assert.equal(h.get('audio').paused, false);
    h.get('close').onclick();
  });
}

test('switching formats stops both players and loads the separate format cache', async () => {
  const modes=[];
  const h=harness(async (_,options)=>{const mode=JSON.parse(options.body).mode;modes.push(mode);return response(mode==='video'?videoReady:audioReady);});
  h.get('open').onclick();await flush();await h.get('compilation').play();
  h.get('mode-audio').onclick();await flush();
  assert.equal(h.get('compilation').paused,true);assert.equal(h.get('compilation').src,undefined);
  assert.equal(h.get('mode-audio').getAttribute('aria-pressed'),'true');
  h.get('play').onclick();await flush();
  h.get('mode-video').onclick();await flush();
  assert.equal(h.get('audio').paused,true);assert.equal(h.get('audio').src,undefined);
  assert.equal(h.get('video-player').hidden,false);assert.equal(h.get('player').hidden,true);
  assert.deepEqual(modes,['video','audio','video']);h.get('close').onclick();
});

test('switching during preparation aborts and ignores the older format result', async () => {
  let resolveVideo,videoSignal;
  const h=harness((_,options)=>{
    if(JSON.parse(options.body).mode==='video'){videoSignal=options.signal;return new Promise(resolve=>{resolveVideo=resolve;});}
    return Promise.resolve(response(audioReady));
  });
  h.get('open').onclick();h.get('mode-audio').onclick();await flush();
  assert.equal(videoSignal.aborted,true);resolveVideo(response(videoReady));await flush();
  assert.equal(h.get('video-player').hidden,true);assert.equal(h.get('player').hidden,false);
  assert.equal(h.get('compilation').src,undefined);h.get('close').onclick();
});

test('status polls preserve selected format and are canceled on close', async () => {
  const calls=[];
  const h=harness(async (url,options)=>{calls.push([url,options]);return response({status:'working'});},{fakeTimers:true});
  h.get('audio-open').onclick();await flush();h.poll();await flush();
  assert.equal(new URL(calls[1][0]).searchParams.get('mode'),'audio');
  assert.equal(new URL(calls[1][0]).searchParams.get('content_id'),'video-1');
  assert.equal(calls[1][1].method,'GET');h.get('close').onclick();assert.equal(h.timers.size,0);
});

test('closing preparation aborts request and ignores a late result', async () => {
  let resolve,signal;
  const h=harness((_,options)=>{signal=options.signal;return new Promise(done=>{resolve=done;});});
  h.get('open').onclick();h.get('close').onclick();assert.equal(signal.aborted,true);
  resolve(response(videoReady));await flush();assert.equal(h.get('compilation').src,undefined);
});

test('articles explain unavailable source without requesting either generation mode', async () => {
  let calls=0;
  const h=harness(async()=>{calls++;return response(videoReady);},{kind:'article'});
  h.get('open').onclick();await flush();h.get('mode-audio').onclick();await flush();
  assert.equal(calls,0);assert.match(h.get('message').textContent,/没有可用的视频原声/);h.get('close').onclick();
});

test('source switching stops playback and releases loaded assets', async () => {
  const h=harness(async()=>response(audioReady));
  h.get('audio-open').onclick();await flush();h.get('play').onclick();await flush();
  h.context.currentDoc={id:'another-video'};h.changed();
  assert.equal(h.get('dialog').open,false);assert.equal(h.get('audio').paused,true);assert.equal(h.get('audio').src,undefined);
});

test('unavailable preparation displays a retryable reason', async () => {
  const h=harness(async()=>response({status:'unavailable',message:'需要安装 FFmpeg'}));
  h.get('open').onclick();await flush();assert.equal(h.get('message').textContent,'需要安装 FFmpeg');
  assert.equal(h.get('retry').hidden,false);h.get('close').onclick();
});

test('selection disclosure remains visible throughout audio playback', async () => {
  const message='语义筛选暂不可用，已按摘要关键词匹配片段。';
  const h=harness(async()=>response({...audioReady,message}));
  h.get('audio-open').onclick();await flush();assert.equal(h.get('method').hidden,false);
  h.get('play').onclick();await flush();assert.equal(h.get('method').textContent,message);
  h.get('audio').fire('ended');await flush();assert.equal(h.get('method').textContent,message);
  h.get('audio').fire('ended');assert.equal(h.get('method').textContent,message);h.get('close').onclick();
});

test('Chinese captions and reading highlight follow latest overlapping cue, then clear in gaps',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();
  assert.equal(h.summary.children[0].classList.contains('media-current'),true);
  assert.equal(h.summary.children[0].getAttribute('aria-current'),'step');
  const initialScrolls=h.reading.scrollCount;
  h.get('audio').currentTime=20;h.get('audio').fire('timeupdate');
  assert.equal(h.reading.scrollCount,initialScrolls,'same paragraph does not scroll repeatedly');
  h.get('audio').currentTime=59.5;h.get('audio').fire('timeupdate');
  assert.equal(h.get('text').textContent,'第二条中文字幕');
  assert.equal(h.summary.children[0].getAttribute('aria-current'),'false');
  assert.equal(h.summary.children[1].getAttribute('aria-current'),'step');
  h.get('audio').currentTime=115;h.get('audio').fire('timeupdate');
  assert.equal(h.get('text').textContent,'');
  assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  assert.match(h.get('current-summary').textContent,/未关联/);
  h.get('next').onclick();
  h.get('audio').currentTime=100;h.get('audio').fire('seeked');
  assert.equal(h.get('text').textContent,'不关联内容');
  assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false,'explicit null does not fall back to slide summary_index');
  h.get('close').onclick();
});

test('summary click seeks mapped relative cue and preserves paused or playing state',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();
  h.clickSummary(1);
  assert.equal(h.get('text').textContent,'第二条中文字幕','highlight updates before metadata arrives');
  assert.equal(h.summary.children[1].classList.contains('media-current'),true);
  assert.equal(h.get('audio').paused,true);
  h.get('audio').fire('loadedmetadata');await flush();
  assert.equal(h.get('audio').currentTime,59,'seeks cue offset, not original source timestamp');
  assert.equal(h.get('audio').paused,true);
  h.get('play').onclick();await flush();
  h.clickSummary(0);await flush();
  assert.equal(h.get('audio').currentTime,0);assert.equal(h.get('audio').paused,false);
  assert.equal(h.summary.children[0].classList.contains('media-current'),true);
  h.get('close').onclick();assert.equal(h.get('inline').hidden,true);
  assert.equal(h.context.document.body.classList.contains('media-reading-active'),false);
  assert.equal(h.summary.children[0].getAttribute('aria-current'),'step','original graph selection restored');
});

test('unmapped summary click explicitly reports missing coverage without seeking or replacing active cue',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();h.get('play').onclick();await flush();
  h.get('audio').currentTime=25;h.get('audio').fire('timeupdate');const before=h.get('audio').src;
  h.clickSummary(2);
  assert.equal(h.get('audio').currentTime,25);assert.equal(h.get('audio').src,before);assert.equal(h.get('audio').paused,false);
  assert.match(h.get('notice').textContent,/未收录/);assert.equal(h.summary.children[0].getAttribute('aria-current'),'step');
  assert.match(h.get('coverage').textContent,/2 \/ 3/);h.get('close').onclick();
});

test('stale summary text never maps to the wrong current reading paragraph',async()=>{
  const h=harness(async()=>response({...audioReady,summary_steps:['过时的摘要','另一段旧摘要']}));h.get('audio-open').onclick();await flush();
  assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  h.clickSummary(0);assert.match(h.get('notice').textContent,/未收录/);h.get('close').onclick();
});

test('video captions map stitched time to each source clip and summary click seeks exact cue',async()=>{
  const h=harness(async()=>response(videoReady));h.get('open').onclick();await flush();
  assert.equal(h.get('video-caption').textContent,'视频第一条中文字幕');
  assert.equal(h.summary.children[0].getAttribute('aria-current'),'step');
  h.get('compilation').currentTime=55;h.get('compilation').fire('timeupdate');
  assert.equal(h.get('video-caption').textContent,'视频第二条中文字幕');
  assert.equal(h.summary.children[1].getAttribute('aria-current'),'step');
  h.get('compilation').currentTime=72;h.get('compilation').fire('timeupdate');
  assert.equal(h.get('video-caption').textContent,'');
  assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  h.get('compilation').currentTime=80;h.get('compilation').fire('timeupdate');
  assert.equal(h.get('video-caption').textContent,'没有关联摘要的结尾');
  assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  h.clickSummary(1);
  assert.equal(h.get('video-caption').textContent,'视频第二条中文字幕','paused seek updates captions immediately');
  h.get('compilation').fire('loadedmetadata');await flush();
  assert.equal(h.get('compilation').currentTime,50,'stitched 45 + relative cue 5; never source 1000');
  assert.equal(h.get('compilation').paused,true);
  await h.get('compilation').play();h.get('compilation').readyState=1;h.clickSummary(0);await flush();
  assert.equal(h.get('compilation').currentTime,0);assert.equal(h.get('compilation').paused,false);
  h.clickSummary(2);assert.match(h.get('video-notice').textContent,/未收录/);assert.equal(h.get('compilation').currentTime,0);
  h.get('close').onclick();
});

test('switching modes clears timed caption highlight until new mapped media is ready',async()=>{
  let resolveVideo;
  const h=harness((_,options)=>JSON.parse(options.body).mode==='audio'?Promise.resolve(response(audioReady)):new Promise(resolve=>{resolveVideo=resolve;}));
  h.get('audio-open').onclick();await flush();assert.equal(h.summary.children[0].classList.contains('media-current'),true);
  h.get('mode-video').onclick();assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  h.get('close').onclick();resolveVideo(response(videoReady));await flush();
  assert.equal(h.get('inline').hidden,true);assert.equal(h.get('compilation').src,undefined);
});

test('opening either format immediately reveals left summary before loading or an unmapped cue',async()=>{
  let resolve;
  const h=harness(()=>new Promise(done=>{resolve=done;}));h.summary.offsetTop=420;
  h.get('open').onclick();
  assert.equal(h.reading.lastScroll.top,375);
  assert.equal(h.reading.lastScroll.behavior,'instant');
  assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  resolve(response({...videoReady,summary_steps:[]}));await flush();
  assert.equal(h.reading.lastScroll.top,375,'unmapped first cue leaves summary visible');
  h.get('mode-audio').onclick();assert.equal(h.reading.lastScroll.top,375);
  resolve(response({...audioReady,summary_steps:[]}));await flush();
  assert.equal(h.reading.lastScroll.top,375);h.get('close').onclick();
});

test('return to graph selects last audio summary even after a subtitle gap',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();
  h.clickSummary(1);h.get('audio').fire('loadedmetadata');
  h.get('audio').currentTime=115;h.get('audio').fire('timeupdate');
  assert.equal(h.get('text').textContent,'');assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  h.get('close').onclick();assert.equal(h.context.stepIndex,1);
  assert.deepEqual(h.selections.at(-1),{id:'video-1',index:1});
  assert.equal(h.summary.children[1].classList.contains('active'),true);
});

test('return to graph preserves last video summary across an explicitly unmapped cue',async()=>{
  const h=harness(async()=>response(videoReady));h.get('open').onclick();await flush();
  h.get('compilation').currentTime=55;h.get('compilation').fire('timeupdate');
  h.get('compilation').currentTime=80;h.get('compilation').fire('timeupdate');h.get('close').onclick();
  assert.equal(h.context.stepIndex,1);assert.deepEqual(h.selections.at(-1),{id:'video-1',index:1});
});

test('graph entry locates current summary without loading or playing the first unrelated clip',async()=>{
  const result=structuredClone(audioReady);result.slides[0].captions=result.slides[0].captions.slice(0,1);
  const h=harness(async()=>response(result));h.context.stepIndex=1;
  h.get('graph-audio').onclick();await flush();
  assert.deepEqual(h.get('audio').loadedSources,['http://127.0.0.1:8765/api/media/assets/b.m4a?mode=audio']);
  assert.equal(h.get('text').textContent,'第二段原声中文字幕');assert.equal(h.get('audio').paused,true);
  h.get('audio').fire('loadedmetadata');assert.equal(h.get('audio').currentTime,10);assert.equal(h.get('audio').paused,true);
  h.get('close').onclick();assert.equal(h.context.stepIndex,1);
});

test('unmapped graph target stays unplayed and returns to its original graph paragraph',async()=>{
  const h=harness(async()=>response(audioReady));h.context.stepIndex=2;h.get('graph-audio').onclick();await flush();
  assert.equal(h.get('audio').src,undefined);assert.equal(h.get('audio').paused,true);assert.match(h.get('notice').textContent,/未收录/);
  h.get('audio').fire('timeupdate');assert.equal(h.summary.children.some(b=>b.classList.contains('media-current')),false);
  h.get('close').onclick();assert.equal(h.context.stepIndex,2);
  h.get('graph-audio').onclick();await flush();h.get('play').onclick();await flush();
  assert.equal(h.get('audio').paused,false);h.get('close').onclick();
  assert.equal(h.context.stepIndex,0,'explicitly starting from the beginning updates the return point');
});

test('changing documents never applies old media return indices to the new graph',async()=>{
  let resolve;
  const h=harness(()=>new Promise(done=>{resolve=done;}));h.context.stepIndex=1;h.get('graph-audio').onclick();
  h.context.currentDoc={...h.context.currentDoc,id:'video-2'};h.context.stepIndex=2;h.changed();
  resolve(response(audioReady));await flush();
  assert.equal(h.get('inline').hidden,true);assert.equal(h.context.stepIndex,2);assert.deepEqual(h.selections,[]);
  assert.equal(h.get('audio').src,undefined);
});

test('late graph-target request cannot replace a newer unmapped target',async()=>{
  const requests=[];
  const h=harness(()=>new Promise(resolve=>requests.push(resolve)));
  h.context.stepIndex=1;h.get('graph-audio').onclick();h.get('close').onclick();
  h.context.stepIndex=2;h.get('graph-audio').onclick();
  requests[0](response(audioReady));await flush();assert.equal(h.get('audio').src,undefined);
  requests[1](response(audioReady));await flush();assert.match(h.get('notice').textContent,/第 3 段/);
  assert.equal(h.get('audio').src,undefined);h.get('close').onclick();assert.equal(h.context.stepIndex,2);
});

test('dragging within a playing clip pauses, previews stably, and resumes without reload',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();h.get('audio').readyState=1;h.get('play').onclick();await flush();
  const loads=h.get('audio').loadCount,range=h.get('progress');range.fire('pointerdown');range.value=20;range.fire('input');
  assert.equal(h.get('audio').paused,true);assert.equal(h.get('audio').currentTime,60);
  assert.equal(h.get('text').textContent,'第二条中文字幕');
  h.get('audio').currentTime=5;h.get('audio').fire('timeupdate');h.get('audio').fire('ended');
  assert.equal(range.value,20);assert.equal(h.get('time').textContent,'1:00 / 5:00');assert.equal(h.get('text').textContent,'第二条中文字幕');
  range.fire('pointerup');range.fire('change');await flush();
  assert.equal(h.get('audio').currentTime,60);assert.equal(h.get('audio').paused,false);assert.equal(h.get('audio').loadCount,loads);
  h.get('close').onclick();
});

test('keyboard range input seeks across clips and stays paused through pending metadata',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();const range=h.get('progress');
  range.value=60;range.fire('input');assert.match(h.get('audio').src,/b\.m4a/);assert.equal(h.get('text').textContent,'第二段原声中文字幕');
  assert.equal(h.summary.children[1].classList.contains('media-current'),true);range.fire('change');
  h.get('audio').fire('loadedmetadata');await flush();assert.equal(h.get('audio').currentTime,60);assert.equal(h.get('audio').paused,true);
  assert.equal(range.getAttribute('aria-valuetext'),'3:00 / 5:00');h.get('close').onclick();
});

test('rapid cross-clip drags apply only final seek before resuming playback',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();h.get('play').onclick();await flush();const range=h.get('progress');
  range.fire('pointerdown');range.value=60;range.fire('input');range.value=80;range.fire('input');range.value=20;range.fire('input');
  assert.match(h.get('audio').src,/a\.m4a/);assert.equal(h.get('audio').paused,true);range.fire('change');
  assert.equal(h.get('audio').paused,true,'waits for final target metadata before playback');
  h.get('audio').fire('loadedmetadata');await flush();assert.equal(h.get('audio').currentTime,60);assert.equal(h.get('audio').paused,false);
  assert.equal(h.get('text').textContent,'第二条中文字幕');assert.equal(h.summary.children[1].classList.contains('media-current'),true);h.get('close').onclick();
});

test('closing during a drag cancels pending resume and metadata seek',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();h.get('play').onclick();await flush();const range=h.get('progress');
  range.fire('pointerdown');range.value=60;range.fire('input');h.get('close').onclick();range.fire('pointerup');h.get('audio').fire('loadedmetadata');await flush();
  assert.equal(h.get('audio').src,undefined);assert.equal(h.get('audio').paused,true);assert.equal(h.get('inline').hidden,true);
});

test('vertical divider adjusts picture area height and restores the saved preference',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();
  assert.equal(h.get('player').classList.contains('media-height-custom'),false,'default keeps existing layout');
  const divider=h.get('height-divider');divider.fire('pointerdown',{clientY:300,button:0,preventDefault(){}});divider.fire('pointermove',{clientY:400,preventDefault(){}});divider.fire('pointerup');
  assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'360px');
  assert.equal(h.storage.get('ontokb.media.layoutHeight'),'360');h.get('close').onclick();
  const restored=harness(async()=>response(audioReady),{storedHeight:360});restored.get('audio-open').onclick();await flush();
  assert.equal(restored.get('player').style.getPropertyValue('--media-layout-height'),'360px');restored.get('close').onclick();
});

test('height divider keyboard controls respect limits and reset to default',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();const divider=h.get('height-divider');
  divider.fire('keydown',{key:'ArrowDown',preventDefault(){}});assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'280px');
  divider.fire('keydown',{key:'Home',preventDefault(){}});assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'160px');
  divider.fire('keydown',{key:'ArrowUp',preventDefault(){}});assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'160px');
  divider.fire('keydown',{key:'End',preventDefault(){}});assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'800px');
  divider.fire('keydown',{key:'ArrowDown',preventDefault(){}});assert.equal(Number(divider.getAttribute('aria-valuenow')),800);
  divider.fire('dblclick');assert.equal(h.get('player').classList.contains('media-height-custom'),false);assert.equal(h.storage.has('ontokb.media.layoutHeight'),false);h.get('close').onclick();
});

test('pointer height resizing clamps extremes and stops when the workspace closes',async()=>{
  const h=harness(async()=>response(audioReady));h.get('audio-open').onclick();await flush();const divider=h.get('height-divider');
  divider.fire('pointerdown',{clientY:300,preventDefault(){}});divider.fire('pointermove',{clientY:-10000,preventDefault(){}});assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'160px');
  divider.fire('pointermove',{clientY:10000,preventDefault(){}});assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'800px');
  h.get('close').onclick();divider.fire('pointermove',{clientY:320,preventDefault(){}});assert.equal(h.context.document.body.classList.contains('media-height-resizing'),false);
  assert.equal(h.get('player').style.getPropertyValue('--media-layout-height'),'800px');
});
