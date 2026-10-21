export const SECTIONS = [
 {id:'inbox',label:'Thoughts'}, {id:'ideas',label:'Ideas'}, {id:'projects',label:'Projects'},
 {id:'mind-map',label:'Mind map'}, {id:'wiki',label:'Wiki'}, {id:'office',label:'Office'},
 {id:'research',label:'Research'}, {id:'attention',label:'Activity & budget'},
 {id:'approvals',label:'Needs approval'}, {id:'status',label:'Workspace'},
] as const;
export type Section = typeof SECTIONS[number]['id'];
export type Route = {section:Section; id?:string};
export function parseRoute(hash:string):Route {
 try {
  const [raw,entity] = hash.replace(/^#\/?/,'').split('/');
  const aliases:Record<string,string> = {thoughts:'inbox',workspace:'status','research-start':'research'};
  const section = aliases[raw] || raw;
  if (!SECTIONS.some(item=>item.id===section)) return {section:'inbox'};
  return {section:section as Section,...(entity ? {id:decodeURIComponent(entity)} : {})};
 } catch {return {section:'inbox'};}
}
export function routeHref(route:Route) {return `#/${route.section}${route.id ? `/${encodeURIComponent(route.id)}` : ''}`;}
