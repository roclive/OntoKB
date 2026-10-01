const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/ontokb/web/reading.js'),'utf8');
const code=source.slice(source.indexOf('const memoryInclusions='),source.indexOf('function entityContextMenu('));
function setup(records,ok=true){
  const calls=[];const info={setAttribute(){},textContent:''};
  const ctx={info,apiUrl:p=>p,fetch:async(url,options)=>{calls.push({url,options});return {ok:options?ok:true,json:async()=>options?(ok?{ok:true}:{error:'revision conflict'}):{records}};}};
  vm.createContext(ctx);vm.runInContext(code,ctx);return {ctx,calls,info};
}
const record={key:'current',revision:7,current:true,snapshot:{kind:'entity',title:'Example'},stance:'uncertain',note:'Keep my note'};
test('includes current entity and preserves existing judgment',async()=>{
  const {ctx,calls,info}=setup([{...record,key:'old',current:false},record]);
  await Promise.all([ctx.includeEntityMemory({id:'Example'}),ctx.includeEntityMemory({id:'Example'})]);
  assert.equal(calls.length,2);
  assert.deepEqual(JSON.parse(calls[1].options.body),{key:'current',revision:7,reviewed:true,included:true,stance:'uncertain',note:'Keep my note',source_id:''});
  assert.match(info.textContent,/已审核，已纳入个人记忆并保存/);
});
test('missing entity does not write; failed save does not report success',async()=>{
  const missing=setup([]);await missing.ctx.includeEntityMemory({id:'Example'});assert.equal(missing.calls.length,1);assert.match(missing.info.textContent,/失败/);
  const failed=setup([record],false);await failed.ctx.includeEntityMemory({id:'Example'});assert.match(failed.info.textContent,/revision conflict/);
  await failed.ctx.includeEntityMemory({id:'Example'});assert.equal(failed.calls.length,4);
});
