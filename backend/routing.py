"""Cached TopologicPy grid construction and shortest-path API calls."""
import hashlib
import math
import json
import os
import tempfile
import time
from pathlib import Path
from collections import OrderedDict
from threading import RLock
from importlib.metadata import version
from topologicpy.TGraph import TGraph
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Edge import Edge
from topologicpy.Wire import Wire
from topologicpy.Core import Core
from .geometry import make_face,slice_grid,face_data,coordinates,contains_point

_cache=OrderedDict()
_lock=RLock()

def graph_data(graph):
    records=TGraph.Vertices(graph);edges=TGraph.Edges(graph)
    index={v['index']:i for i,v in enumerate(records)}
    data={'nodes':[[v['dictionary']['x'],v['dictionary']['y']] for v in records],
          'edges':[[index[e['src']],index[e['dst']]] for e in edges]}
    if TGraph.Dictionary(graph).get('graph_type')=='isovist_intersection':
        data['node_attributes']=[v['dictionary'] for v in records]
        data['edge_attributes']=[e['dictionary'] for e in edges]
    return data

def visibility_graph(host,points):
    graph=TGraph.VisibilityGraph(host,vertices=[Vertex.ByCoordinates(*p,0) for p in points],includeBoundaryVertices=False,trim=True,ontology=False,storeEdgeRepresentations=False)
    if graph is None:raise ValueError('TGraph.VisibilityGraph returned no graph.')
    return graph

def prepare(a,boundary):
    payload={'schema':'topologicpy-native-host-2','api':version('topologicpy'),'backend':type(Core.Backend()).__name__,'boundary':boundary.model_dump(),'spacing':a.spacing,'graph':a.path_graph}
    key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    with _lock:
        if key in _cache:
            entry=_cache.pop(key);_cache[key]=entry
            return entry,True
        timing={};start=time.perf_counter();host=make_face(boundary)
        timing['host_seconds']=time.perf_counter()-start
        start=time.perf_counter();shell,samples=slice_grid(host,a.spacing)
        timing['slice_seconds']=time.perf_counter()-start
        start=time.perf_counter();graph=None;disk_reused=False
        root=os.environ.get('TOPOLOGICLAB_ROUTE_CACHE_DIR',os.environ.get('SPATIAL_ROUTE_CACHE_DIR',str(Path.home()/'.cache'/'topologiclab'/'routing')))
        cache_file=Path(root)/f'{key}.json' if root else None
        if cache_file is not None:
            try:graph=TGraph.ByJSONData(json.loads(cache_file.read_text(encoding='utf-8')),ontology=False)
            except (OSError,ValueError,TypeError,KeyError):pass
            disk_reused=graph is not None
        if graph is None:
            graph=visibility_graph(host,[p for p,_ in samples]) if a.path_graph=='visibility' else TGraph.ByTopology(shell,direct=a.path_graph!='navigation',viaSharedTopologies=a.path_graph=='navigation',useInternalVertex=True,ontology=False,silent=True,host=host)
        if graph is None:raise ValueError('TGraph.ByTopology returned no graph.')
        timing['topology_graph_seconds']=time.perf_counter()-start
        if cache_file is not None and not disk_reused:
            temporary=None
            try:
                cache_file.parent.mkdir(parents=True,exist_ok=True)
                if len(list(cache_file.parent.glob('*.json')))<20:
                    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=cache_file.parent,suffix='.tmp',delete=False) as output:
                        temporary=Path(output.name);json.dump(TGraph.JSONData(graph),output,separators=(',',':'))
                    temporary.replace(cache_file);temporary=None
            except (OSError,TypeError,ValueError):pass
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
        entry={'host':host,'shell':shell,'samples':samples,'graph':graph,'display':graph_data(graph),'grid':[face_data(f) for _,f in samples],'disk_reused':disk_reused,'construction_timings':timing}
        _cache[key]=entry
        while len(_cache)>3:_cache.popitem(last=False)
        return entry,False

def shortest_route(a,boundary,started):
    build_start=time.perf_counter();entry,reused=prepare(a,boundary)
    timings={'graph_seconds':time.perf_counter()-build_start,'graph_reused':reused,'disk_reused':entry['disk_reused']}
    if not reused:timings.update(entry['construction_timings'])
    for label,p in [('start',a.path_start),('end',a.path_end)]:
        if p is None or len(p)!=2 or not all(math.isfinite(v) for v in p):raise ValueError(f'Choose a valid path {label}.')
        if not contains_point(entry['host'],p):raise ValueError(f'The path {label} must lie inside the floor plan.')
    search_start=time.perf_counter()
    # The API performs endpoint snapping and Dijkstra search.
    route=TGraph.ShortestPath(entry['graph'],[*a.path_start,0],[*a.path_end,0],edgeKey='Length',useAStar=False,snapEndpoints=True,silent=True)
    timings['search_seconds']=time.perf_counter()-search_start
    if not route:raise ValueError('No path connects the snapped grid endpoints.')
    records={v['index']:v for v in TGraph.Vertices(entry['graph'])}
    raw=[[records[i]['dictionary']['x'],records[i]['dictionary']['y']] for i in route]
    if len(raw)<2:raise ValueError('Both points snapped to the same graph vertex. Choose a more distant destination or finer grid.')
    raw_wire=Wire.ByVertices([Vertex.ByCoordinates(*p,0) for p in raw],close=False,silent=True)
    raw_length=Wire.Length(raw_wire)
    path=raw_wire;timings['straighten_seconds']=0
    if a.straighten:
        straight_start=time.perf_counter()
        path=Wire.Straighten(raw_wire,host=entry['host'],tolerance=.0001,silent=True)
        if path is None:raise ValueError('Wire.Straighten returned no path.')
        timings['straighten_seconds']=time.perf_counter()-straight_start
    if not Topology.Contains(entry['host'],path,tolerance=.0001,silent=True):
        raise ValueError('The TopologicPy path leaves the navigable floor. Try finer spacing or report this API result for investigation.')
    points=[coordinates(v) for v in Wire.Vertices(path)]
    if points and math.dist(points[-1],raw[0])<math.dist(points[0],raw[0]):points.reverse()
    length=Wire.Length(path)
    elements=[]
    for i,(p,q) in enumerate(zip(points,points[1:])):
        edge=Edge.ByVertices([Vertex.ByCoordinates(*p,0),Vertex.ByCoordinates(*q,0)])
        segment_length=Edge.Length(edge)
        elements.append({'id':i,'point':coordinates(Topology.Centroid(edge)),'line':[p,q],'value':segment_length,'metrics':{'segment_length_m':segment_length,'total_path_length_m':length}})
    return {'elements':elements,'graph':entry['display'],'grid':entry['grid'],'metric':'PathLength','name':'Shortest path','unit':'m','source':'topologicpy','engine_version':version('topologicpy'),
            'route':{'points':points,'raw_points':raw,'length':length,'raw_length':raw_length,'straightened':a.straighten,'start':raw[0],'end':raw[-1],'requested_start':a.path_start,'requested_end':a.path_end,'snapped':True},
            'parameters':a.model_dump(exclude={'model'}),'timings':timings,'elapsed':time.perf_counter()-started}
