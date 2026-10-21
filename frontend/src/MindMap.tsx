import {type Headers} from './entity-api';
import {routeHref,type Route} from './navigation';
import {ResourceState,useResource} from './useResource';
type Node={id:string;kind:string;label:string;target:Route};
type Graph={nodes:Node[];edges:{source:string;target:string;relation:string}[]};
export default function MindMap({headers}:{headers:Headers}) {
 const resource=useResource<Graph>('/api/ui/mind-map',headers);const graph=resource.value;
 const valid=graph&&Array.isArray(graph.nodes)&&Array.isArray(graph.edges);
 return <><h2 className="panel-title" aria-label="Mind map">Mind map<span>Connections from saved records</span></h2><div className="pad">
  <p className="page-intro">Only stored relationships appear here. Nearby nodes are not necessarily connected. Open a node to view its full record.</p>
  <ResourceState {...resource}/>
  {graph&&!valid&&<p role="alert">Drift returned an unreadable map. <button onClick={resource.retry}>Retry</button></p>}
  {valid&&<>
   {!graph.nodes.length?<p className="empty-state">No active entities yet. Add a thought, idea, or project to start your map.</p>:<>
    <div className="knowledge-map" aria-label="Saved knowledge map">
     <svg viewBox={`0 0 900 ${Math.max(180,Math.ceil(graph.nodes.length/3)*140)}`} role="img" aria-label={`${graph.nodes.length} nodes and ${graph.edges.length} stored connections; equivalent links and relationships follow below`}>
      {graph.edges.map((edge,index)=>{const a=graph.nodes.findIndex(n=>n.id===edge.source);const b=graph.nodes.findIndex(n=>n.id===edge.target);return a<0||b<0?null:<line key={index} x1={150+a%3*300} y1={65+Math.floor(a/3)*140} x2={150+b%3*300} y2={65+Math.floor(b/3)*140}/>;})}
      {graph.nodes.map((node,index)=><a key={node.id} href={routeHref(node.target)} aria-label={`${node.kind}: ${node.label}`}><rect x={25+index%3*300} y={30+Math.floor(index/3)*140} width="250" height="70" rx="8"/><text x={150+index%3*300} y={58+Math.floor(index/3)*140} textAnchor="middle">{node.kind}</text><text x={150+index%3*300} y={82+Math.floor(index/3)*140} textAnchor="middle">{node.label.slice(0,27)}{node.label.length>27?'…':''}</text></a>)}
     </svg>
    </div>
    <h3>All nodes</h3><ul className="map-list">{graph.nodes.map(node=><li key={node.id}><a href={routeHref(node.target)} aria-label={`${node.kind}: ${node.label}`}>{node.kind}: {node.label}</a></li>)}</ul>
    <h3>Stored relationships</h3>{!graph.edges.length&&<p>No saved relationships yet. No connections have been inferred.</p>}<ul>{graph.edges.map((edge,index)=>{const a=graph.nodes.find(n=>n.id===edge.source),b=graph.nodes.find(n=>n.id===edge.target);return <li key={index}>{a?<a href={routeHref(a.target)}>{a.label}</a>:edge.source} — <b>{edge.relation}</b> → {b?<a href={routeHref(b.target)}>{b.label}</a>:edge.target}</li>;})}</ul>
   </>}
  </>}
 </div></>;
}
