export type Headers = () => Record<string,string>;
export type Entity = {id:string; text?:string; current_text?:string; name?:string; repo?:string; local_path?:string; importance?:number; revision?:number; archived?:boolean; status?:string; related_projects?:string[]; idea_id?:string; task_id?:string; created_at?:string};
export type Kind = 'thought'|'idea'|'project';
export const resources = {thought:'captures',idea:'ideas',project:'projects'};
export const sections = {thought:'inbox',idea:'ideas',project:'projects'} as const;
export function entityLabel(item:Entity) {return item.name ?? item.current_text ?? item.text ?? item.id;}
export async function api<T>(url:string,headers:Headers,method='GET',body?:unknown,signal?:AbortSignal):Promise<T> {
 const response=await fetch(url,{method,headers:headers(),...(body===undefined ? {} : {body:JSON.stringify(body)}),signal});
 if(!response.ok) {
  let detail='';try{const data=await response.json();if(typeof data.detail==='string')detail=data.detail;}catch{}
  const message=response.status===409 ? 'This item changed in another session. Your edits are kept. Reload latest before trying again.'
   : response.status===401 ? 'Session token required. Open Connection settings, then retry. Your inputs are kept.'
   : response.status===403 ? 'Access denied. Check your token or allowed project folder. Your inputs are kept.'
   : response.status===404 ? 'This item or endpoint is unavailable (404). Retry or return to the list.'
   : `Request failed (${response.status}). Your inputs are kept.${detail ? ` ${detail}`:''}`;
  throw new Error(message);
 }
 return response.json();
}
export function entityPath(kind:Kind,id?:string) {return `/api/ui/${resources[kind]}${id ? `/${encodeURIComponent(id)}`:''}`;}
export function unwrapEntity(value:unknown,kind:Kind):Entity {
 const item=(value as Record<string,unknown>)?.[kind==='thought'?'capture':kind] as Entity;
 if(!item || typeof item.id!=='string' || (kind==='project'?typeof item.name!=='string':typeof item.text!=='string'))throw new Error('Drift returned an unreadable item. Retry; your inputs are kept.');
 return item;
}
export async function listEntities(kind:Kind,headers:Headers,signal:AbortSignal):Promise<Entity[]> {
 const all:Entity[]=[];const seen=new Set<string>();let offset=0;
 do {
  const page=await api<Record<string,unknown>>(`${entityPath(kind)}?include_archived=true&limit=100&offset=${offset}`,headers,'GET',undefined,signal);
  const rows=page[resources[kind]];
  if(!Array.isArray(rows) || rows.some(item=>!item || typeof item.id!=='string')) throw new Error('Drift returned an unreadable list. Retry.');
  if(page.has_more && !rows.some(item=>!seen.has(item.id))) throw new Error('History pagination did not advance. Retry.');
  rows.forEach(item=>seen.add(item.id));
  all.push(...rows);offset+=rows.length;
  if(!page.has_more)break;
 }while(true);
 return [...new Map(all.map(item=>[item.id,item])).values()];
}
