import {useEffect,useRef,useState} from 'react';
import {api,sections,type Headers,type Kind} from './entity-api';
import {routeHref} from './navigation';import {ResourceState,useResource} from './useResource';
type Page={id:string;title:string;status:string;text?:string;summary?:string;revision?:number;project_id?:string;task_id?:string;verified?:boolean;stale?:boolean;omitted_source_count?:number;truncated_source_count?:number;errors?:string[];partial_text?:string;sources?:{kind:string;id:string;label:string;revision?:number;url?:string}[]};
function WikiPage({id,headers}:{id:string;headers:Headers}) {
 const resource=useResource<{page:Page}>(`/api/ui/wiki/${encodeURIComponent(id)}`,headers);const page=resource.value?.page;const heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{if(page)heading.current?.focus();},[page?.id]);
 return <article><a href={routeHref({section:'wiki'})}>← All wiki pages</a><ResourceState {...resource}/>
 {page&&<><h3 ref={heading} tabIndex={-1} className="entity-title">{page.title}</h3><p>Status: {page.status}</p><p className="helper">Unverified model output. Review its sources before relying on this page. Saving or reading does not start generation.</p>
 {page.stale&&<p className="cost-warning" role="status">Sources have changed since this page was generated. This saved answer may be out of date; review the current sources before using it.</p>}
 {!!page.omitted_source_count&&<p className="helper">{page.omitted_source_count} sources omitted because they did not fit the context limit.</p>}
 {!!page.truncated_source_count&&<p className="helper">{page.truncated_source_count} source excerpt{page.truncated_source_count===1?'':'s'} shortened to fit. Open the saved sources for their full text.</p>}
 {!!page.errors?.length&&<section aria-label="Generation issues"><h4>Generation needs review</h4><ul>{page.errors.map((error,index)=><li key={index}>{error}</li>)}</ul>{page.task_id?<a href={routeHref({section:'approvals'})}>Review blocked tasks</a>:<a href={routeHref({section:'wiki'})}>Back to Wiki to queue a new page</a>}</section>}
 {page.partial_text&&<details><summary>Read unfinished output</summary><p>This is an incomplete attempt, not a finished wiki page.</p><pre className="wiki-text" tabIndex={0}>{page.partial_text}</pre></details>}
 {page.task_id&&<p>Task: {page.task_id}. <a href={routeHref({section:'attention'})}>Review activity & budget</a></p>}
 {page.project_id&&<p><a href={routeHref({section:'projects',id:page.project_id})}>Open source project</a></p>}
 <button onClick={resource.retry} disabled={resource.loading}>Refresh saved page</button>
 {page.text?<pre tabIndex={0} className="wiki-text">{page.text}</pre>:<p>No generated text saved yet. {page.status==='blocked'?'Generation is blocked; review its task and budget.':page.status==='failed'?'Generation failed. Review activity for details.':'Work may be queued or pending; refresh to check saved progress.'}</p>}
 <h4>Sources</h4>{!page.sources?.length&&<p>No source references saved.</p>}<ul>{page.sources?.map((source,index)=>{
 const kind=(source.kind==='capture'?'thought':source.kind) as Kind;
 const destination=sections[kind];
 return <li key={index}>{destination?<a href={routeHref({section:destination,id:source.id})}>{source.label}</a>:source.url&&/^https?:\/\//.test(source.url)?<a href={source.url} target="_blank" rel="noreferrer">{source.label}</a>:<span>{source.label} ({source.kind}: {source.id})</span>}{source.revision!==undefined&&` · revision ${source.revision}`}</li>;
 })}</ul></>}
 </article>;
}
function WikiGeneration({headers,onCancel}:{headers:Headers;onCancel:()=>void}) {
 const [title,setTitle]=useState('');const [project,setProject]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const cancel=useRef<HTMLButtonElement>(null);
 const projects=useResource<{projects:{id:string;name:string;archived?:boolean}[]}>('/api/ui/projects',headers);
 useEffect(()=>cancel.current?.focus(),[]);
 const generate=async()=>{
  if(busy)return;setBusy(true);setError('');
  try {
   const result=await api<{page:Page;task_id:string}>('/api/ui/wiki/generate',headers,'POST',{title,...(project.trim()?{project_id:project.trim()}:{}),confirm:true});
   if(!result.page?.id)throw new Error('Generation response unreadable. Check Activity before retrying to avoid duplicate work.');
   // Open the saved resource immediately; retrying its read must never queue AI twice.
   window.location.hash=routeHref({section:'wiki',id:result.page.id});
  }catch(e){setError(e instanceof Error?e.message:'Queueing was not confirmed. Check Activity before retrying.');}finally{setBusy(false);}
 };
 return <form onSubmit={e=>{e.preventDefault();void generate();}}><h3>Generate a wiki page</h3>
 <p className="cost-warning">This explicitly queues AI work. It may send saved context to your configured provider and consume model-call allowance or incur cost, subject to workspace free-only and budget protections. Generation may remain blocked or fail. Nothing runs until you confirm.</p>
 <fieldset disabled={busy}><label htmlFor="wiki-title">Page title</label><input id="wiki-title" value={title} onChange={e=>setTitle(e.target.value)} required maxLength={200}/>
 <label htmlFor="wiki-project">Project scope</label><select id="wiki-project" value={project} onChange={e=>setProject(e.target.value)} disabled={projects.loading}><option value="">All active saved work</option>{projects.value?.projects?.filter(item=>!item.archived).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
 <ResourceState {...projects}/>
 <div className="entity-actions"><button type="button" ref={cancel} onClick={onCancel}>Cancel</button><button type="submit">{busy?'Queueing…':'Confirm and queue generation'}</button></div></fieldset>{error&&<p role="alert" className="error">{error}</p>}
 </form>;
}
export default function WikiScreen({id,headers}:{id?:string;headers:Headers}) {
 const resource=useResource<{pages:Page[]}>('/api/ui/wiki',headers);const [generating,setGenerating]=useState(false);const [q,setQ]=useState('');const button=useRef<HTMLButtonElement>(null);
 return <><h2 className="panel-title" aria-label="Wiki">Wiki<span>Source-linked, unverified knowledge</span></h2><div className="pad">
 {id?<WikiPage key={id} id={id} headers={headers}/>:<>
  <div className="entity-toolbar"><div className="entity-search"><label htmlFor="wiki-search">Search saved pages</label><input id="wiki-search" type="search" value={q} onChange={e=>setQ(e.target.value)}/></div><button ref={button} className="primary" onClick={()=>setGenerating(true)}>Generate wiki page</button></div>
  <p className="helper">Reading saved pages does not call AI. <a href={routeHref({section:'attention'})}>Review current budget and activity</a> before generation; availability is checked when work runs.</p>
  {generating&&<WikiGeneration headers={headers} onCancel={()=>{setGenerating(false);button.current?.focus();}}/>}
  <ResourceState {...resource}/>
  {resource.value&&!Array.isArray(resource.value.pages)&&<p role="alert">Unreadable wiki index. <button onClick={resource.retry}>Retry</button></p>}
  {Array.isArray(resource.value?.pages)&&<><ul className="entity-list">{resource.value.pages.filter(page=>`${page.title} ${page.summary??''}`.toLowerCase().includes(q.toLowerCase())).map(page=><li key={page.id}><a href={routeHref({section:'wiki',id:page.id})}>{page.title}</a><small>{page.status} · revision {page.revision??0}</small>{page.summary&&<p>{page.summary}</p>}</li>)}</ul>{!resource.value.pages.length&&<p className="empty-state">No saved wiki pages. You can explicitly queue generation above; it may use AI allowance.</p>}</>}
 </>}
 </div></>;
}
