import assert from 'node:assert/strict';
import test from 'node:test';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundle=await build({entryPoints:[fileURLToPath(new URL('../src/office/character.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node'});
const {drawCharacter}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
function origin(activity){
  const translations=[];
  const context=new Proxy({translate:(...p)=>translations.push(p),createRadialGradient:()=>({addColorStop(){}})}, {get:(o,k)=>k in o?o[k]:()=>{},set:(o,k,v)=>(o[k]=v,true)});
  drawCharacter(context,{state:'idle',position:{x:2.6,y:8.9},alert:false,conversing:false,activity:{type:activity,detail:''}},{x:2.6,y:8.9},0,{walking:false});
  return translations[0];
}
test('waiting and idle both sit on the elevated couch, never through its cushion',()=>{
  assert.deepEqual(origin('waiting'),origin('idle'));
});

test('typing paws meet the projected keyboard instead of typing below the desk',()=>{
  let offset=[0,0];const stack=[],ends=[];
  const context=new Proxy({save(){stack.push([...offset])},restore(){offset=stack.pop()||[0,0]},translate(x,y){offset=[offset[0]+x,offset[1]+y]},quadraticCurveTo(_x,_y,x,y){ends.push([x+offset[0],y+offset[1]])},createRadialGradient:()=>({addColorStop(){}})}, {get:(o,k)=>k in o?o[k]:()=>{},set:(o,k,v)=>(o[k]=v,true)});
  drawCharacter(context,{state:'thinking',position:{x:7.4,y:3.55},alert:false,conversing:false,activity:{type:'writing',detail:''}},{x:7.4,y:3.55},0,{walking:false});
  for(const index of [0,2]) assert.ok(ends[index][1]<350,`Paw below keyboard: ${ends[index]}`);
});
