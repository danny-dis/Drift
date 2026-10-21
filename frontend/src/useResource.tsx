import {useEffect,useState} from 'react';
import {api,type Headers} from './entity-api';
export function useResource<T>(path:string,headers:Headers) {
 const [value,setValue]=useState<T|null>(null);const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [revision,setRevision]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setValue(null);setError('');setLoading(true);
  api<T>(path,headers,'GET',undefined,controller.signal).then(setValue).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[path,headers,revision]);
 return {value,error,loading,retry:()=>setRevision(value=>value+1)};
}
export function ResourceState({loading,error,retry}:{loading:boolean;error:string;retry:()=>void}) {
 return <>{loading&&<p role="status">Loading saved data…</p>}{error&&<div role="alert"><p className="error">{error}</p><button onClick={retry}>Retry</button></div>}</>;
}
