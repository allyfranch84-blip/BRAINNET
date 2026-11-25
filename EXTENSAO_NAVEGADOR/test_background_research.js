const assert = require('node:assert/strict');
const {test} = require('node:test');
const {runBackgroundResearch, commandIsFresh} = require('./background_research');
const command = () => ({query:'test', deadline_epoch_ms:Date.now()+60000});
function fake({active=false, redirect=false, empty=false, stuck=false, moved=false}={}) {
  const calls=[];
  const current={id:12,windowId:moved?8:7,active,status:stuck?'loading':'complete',url:redirect?'https://consent.google.com/':'https://www.google.com/search?q=test'};
  return {calls,api:{windows:{getLastFocused:async()=>({id:7})},tabs:{query:async()=>[{id:1}],create:async args=>{calls.push(['create',args]);return {id:12};},get:async()=>current,remove:async id=>calls.push(['remove',id])},scripting:{executeScript:async args=>{calls.push(['extract',args.target.tabId]);return [{result:{url:current.url,title:'Google',links:empty?[]:[{title:'Example',url:'https://example.org'}]}}];}}}};
}
test('uses inactive owned tab and removes only it',async()=>{const f=fake();const r=await runBackgroundResearch(command(),f.api,async()=>{});assert.equal(r.ok,true);assert.equal(r.browser_active_tab_unchanged,true);assert.equal(f.calls[0][1].active,false);assert.deepEqual(f.calls.slice(1),[['extract',12],['remove',12]]);});
test('preserves a tab taken over by user',async()=>{const f=fake({active:true});const r=await runBackgroundResearch(command(),f.api,async()=>{});assert.equal(r.ok,false);assert.equal(r.cleanup,'USER_TAB_PRESERVED');assert.equal(f.calls.length,1);});
test('rejects redirect without extraction',async()=>{const f=fake({redirect:true});const r=await runBackgroundResearch(command(),f.api,async()=>{});assert.equal(r.ok,false);assert.deepEqual(f.calls.slice(1),[['remove',12]]);});
test('empty results and navigation timeout are failures',async()=>{for(const flags of [{empty:true},{stuck:true}]){const f=fake(flags);const r=await runBackgroundResearch(command(),f.api,async()=>{});assert.equal(r.ok,false);assert.equal(r.cleanup,'OWNED_TAB_REMOVED');}});
test('preserves an inactive tab moved to another window',async()=>{const f=fake({moved:true});const r=await runBackgroundResearch(command(),f.api,async()=>{});assert.equal(r.ok,false);assert.equal(r.cleanup,'USER_TAB_PRESERVED');assert.equal(f.calls.length,1);});
test('expired or absent deadline cannot open a tab',async()=>{const f=fake();for(const c of [{query:'test'},{query:'test',deadline_epoch_ms:Date.now()-1}]){const r=await runBackgroundResearch(c,f.api,async()=>{});assert.equal(r.ok,false);}assert.deepEqual(f.calls,[]);assert.equal(commandIsFresh({deadline_epoch_ms:100},100),false);});
