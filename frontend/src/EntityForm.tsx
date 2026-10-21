import {useEffect,useRef,useState} from 'react';
import {api,entityLabel,entityPath,unwrapEntity,type Entity,type Headers,type Kind} from './entity-api';
type Props={kind:Kind;item?:Entity;headers:Headers;onSaved:(item:Entity)=>void;onCancel:()=>void};
export default function EntityForm({kind,item,headers,onSaved,onCancel}:Props) {
 const [text,setText]=useState(item?.current_text ?? item?.text ?? '');
 const [name,setName]=useState(item?.name ?? '');const [repo,setRepo]=useState(item?.repo ?? '');
 const [path,setPath]=useState(item?.local_path ?? '');const [importance,setImportance]=useState(String(item?.importance ?? .5));
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const first=useRef<HTMLInputElement & HTMLTextAreaElement>(null);
 const [baseRevision,setBaseRevision]=useState(item?.revision??0);const [latest,setLatest]=useState<Entity|null>(null);
 useEffect(()=>first.current?.focus(),[]);
 const reloadLatest=async()=>{
  if(!item||busy)return;setBusy(true);
  try {const value=unwrapEntity(await api(entityPath(kind,item.id),headers),kind);setLatest(value);setBaseRevision(value.revision??0);setError('');}
  catch(e){setError(e instanceof Error?e.message:'Latest version could not be loaded.');}finally{setBusy(false);}
 };
 const save=async()=>{
  if(busy)return;setBusy(true);setError('');
  try {
   const fields=kind==='project'?{name,repo,local_path:path,importance:Number(importance)}:{text};
   const value=await api<unknown>(entityPath(kind,item?.id),headers,item?'PATCH':'POST',{...fields,...(item?{expected_revision:baseRevision}:{})});
   const saved=unwrapEntity(value,kind);
   const verified=unwrapEntity(await api(entityPath(kind,saved.id),headers),kind);
   onSaved(verified);
  }catch(e){setError(e instanceof Error?e.message:'Save could not be confirmed. Your inputs are kept.');}finally{setBusy(false);}
 };
 return <form className="entity-form" onSubmit={e=>{e.preventDefault();void save();}}>
  <h3>{item?'Edit':'Add'} {kind}</h3>
  <fieldset disabled={busy}>
  {kind==='project'?<>
   <label htmlFor="entity-name">Name</label><input ref={first} id="entity-name" value={name} onChange={e=>setName(e.target.value)} required />
   <label htmlFor="entity-repo">Code repository (optional)</label><input id="entity-repo" value={repo} onChange={e=>setRepo(e.target.value)} />
   <label htmlFor="entity-path">Project folder (optional)</label><input id="entity-path" value={path} onChange={e=>setPath(e.target.value)} />
   <p className="helper">Only existing folders allowed by this workspace can be linked.</p>
   <label htmlFor="entity-importance">Priority (0–1)</label><input id="entity-importance" type="number" min="0" max="1" step="0.1" value={importance} onChange={e=>setImportance(e.target.value)} required />
  </>:<><label htmlFor="entity-text">{kind==='thought'?'Current thought text':'Idea text'}</label><textarea ref={first} id="entity-text" value={text} onChange={e=>setText(e.target.value)} required />
   {kind==='thought'&&<p className="helper">Editing the current version does not replace your original capture or rewrite earlier AI suggestions.</p>}</>}
  <div className="entity-actions"><button className="primary" type="submit">{busy?'Saving…':item?'Save changes':`Add ${kind}`}</button><button type="button" onClick={onCancel}>Cancel</button></div>
  </fieldset>{error&&<p role="alert" className="error">{error}</p>}
  {item&&error.includes('changed')&&<button type="button" disabled={busy} onClick={()=>void reloadLatest()}>Reload latest revision (keep my edits)</button>}
  {latest&&<section><h4>Latest saved version · revision {latest.revision??0}</h4><pre aria-label="Latest saved version">{kind==='project'?JSON.stringify(latest,null,2):entityLabel(latest)}</pre><p>Your edits above are unchanged. Review differences, then Save changes to replace the current version.</p></section>}
 </form>;
}
