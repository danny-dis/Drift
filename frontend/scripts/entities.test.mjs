import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import test from 'node:test';
const require=createRequire(import.meta.url);
const {buildSync}=require('esbuild');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
function load(name) {
 const result=buildSync({entryPoints:[`src/${name}`],bundle:true,write:false,platform:'node',format:'cjs',external:['react','react-dom'],loader:{'.css':'empty'},logLevel:'silent'});
 const module={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,module,module.exports);return module.exports;
}
test('new screens render honest loading states with no server calls during initial rendering',()=>{
 const previous=globalThis.fetch;let calls=0;globalThis.fetch=()=>{calls++;throw Error('Unexpected network call');};
 try {
  for(const [name,props,label] of [
   ['EntityScreen.tsx',{kind:'idea'},'Loading ideas'],
   ['EntityScreen.tsx',{kind:'project',id:'p1'},'Loading project'],
   ['EntityScreen.tsx',{kind:'thought',id:'c1'},'Loading thought'],
   ['MindMap.tsx',{},'Loading saved data'],
   ['WikiScreen.tsx',{},'Generate wiki page'],
   ['WikiScreen.tsx',{id:'w1'},'Loading saved data'],
  ]) {
   const html=renderToStaticMarkup(React.createElement(load(name).default,{headers:()=>({}),...props}));
   assert.ok(html.includes(label),name);assert.ok(!html.includes('No saved wiki pages'),name);
  }
  assert.equal(calls,0);
 }finally{globalThis.fetch=previous;}
});
test('capture wrappers retain immutable originals and use current text for list labels',()=>{
 const {unwrapEntity,entityLabel}=load('entity-api.ts');
 const capture=unwrapEntity({capture:{id:'a/b',text:'  Exact\noriginal  ',current_text:'Edited version'}},'thought');
 assert.equal(capture.text,'  Exact\noriginal  ');assert.equal(entityLabel(capture),'Edited version');
 assert.equal(entityLabel({id:'old',text:'Legacy original'}),'Legacy original');
 assert.throws(()=>unwrapEntity({id:'a',text:'Raw unwrapped body'},'thought'),/unreadable/);
});
test('all capture pages are loaded before client-side search/archive totals; authentication is retained',async()=>{
 const {listEntities}=load('entity-api.ts');const previous=globalThis.fetch;const requests=[];
 const first=Array.from({length:100},(_,i)=>({id:`c${i}`,text:`Thought ${i}`,archived:i%2===0}));
 globalThis.fetch=async(url,options)=>{
  requests.push({url,options});const offset=new URL(url,'http://fixture').searchParams.get('offset');
  return Response.json({captures:offset==='0'?first:[{id:'c100',text:'Search beyond first page',archived:true}],total:101,has_more:offset==='0'});
 };
 try {
  const captures=await listEntities('thought',()=>({Authorization:'Bearer fixture-token'}),new AbortController().signal);
  assert.equal(captures.length,101);assert.equal(captures.at(-1).text,'Search beyond first page');
  assert.equal(requests.length,2);assert.match(requests[1].url,/offset=100/);
  assert.ok(requests.every(r=>r.url.includes('include_archived=true')&&r.options.headers.Authorization==='Bearer fixture-token'));
 }finally{globalThis.fetch=previous;}
});
test('unreadable or stalled pagination rejects rather than showing a fake empty list',async()=>{
 const {listEntities}=load('entity-api.ts');const previous=globalThis.fetch;
 try {
  globalThis.fetch=async()=>Response.json({captures:[],total:3,has_more:true});
  await assert.rejects(listEntities('thought',()=>({}),new AbortController().signal),/did not advance/);
  globalThis.fetch=async()=>Response.json({});
  await assert.rejects(listEntities('idea',()=>({}),new AbortController().signal),/unreadable list/);
  let repeats=0;
  globalThis.fetch=async()=>{if(++repeats>3)throw new Error('Repeated forever');return Response.json({captures:[{id:'same',text:'Same page'}],has_more:true,total:2});};
  await assert.rejects(listEntities('thought',()=>({}),new AbortController().signal),/did not advance/);
 }finally{globalThis.fetch=previous;}
});
test('API failures distinguish authorization, conflict, missing and validation failures',async()=>{
 const {api}=load('entity-api.ts');const previous=globalThis.fetch;
 try {
  for(const [status,expected] of [[401,/token required/],[403,/Access denied/],[404,/unavailable/],[409,/changed.*edits are kept/],[422,/422.*inputs are kept/],[500,/500.*inputs are kept/]]) {
   globalThis.fetch=async()=>Response.json({detail:'fixture detail'},{status});
   await assert.rejects(api('/fixture',()=>({})),expected);
  }
 }finally{globalThis.fetch=previous;}
});
