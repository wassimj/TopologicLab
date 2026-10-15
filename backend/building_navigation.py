"""TopologicPy navigation adapters and retained specialized planar analysis modes."""
import math
from collections import OrderedDict
from threading import RLock
import hashlib,json
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
from .ifc_geometry import shape,surface,height,polygons,EPS

MAX_RISE=.17
_cache=OrderedDict();_lock=RLock()

def canonical_model(model):
    data=model.model_dump() if hasattr(model,'model_dump') else model
    data=json.loads(json.dumps(data))
    for s in data['faces']:
        z=s.get('elevation',0);s['plane']=s.get('plane') or [0,0,z]
        s['outer']=[p if len(p)==3 else [*p,z] for p in s['outer']]
        s['holes']=[[p if len(p)==3 else [*p,z] for p in r] for r in s.get('holes',[])]
    if not data.get('storeys'):
        levels=sorted(set(round(s.get('elevation',0),4) for s in data['faces']))
        data['storeys']=[{'id':str(i),'name':f'Level {z:g} m','elevation':z} for i,z in enumerate(levels)]
        for s in data['faces']:s['storey']=str(levels.index(round(s.get('elevation',0),4)))
    return data

def ramp_samples(connector):
    """Compatibility display adapter; sampling itself belongs to Navigation.Graph."""
    from topologicpy.Navigation import Navigation
    from topologicpy.TGraph import TGraph
    ramp=Navigation.Ramp([api_face(f) for f in connector['surfaces']],storey=connector.get('storey'),source=connector.get('source'),group=connector.get('group'))
    far=api_face({'outer':[[1e6,1e6,0],[1e6+1,1e6,0],[1e6+1,1e6+1,0],[1e6,1e6+1,0]],'storey':'0'})
    model=Navigation.ByFaces([far],connectors=[ramp])
    graph=Navigation.Graph(model,spacing=2,graphType='tgraph')
    tiles=json.loads(TGraph.Dictionary(graph)['navigationTiles'])
    return [([d[k] for k in ('x','y','z')],[t for t in tiles if t['node']==i]) for i,v in enumerate(TGraph.Vertices(graph)) if (d:=v['dictionary'])['kind']=='ramp']


def planar_network(model,spacing,mode,storey,options):
    """Adapt the existing planar constructors and API-produced circulation graph."""
    from .analysis import analyze
    from .models import Analysis,Model,Boundary
    m=canonical_model(model);nodes=[];edges=[];tiles=[]
    floors=[s for s in m['faces'] if storey is None or s['storey']==storey]
    for s in floors:
        b=Boundary(id=0,outer=[p[:2] for p in s['outer']],holes=[[p[:2] for p in r] for r in s.get('holes',[])])
        segments=[[[p[0],p[1],0] for p in seg] for seg in m.get('segments',[]) if all(len(p)<3 or abs(p[2]-s['plane'][2])<.01 for p in seg)]
        if mode in {'segments','axial'} and not segments:continue
        request=Analysis(model=Model(name=m['name'],faces=[b],segments=segments),metric='Connectivity',spacing=spacing,graph_mode=mode,**(options or {}))
        result=analyze(request);offset=len(nodes)
        for i,p in enumerate(result['graph']['nodes']):
            e=result['elements'][i];node=len(nodes)
            nodes.append({'point':[p[0],p[1],height(s,p[0],p[1])],'kind':'floor','storey':s['storey']})
            if e.get('polygon'):tiles.append({'node':node,**surface(Polygon(e['polygon'],e.get('holes',[])),s['plane'],s['storey'])})
            elif e.get('line'):tiles.append({'node':node,'outer':[],'holes':[],'line':[[q[0],q[1],height(s,*q[:2])] for q in e['line']],'storey':s['storey']})
        edges.extend({'src':a+offset,'dst':b+offset,'length':math.dist(nodes[a+offset]['point'],nodes[b+offset]['point']),'kind':mode} for a,b in result['graph']['edges'])
    floor_count=len(nodes)
    if not nodes:raise ValueError('No usable network exists for this graph construction. Choose a navigation grid, visibility graph or generated axial lines.')
    circulation,_=build(m,spacing,'navigation',storey)
    mapping={}
    for i,n in enumerate(circulation['nodes']):
        if n['kind']!='floor':mapping[i]=len(nodes);nodes.append(n)
    # The library establishes which floor attachments exist. Substitute the
    # nearest reachable analytical node for each attached grid node.
    for edge in circulation['edges']:
        a,b=edge['src'],edge['dst']
        if a not in mapping and b not in mapping:continue
        for old,other in ((a,b),(b,a)):
            if old in mapping:continue
            n=circulation['nodes'][old];support=unary_union([shape(f) for f in floors if f['storey']==n['storey'] and abs(height(f,*n['point'][:2])-n['point'][2])<=MAX_RISE+EPS])
            candidates=sorted((j for j in range(floor_count) if nodes[j]['storey']==n['storey'] and abs(nodes[j]['point'][2]-n['point'][2])<=MAX_RISE+EPS),key=lambda j:math.dist(nodes[j]['point'],n['point']))
            for j in candidates:
                if support.buffer(EPS).covers(LineString([n['point'][:2],nodes[j]['point'][:2]])):
                    mapping[old]=len(nodes);nodes.append(n)
                    edges.append({'src':mapping[old],'dst':j,'length':math.dist(n['point'],nodes[j]['point']),'kind':'attachment'});break
        if a in mapping and b in mapping:
            edges.append({**edge,'src':mapping[a],'dst':mapping[b]})
    tiles.extend({**t,'node':mapping[t['node']]} for t in circulation['tiles'] if t['node'] in mapping and circulation['nodes'][t['node']]['kind']!='floor')
    return {'model':m,'nodes':nodes,'edges':edges,'tiles':tiles,'floor_count':floor_count},False


# Public TopologicPy API adapters. Records are the browser's display/transport format.
def wire_points(w):
    from topologicpy.Wire import Wire
    from topologicpy.Edge import Edge
    from topologicpy.Vertex import Vertex
    pairs=[[Vertex.Coordinates(Edge.StartVertex(e),mantissa=12),Vertex.Coordinates(Edge.EndVertex(e),mantissa=12)] for e in Wire.Edges(w)]
    a,b=pairs.pop(0);points=[a,b]
    while pairs:
        i,flip=min(((i,k) for i in range(len(pairs)) for k in (0,1)),key=lambda item:math.dist(points[-1],pairs[item[0]][item[1]]))
        pair=pairs.pop(i);points.append(pair[1-flip])
    return points[:-1]


def restore_boundary_types(face,record):
    from topologicpy.Face import Face
    from topologicpy.Topology import Topology
    from topologicpy.Dictionary import Dictionary
    roles=record.get('hole_types',[])
    if not roles or not record.get('holes'):return face
    rings=[Polygon([p[:2] for p in ring]) for ring in record.get('holes',[])]
    for wire in Face.InternalBoundaries(face):
        poly=Polygon([p[:2] for p in wire_points(wire)])
        index=min(range(len(rings)),key=lambda i:poly.symmetric_difference(rings[i]).area)
        role=roles[index] if index<len(roles) else 'obstacle'
        metadata=Dictionary.PythonDictionary(Topology.Dictionary(wire),silent=True) or {}
        Topology.SetDictionary(wire,Dictionary.ByPythonDictionary({**metadata,'isovistType':role}))
    return face


def api_face(record):
    from topologicpy.Face import Face
    from topologicpy.Wire import Wire
    from topologicpy.Vertex import Vertex
    from topologicpy.Topology import Topology
    from topologicpy.Dictionary import Dictionary
    transport=record
    if record.get('brep'):
        f=Topology.ByBREPString(record['brep'],silent=True)
        if f is None:raise ValueError('Could not restore imported navigation geometry.')
        return restore_boundary_types(Topology.SetDictionary(f,Dictionary.ByPythonDictionary({k:record[k] for k in ('storey','source','kind') if record.get(k) is not None})),transport)
    z=record.get('elevation',0)
    poly=shape(record).buffer(0).simplify(1e-6,preserve_topology=True)
    if poly.geom_type!='Polygon' or poly.is_empty:raise ValueError('Expected one nonempty walkable surface.')
    record={**record,**surface(poly,record.get('plane') or [0,0,z],record.get('storey','0'))}
    def wire(r):
        return Wire.ByVertices([Vertex.ByCoordinates(*(p if len(p)==3 else [*p,z])) for p in r],close=True,tolerance=1e-7,silent=True)
    f=Face.ByWires(wire(record['outer']),[wire(r) for r in record.get('holes',[])],tolerance=1e-7,silent=True)
    if f is None:raise ValueError('Could not restore a walkable surface.')
    return restore_boundary_types(Topology.SetDictionary(f,Dictionary.ByPythonDictionary({k:record[k] for k in ('storey','source','kind') if record.get(k) is not None})),transport)


def face_record(face):
    from topologicpy.Face import Face
    from topologicpy.Topology import Topology
    from topologicpy.Dictionary import Dictionary
    inners=Face.InternalBoundaries(face)
    outer=wire_points(Face.ExternalBoundary(face));holes=[wire_points(w) for w in inners]
    roles=[Dictionary.ValueAtKey(Topology.Dictionary(w),'isovistType',defaultValue='obstacle',silent=True) or 'obstacle' for w in inners]
    normal=Face.Normal(face,mantissa=12);a,b=-normal[0]/normal[2],-normal[1]/normal[2];c=outer[0][2]-a*outer[0][0]-b*outer[0][1]
    native=Topology.Dictionary(face)
    d=(native.copy() if isinstance(native,dict) else Dictionary.PythonDictionary(native)) or {}
    return {**d,'brep':Topology.BREPString(face),'outer':outer,'holes':holes,'hole_types':roles,'plane':[a,b,c],'elevation':c,'storey':str(d.get('storey','0'))}


def navigation_model(model):
    from topologicpy.Navigation import Navigation
    m=canonical_model(model);connectors=[]
    for c in m.get('connectors',[]):
        if c['type']=='ramp':
            connectors.append(Navigation.Ramp([api_face(s) for s in c['surfaces']],storey=c.get('storey'),source=c.get('source'),group=c.get('group')))
        else:
            connectors.append(Navigation.Stair(api_face(c),storey=c.get('storey'),source=c.get('source'),group=c.get('group'),kind=c.get('kind','tread')))
    for c in m.get('lifts',[]):
        if 'cabins' in c:connectors.append(Navigation.Lift(c['doors'],c['cabins'],c.get('storeys'),source=c.get('source'),footprint=api_face(c['footprint']) if c.get('footprint') else None))
    api_floors=m.get('navigation_faces') or m['faces']
    nav=Navigation.ByFaces([api_face(s) for s in api_floors],obstacles=[api_face(s) for s in m.get('obstacles',[])],connectors=connectors,storeys=m['storeys'],storeyIDs=[s['storey'] for s in api_floors])
    nav.metadata.update(unit='m',eyeHeight=1.6)
    if m.get('navigation_ifc'):
        nav._ifc=m['navigation_ifc'].copy()
        # JSON object keys are strings; the IFC mesh source identifiers are integers.
        nav._ifc['_void_meshes']={int(k):v for k,v in nav._ifc.get('_void_meshes',{}).items()}
        nav._ifc['_obstacle_faces']=tuple(id(f) for f in nav.obstacles)
    return nav


def build(model,spacing=4,mode='navigation',storey=None,options=None,clearance=0):
    from topologicpy.Navigation import Navigation
    from topologicpy.TGraph import TGraph
    m=canonical_model(model)
    key=hashlib.sha256(json.dumps([m,spacing,mode,storey,options,clearance],sort_keys=True).encode()).hexdigest()
    with _lock:
        if key in _cache:return _cache[key],True
    if mode not in {'navigation','grid_shell','visibility'}:
        # Existing segment/axial constructors remain public TopologicPy calls.
        if clearance:raise ValueError('Clearance applies to navigation and visibility grids. Choose one of those graph types.')
        return planar_network(model,spacing,mode,storey,options)
    if sum(shape(f).area/spacing**2 for f in m['faces'])>200000:raise ValueError('Grid is too dense. Increase spacing.')
    graph=Navigation.Graph(navigation_model(m),spacing=spacing,storey=storey,mode='visibility' if mode=='visibility' else 'navigation',graphType='tgraph',clearance=clearance)
    nodes=[]
    for v in TGraph.Vertices(graph):
        d=v['dictionary'];nodes.append({**d,'point':[d[k] for k in ('x','y','z')]})
    if len(nodes)>10000:raise ValueError('More than 10000 navigation points. Increase spacing.')
    if not nodes:raise ValueError('No walkable grid remains. Reduce clearance or grid spacing.')
    edges=[{'src':e['src'],'dst':e['dst'],'length':e['dictionary']['Length'],'kind':e['dictionary'].get('kind','floor')} for e in TGraph.Edges(graph)]
    entry={'model':m,'nodes':nodes,'edges':edges,'tiles':json.loads(TGraph.Dictionary(graph).get('navigationTiles','[]')),'floor_count':sum(n['kind']=='floor' for n in nodes),'api_graph':graph}
    with _lock:
        _cache[key]=entry
        while len(_cache)>3:_cache.popitem(last=False)
    return entry,False
