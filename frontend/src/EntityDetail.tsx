import {useEffect,useRef,useState} from 'react';
import {api,entityLabel,entityPath,sections,unwrapEntity,type Entity,type Headers,type Kind} from './entity-api';
import EntityForm from './EntityForm';
import ThoughtInsights from './ThoughtInsights';
import ProjectIntelligence from './ProjectIntelligence';
import {routeHref} from './navigation';
type Detail={events?:{summary:string}[];ideas?:Entity[];drift_md?:string;intelligence?:Record<string,unknown>};
export default function EntityDetail({kind,id,headers,onChanged}:{kind:Kind;id:string;headers:Headers;onChanged:()=>void}) {
 const [item,setItem]=useState<Entity|null>(null);const [detail,setDetail]=useState<Detail>({});
 const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [version,setVersion]=useState(0);
 const [editing,setEditing]=useState(false);const [confirm,setConfirm]=useState(false);const [busy,setBusy]=useState(false);
 const heading=useRef<HTMLHeadingElement>(null);const cancel=useRef<HTMLButtonElement>(null);const archiveButton=useRef<HTMLButtonElement>(null);
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');
  api<Detail>(entityPath(kind,id),headers,'GET',undefined,controller.signal).then(value=>{
   setItem(unwrapEntity(value,kind));setDetail(value);
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[kind,id,version,headers]);
 useEffect(()=>{if(item&&!loading)heading.current?.focus();},[id,item?.id,loading]);
 useEffect(()=>{if(confirm)cancel.current?.focus();},[confirm]);
 const changeArchive=async()=>{
  if(!item||busy)return;setBusy(true);setError('');
  try {
   await api(`${entityPath(kind,id)}${item.archived?'/restore':''}`,headers,item.archived?'POST':'DELETE',{confirm:true,...(!item.archived?{expected_revision:item.revision??0}:{})});
   setItem(unwrapEntity(await api(entityPath(kind,id),headers),kind));setConfirm(false);onChanged();heading.current?.focus();
  }catch(e){setError(e instanceof Error?e.message:'Change was not confirmed. Retry.');}finally{setBusy(false);}
 };
 return <article className="entity-detail" aria-busy={loading}>
  <a href={routeHref({section:sections[kind]})}>← All {kind==='thought'?'thoughts':`${kind}s`}</a>
  {loading&&<p role="status">Loading {kind}…</p>}
  {error&&<div role="alert" className="error">{error}{item&&<p>Previously loaded details may be stale.</p>}</div>}
  {error&&<button onClick={()=>setVersion(v=>v+1)} disabled={busy}>Reload latest</button>}
  {item&&<>
   <h3 ref={heading} tabIndex={-1} className="entity-title">{entityLabel(item)}</h3>
   <p>{item.archived?'Archived':'Active'} · revision {item.revision??0}</p>
   {editing?<EntityForm key={`${kind}:${id}`} kind={kind} item={item} headers={headers} onCancel={()=>{setEditing(false);heading.current?.focus();}} onSaved={saved=>{setItem(saved);setEditing(false);onChanged();heading.current?.focus();}} />:<>
    {kind==='project'?<dl><dt>Repository</dt><dd>{item.repo||'Not linked'}</dd><dt>Local folder</dt><dd>{item.local_path||'Not linked'}</dd><dt>Priority</dt><dd>{item.importance??'Unavailable'}</dd></dl>:<pre tabIndex={0} aria-label={kind==='thought'?'Current thought':'Full idea'}>{entityLabel(item)}</pre>}
    <div className="entity-actions">
     <button onClick={()=>setEditing(true)} disabled={busy||confirm||!!item.archived}>Edit {kind}</button>
     <button ref={archiveButton} disabled={busy} onClick={()=>item.archived?void changeArchive():setConfirm(true)}>{busy?'Updating…':item.archived?`Restore ${kind}`:`Archive ${kind}`}</button>
    </div>
   </>}
   {confirm&&<section className="archive-confirm" role="group" aria-label={`Confirm archive ${kind}`}>
    <h4>Archive this {kind}?</h4><p>This hides the {kind} from active lists and the mind map. It remains saved and can be restored from Archived. Related records and already queued tasks are not erased or cancelled. Restore does not approve paused tasks.</p>
    <div className="entity-actions"><button ref={cancel} disabled={busy} onClick={()=>{setConfirm(false);archiveButton.current?.focus();}}>Cancel</button><button disabled={busy} onClick={()=>void changeArchive()}>Confirm archive</button></div>
   </section>}
   {kind==='thought'&&<section><h4>Full original thought</h4><pre tabIndex={0} aria-label="Full original thought">{item.text}</pre>
    <h4>AI suggestions for the original capture</h4><p className="helper">Earlier suggestions refer to the immutable original, not edits to the current version.</p>
    <ThoughtInsights captureId={id} status={item.status||'captured'} headers={headers} />
    {item.idea_id&&<a href={routeHref({section:'ideas',id:item.idea_id})}>Open related idea</a>}
   </section>}
   {kind==='idea'&&item.related_projects?.length ? <section><h4>Related projects</h4><ul>{item.related_projects.map(pid=><li key={pid}><a href={routeHref({section:'projects',id:pid})}>{pid}</a></li>)}</ul></section>:null}
   {kind==='project'&&<>
    <ProjectIntelligence key={id} projectId={id} value={detail.intelligence} headers={headers} publishAvailable={!!item.local_path}/>
    <h4>Related ideas</h4><ul>{detail.ideas?.map(idea=><li key={idea.id}><a href={routeHref({section:'ideas',id:idea.id})}>{entityLabel(idea)}</a></li>)}</ul>
    <h4>Project events</h4><ul>{detail.events?.map((event,index)=><li key={index}>{event.summary}</li>)}</ul>
    <details><summary>Saved drift.md summary</summary><pre>{detail.drift_md||'No saved summary yet.'}</pre></details>
   </>}
  </>}
 </article>;
}
