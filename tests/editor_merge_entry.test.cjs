const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../src/ontokb/web/editor.js'),'utf8');
function setup(overrides={}){
  const saved={name:'EROFS',type:'DefinedTerm',aliases:[]};
  const calls=[];
  const ctx={selected:{id:1,...saved},kind:'entities',data:{entities:[{id:1,...saved},{id:2,name:'overlayfs',type:'DefinedTerm'}]},baseline:JSON.stringify(saved),busy:false,memoryDirty:false,draft:{...saved,name:'overlayfs'},values(){return this.draft;},isDocument:row=>row?.type==='Article',showMerge:(...ids)=>calls.push(['open',...ids]),previewMerge:()=>calls.push(['preview']),guard:action=>calls.push(['guard',action]),...overrides};
  // values() is called as a plain function by the editor.
  ctx.values=()=>ctx.draft;
  vm.createContext(ctx);
  vm.runInContext(code.slice(code.indexOf('  function renamedMergeTarget('),code.indexOf('  function aliasConflictAction(')),ctx);
  return {ctx,calls};
}
test('conflicting rename opens original source and existing target and loads read-only preview',()=>{
  for(const explicitTarget of [undefined,2]){
    const {ctx,calls}=setup();ctx.beginMerge(1,explicitTarget);
    assert.deepEqual(calls,[['open',1,2],['preview']]);
  }
});
test('matching name handles case, Unicode width and whitespace',()=>{
  const {ctx,calls}=setup();ctx.draft.name='  ＯＶＥＲＬＡＹＦＳ  ';ctx.beginMerge(1);
  assert.deepEqual(calls,[['open',1,2],['preview']]);
});
test('additional unsaved edits or memory edits retain the leave guard',()=>{
  for(const change of [{aliases:['filesystem']},{type:'Thing'},{verificationStatus:'verified'}]){
    const {ctx,calls}=setup();Object.assign(ctx.draft,change);ctx.beginMerge(1,2);
    assert.equal(calls.length,1);assert.equal(calls[0][0],'guard');
    calls[0][1]();assert.deepEqual(calls.slice(1),[['open',1,2],['preview']]);
  }
  const {ctx,calls}=setup({memoryDirty:true});ctx.beginMerge(1,2);assert.equal(calls[0][0],'guard');
});
test('other names, sources and targets cannot bypass unsaved edit protection',()=>{
  for(const ids of [[1,3],[3,2]]){const {ctx,calls}=setup();ctx.beginMerge(...ids);assert.equal(calls[0][0],'guard');}
  const {ctx,calls}=setup();ctx.draft.name='new name';ctx.beginMerge(1);assert.equal(calls[0][0],'guard');
  calls[0][1]();assert.deepEqual(calls.slice(1),[['open',1,undefined]]);
});
test('busy editor does not navigate or start requests',()=>{
  const {ctx,calls}=setup({busy:true});ctx.beginMerge(1,2);assert.deepEqual(calls,[]);
});
test('all merge entry buttons share the corrected flow',()=>{
  assert.match(code,/button\.onclick=\(\)=>beginMerge\(row\.id\)/);
  assert.match(code,/action\.onclick=\(\)=>beginMerge\(sourceId,owner\.id\)/);
  assert.match(code,/byId\('ke-merge-open'\)\.onclick=\(\)=>beginMerge/);
});
