import {useEffect,useRef,useState} from 'react';
import {entityLabel,listEntities,sections,type Entity,type Headers,type Kind} from './entity-api';
import EntityForm from './EntityForm';import EntityDetail from './EntityDetail';import {routeHref} from './navigation';
export default function EntityScreen({kind,id,headers,refreshKey=0,composer}:{kind:Kind;id?:string;headers:Headers;refreshKey?:number;composer?:React.ReactNode}) {
 const [items,setItems]=useState<Entity[]>([]);const [loaded,setLoaded]=useState(false);const [loading,setLoading]=useState(true);const [error,setError]=useState('');
 const [revision,setRevision]=useState(0);const [q,setQ]=useState('');const [archived,setArchived]=useState(false);const [page,setPage]=useState(0);const [adding,setAdding]=useState(false);
 const addButton=useRef<HTMLButtonElement>(null);
 const title=kind==='thought'?'Thoughts':kind==='idea'?'Ideas':'Projects';
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);setError('');
  listEntities(kind,headers,controller.signal).then(value=>{setItems(value);setLoaded(true);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[kind,headers,revision,refreshKey]);
 const changed=()=>setRevision(value=>value+1);
 const filtered=items.filter(item=>!!item.archived===archived&&[entityLabel(item),item.text,item.repo,item.local_path].some(value=>value?.toLowerCase().includes(q.toLowerCase())));
 const currentPage=Math.min(page,Math.max(0,Math.ceil(filtered.length/20)-1));const visible=filtered.slice(currentPage*20,currentPage*20+20);
 return <>
  <h2 className="panel-title" aria-label={title}>{title}<span>Save, revisit, and keep the useful parts.</span></h2>
  <div className="pad">
  {id?<EntityDetail key={`${kind}:${id}`} kind={kind} id={id} headers={headers} onChanged={changed}/>:<>
   <div className="entity-toolbar"><div className="entity-search"><label htmlFor={`search-${kind}`}>Search all {title.toLowerCase()}</label><input id={`search-${kind}`} type="search" value={q} onChange={e=>{setQ(e.target.value);setPage(0);}} /></div>
   <label className="archive-filter"><input type="checkbox" checked={archived} onChange={e=>{setArchived(e.target.checked);setPage(0);}}/> Archived</label>
   <button ref={addButton} className="primary" onClick={()=>setAdding(value=>!value)}>{adding?'Close add form':`Add ${kind}`}</button></div>
   {adding&&(kind==='thought'?<div>{composer}<button onClick={()=>{setAdding(false);addButton.current?.focus();}}>Close composer</button></div>:<EntityForm kind={kind} headers={headers} onCancel={()=>{setAdding(false);addButton.current?.focus();}} onSaved={item=>{changed();setAdding(false);window.location.hash=routeHref({section:sections[kind],id:item.id});}}/>)}
   {loading&&<p role="status">Loading {title.toLowerCase()}…</p>}
   {error&&<div role="alert"><p className="error">{error}</p>{loaded&&<p>Previously loaded results may be stale.</p>}<button onClick={changed}>Retry</button></div>}
   {!loading&&!error&&filtered.length===0&&<p className="empty-state">{q?'No matches. Try another search.':archived?'No archived items.':'Nothing here yet. Use Add to get started.'}</p>}
   {loaded&&<><p className="helper">{filtered.length} {archived?'archived':'active'} {title.toLowerCase()}{q?' matching your search':''}</p><ul className="entity-list" aria-busy={loading}>{visible.map(item=><li key={item.id}><a href={routeHref({section:sections[kind],id:item.id})}>{entityLabel(item)}</a><small>{item.status||kind} · revision {item.revision??0}</small></li>)}</ul>
    <nav className="entity-pagination" aria-label={`${title} pages`}><button disabled={loading||currentPage===0} onClick={()=>setPage(currentPage-1)}>Previous</button><span>{filtered.length?`${currentPage*20+1}–${currentPage*20+visible.length}`:'0'} of {filtered.length}</span><button disabled={loading||(currentPage+1)*20>=filtered.length} onClick={()=>setPage(currentPage+1)}>Next</button></nav>
   </>}
  </>}
  </div>
 </>;
}
