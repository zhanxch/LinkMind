import test from 'node:test';
import assert from 'node:assert/strict';
import {createStudioDock} from '../plugin/studio-dock.mjs';

function createStore(initial) {
  let value=initial; const listeners=new Set();
  return {getSnapshot:()=>value,set(next){value=next;for(const listener of listeners)listener();},subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);}};
}
function fixture() {
  const current=createStore({key:'a'}),sessions=createStore({byId:{a:{projectionValues:{agentPreset:'linkmind-embodied'}},b:{projectionValues:{agentPreset:'linkmind-embodied'}},plain:{projectionValues:{agentPreset:'standard'}}}});
  const mounted=createStore('a'),openTabs=createStore([]),tabs={a:[{id:'file-a',kind:'files'}],b:[{id:'file-b',kind:'files'}],plain:[]};
  const host=new Set(),closed=[],queue=[];let serial=0,fail=false;
  const sidebar={mounted,openTabs,tabsIn:id=>tabs[id],openTab(kind){if(fail)throw Error('Disconnected');const id=mounted.getSnapshot();const tab={id:'term-'+(++serial),kind,title:id+' shell',host:'dock',cwd:id};tabs[id].push(tab);host.add(tab.id);openTabs.set(Object.values(tabs).flat());},float(id){const tab=tabs[mounted.getSnapshot()].find(t=>t.id===id);if(tab)tab.host='float';},focus(id){sidebar.focused=id;},close(id){closed.push(id);host.delete(id);const owner=mounted.getSnapshot();tabs[owner]=tabs[owner].filter(t=>t.id!==id);openTabs.set(Object.values(tabs).flat());}};
  const dock=createStudioDock({sidebar,current,sessions,createStore,schedule:fn=>queue.push(fn)});
  const flush=()=>{while(queue.length)queue.shift()();};flush();
  return {dock,sidebar,tabs,host,closed,flush,fail(value){fail=value;},switchTo(id){current.set({key:id});mounted.set(id);flush();}};
}

test('switching lower panels reuses the terminal and leaves the upper file and process intact',()=>{
  const f=fixture();f.dock.openTerminal();f.flush();
  const first=f.dock.store.getSnapshot().selected;
  assert.equal(f.dock.store.getSnapshot().panel,'terminal');
  assert.equal(f.tabs.a[0].id,'file-a');
  assert.equal(f.tabs.a[1].host,'float');
  for(let i=0;i<4;i++){f.dock.showChat();assert.equal(f.dock.store.getSnapshot().panel,'chat');f.dock.openTerminal();}
  assert.equal(f.host.size,1);assert.equal(f.dock.store.getSnapshot().selected,first);assert.deepEqual(f.closed,[]);
  f.dock.dispose();
});
test('explicit new, select and close affect only the chosen terminal',()=>{
  const f=fixture();f.dock.openTerminal();const first=f.dock.store.getSnapshot().selected;
  f.dock.openTerminal({create:true});const second=f.dock.store.getSnapshot().selected;
  assert.notEqual(first,second);assert.equal(f.host.size,2);
  f.dock.openTerminal({tabId:first});f.dock.closeTerminal();
  assert.deepEqual(f.closed,[first]);assert.equal(f.dock.store.getSnapshot().selected,second);
  f.dock.closeTerminal();assert.equal(f.dock.store.getSnapshot().panel,'chat');assert.equal(f.host.size,0);
  f.dock.dispose();
});
test('session switching keeps workspace terminals and panel choices separate',()=>{
  const f=fixture();f.dock.openTerminal();const a=f.dock.store.getSnapshot().selected;
  f.switchTo('b');assert.equal(f.dock.store.getSnapshot().panel,'chat');assert.equal(f.dock.store.getSnapshot().terminals.length,0);
  f.dock.openTerminal();assert.equal(f.tabs.b[1].cwd,'b');
  f.switchTo('a');assert.equal(f.dock.store.getSnapshot().selected,a);assert.equal(f.tabs.a[1].cwd,'a');assert.equal(f.host.size,2);
  f.switchTo('plain');assert.equal(f.dock.openTerminal(),false);assert.equal(f.tabs.plain.length,0);
  f.dock.dispose();
});
test('agent or recovered terminals are placed below without interrupting the chat',()=>{
  const f=fixture();f.sidebar.openTab('terminal');f.flush();
  assert.equal(f.dock.store.getSnapshot().panel,'chat');assert.equal(f.tabs.a[1].host,'float');
  f.dock.openTerminal();assert.equal(f.host.size,1);
  f.dock.dispose();
});
test('creation errors keep chat accessible and can be retried',()=>{
  const f=fixture();f.fail(true);assert.equal(f.dock.openTerminal(),false);
  assert.equal(f.dock.store.getSnapshot().panel,'chat');assert.match(f.dock.store.getSnapshot().error,/Disconnected/);
  f.fail(false);assert.equal(f.dock.openTerminal(),true);assert.equal(f.dock.store.getSnapshot().error,'');
  f.dock.dispose();
});
test('unrelated session updates do not republish unchanged panel state',()=>{
  const f=fixture();f.dock.openTerminal();f.flush();let updates=0;
  const release=f.dock.store.subscribe(()=>updates++);
  for(let i=0;i<5;i++){f.sidebar.openTabs.set([]);f.flush();}
  assert.equal(updates,0);release();f.dock.dispose();
});
