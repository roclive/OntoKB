const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../src/ontokb/web/editor.js'),'utf8');
function setup(library,sources=library){
  const inputs={};
  for(const id of ['ke-category','ke-article'])inputs[id]={options:[],value:'',replaceChildren(){this.options=[];},add(o){this.options.push(o);}};
  const ctx={data:{sources},DATA:{library},category:'',article:'',kind:'entities',entitySources:new Map(),byId:id=>inputs[id],Option:function(label,value){this.label=label;this.value=value;}};
  vm.createContext(ctx);
  vm.runInContext(code.slice(code.indexOf('  function articleSources('),code.indexOf("  const filters=")),ctx);
  vm.runInContext(code.slice(code.indexOf('  function selectOptions('),code.indexOf('\n',code.indexOf('  function selectOptions('))),ctx);
  return {ctx,inputs};
}
test('legacy articles without status appear once across repeated renders',()=>{
  const docs=Array.from({length:4},(_,i)=>({id:String(i),title:'Article '+i}));
  const {ctx,inputs}=setup(docs);
  ctx.renderArticleFilters();ctx.renderArticleFilters();
  assert.equal(inputs['ke-article'].options.length,5);
  assert.deepEqual(inputs['ke-article'].options.map(o=>o.value),['','0','1','2','3']);
  ctx.article='2';ctx.renderArticleFilters();assert.equal(inputs['ke-article'].value,'2');
  ctx.entitySources.set('10',new Set(['2']));
  for(const kind of ['entities','claims']){ctx.kind=kind;assert.equal(ctx.articleMatches({id:10}),true);assert.equal(ctx.articleMatches({id:11}),false);}
  ctx.kind='triples';assert.equal(ctx.articleMatches({source:'2'}),true);assert.equal(ctx.articleMatches({source:'1'}),false);
});
test('uses workbench categories and resets articles outside selected category',()=>{
  const {ctx,inputs}=setup([{id:'a',title:'A',categories:['AI类']},{id:'b',title:'B',categories:['经济类']}],[{id:'a'},{id:'b'}]);
  ctx.article='a';ctx.category='经济类';ctx.renderArticleFilters();
  assert.equal(ctx.article,'');assert.deepEqual(inputs['ke-article'].options.map(o=>o.value),['','b']);
  ctx.category='';ctx.renderArticleFilters();assert.equal(inputs['ke-article'].options.length,3);
  delete ctx.DATA;ctx.renderArticleFilters();assert.equal(inputs['ke-article'].options.length,3);
});
