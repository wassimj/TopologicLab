"""Whole-building analyses and geometric Dijkstra routing."""
import math,time
from importlib.metadata import version
from topologicpy.TGraph import TGraph
from topologicpy.Vertex import Vertex
from topologicpy.Edge import Edge
from .building_navigation import build,canonical_model
from .ifc_geometry import shape
from .models import Analysis,Model,Boundary,SYNTAX,ISO
from .scores import scores_for

def native_graph(entry):
    if entry.get('api_graph') is not None:return entry['api_graph']
    graph=TGraph()
    for n in entry['nodes']:
        x,y,z=n['point'];graph.AddVertex(dictionary={'x':x,'y':y,'z':z,'storey':n['storey'],'kind':n['kind']},tolerance=1e-8,silent=True)
    for e in entry['edges']:graph.AddEdge(e['src'],e['dst'],directed=False,dictionary={'Length':e['length'],'length':e['length']},silent=True)
    return graph

def graph_data(entry):
    return {'nodes':[n['point'] for n in entry['nodes']],'edges':[[e['src'],e['dst']] for e in entry['edges']],'node_attributes':entry['nodes'],'edge_attributes':entry['edges']}

def prepare_building(a):
    mode=a.path_graph if a.kind=='path' else a.graph_mode
    opts={k:getattr(a,k) for k in ['min_overlap','compute_overlap','fov','direction','isovist_radius','axial_reduce','axial_sampling_distance','axial_max_candidates','axial_max_samples','axial_tolerance']}
    return build(a.model,a.spacing,mode,a.storey,opts,clearance=a.clearance)

def analyze_isovists(a):
    from .analysis import analyze
    m=canonical_model(a.model);surfaces=m.get('isovist_faces')
    if not surfaces or any(s.get('holes') and len(s.get('hole_types') or [])!=len(s['holes']) for s in surfaces):
        # Rebuild legacy imports lacking roles using the authoritative model,
        # including its retained IFC solids and exact eye-height sections.
        from topologicpy.Navigation import Navigation
        from .building_navigation import navigation_model,face_record
        surfaces=[face_record(f) for f in Navigation.IsovistFaces(navigation_model(m))]
    elements=[];graph={'nodes':[],'edges':[],'node_attributes':[]}
    for s in surfaces:
        if a.storey is not None and s['storey']!=a.storey:continue
        z=s['plane'][2]
        if a.point:
            from shapely.geometry import Point
            if len(a.point)>2 and abs(a.point[2]-z)>.02:continue
            if not shape(s).contains(Point(a.point[:2])):continue
        b=Boundary(id=0,outer=[p[:2] for p in s['outer']],holes=[[p[:2] for p in r] for r in s.get('holes',[])],hole_types=s.get('hole_types') or [])
        request=a.model_copy(update={'model':Model(name=m['name'],faces=[b]),'boundary':0,'point':a.point[:2] if a.point else None})
        r=analyze(request);offset=len(graph['nodes'])
        for e in r['elements']:
            e['id']=len(elements);e['storey']=s['storey'];e['point']=[*e['point'][:2],z]
            for key in ['polygon','line','isovist']:
                if key in e:e[key]=[[*p[:2],z] for p in e[key]]
            for key in ['holes','isovist_holes']:
                if key in e:e[key]=[[[*p[:2],z] for p in ring] for ring in e[key]]
            elements.append(e)
        graph['nodes'].extend([[*p[:2],z] for p in r['graph']['nodes']]);graph['edges'].extend([[i+offset,j+offset] for i,j in r['graph']['edges']]);graph['node_attributes'].extend([{'storey':s['storey'],'kind':'isovist'} for _ in r['graph']['nodes']])
        if a.point:break
    if not elements:raise ValueError('Choose a viewpoint on the selected storey’s eye-level face.')
    return {'elements':elements,'graph':graph,'name':ISO[a.metric],'unit':'m²' if a.metric=='area' else 'unitless'}

def analyze_building(a):
    start=time.perf_counter()
    if a.kind=='isovist':result=analyze_isovists(a)
    else:
        entry,reused=prepare_building(a);graph=native_graph(entry);gj=graph_data(entry)
        if a.kind=='path':
            for p in [a.path_start,a.path_end]:
                if p is None or len(p)!=3 or not all(math.isfinite(v) for v in p):raise ValueError('Select a start and destination on walkable surfaces.')
            # Endpoints originate from renderer hit-testing. Snap only within
            # their selected level so stacked surfaces cannot swap endpoints.
            def snap(p):
                candidates=[i for i,n in enumerate(entry['nodes']) if n['kind'] not in {'lift','lift_door'} and abs(n['point'][2]-p[2])<=.17+1e-5]
                if not candidates:raise ValueError('No navigation point lies on this level.')
                from shapely.geometry import LineString,Point
                from shapely.ops import unary_union
                support=unary_union([shape(s) for s in entry['model']['faces'] if abs(s['plane'][0]*p[0]+s['plane'][1]*p[1]+s['plane'][2]-p[2])<=.17+1e-5])
                for c in entry['model'].get('connectors',[]):
                    for s in c.get('surfaces',[c]):
                        if s.get('outer') and shape(s).buffer(1e-5).covers(Point(p[:2])):
                            support=support.union(shape(s))
                if a.clearance:
                    support=clearance_region(support,a.clearance)
                candidates.sort(key=lambda i:math.dist(entry['nodes'][i]['point'],p))
                for i in candidates:
                    if support.buffer(1e-5).covers(LineString([p[:2],entry['nodes'][i]['point'][:2]])):return i
                raise ValueError('No reachable navigation point lies on this surface. Try a finer grid.')
            source,target=snap(a.path_start),snap(a.path_end)
            route=TGraph.ShortestPath(graph,source,target,edgeKey='Length',useAStar=False,silent=True)
            if not route:raise ValueError('No path connects these locations.')
            points=[entry['nodes'][i]['point'] for i in route]
            length=sum(math.dist(p,q) for p,q in zip(points,points[1:]))
            raw_length=length
            if a.straighten and len(points)>2:
                # Straighten only contiguous coplanar floor runs. Vertical
                # circulation remains on its modelled steps, ramp or lift.
                from shapely.geometry import LineString
                from shapely.ops import unary_union
                from topologicpy.Face import Face
                from topologicpy.Wire import Wire
                from .geometry import make_face
                smoothed=[];i=0
                while i<len(points):
                    j=i
                    while j+1<len(points) and entry['nodes'][route[j]]['kind']=='floor' and entry['nodes'][route[j+1]]['kind']=='floor' and abs(points[j+1][2]-points[i][2])<1e-5:j+=1
                    run=points[i:j+1]
                    if len(run)>2:
                        sid=entry['nodes'][route[i]]['storey'];z=run[0][2]
                        hosts=[s for s in entry['model']['faces'] if s['storey']==sid and abs(s['plane'][0])+abs(s['plane'][1])<1e-5 and abs(s['plane'][2]-z)<1e-5]
                        from .ifc_geometry import polygons,surface
                        for poly in polygons(clearance_region(unary_union([shape(s) for s in hosts]),a.clearance)):
                            if not poly.buffer(1e-6).covers(LineString([p[:2] for p in run])):continue
                            host=make_face(Boundary(id=0,outer=list(poly.exterior.coords)[:-1],holes=[list(r.coords)[:-1] for r in poly.interiors]))
                            wire=Wire.ByVertices([Vertex.ByCoordinates(p[0],p[1],0) for p in run],close=False,silent=True)
                            smooth=Wire.Straighten(wire,host=host,silent=True)
                            if smooth:
                                candidate=[[Vertex.X(v),Vertex.Y(v),z] for v in Wire.Vertices(smooth)]
                                if poly.buffer(1e-6).covers(LineString([p[:2] for p in candidate])):run=candidate
                            break
                    smoothed.extend(run);i=j+1
                points=smoothed;length=sum(math.dist(p,q) for p,q in zip(points,points[1:]))
            result={'elements':[],'graph':gj,'grid':[{'polygon':s['outer'],'holes':s.get('holes',[]),'storey':s['storey']} for s in entry['tiles']],'name':'Shortest path','unit':'m','route':{'points':points,'raw_points':[entry['nodes'][i]['point'] for i in route],'length':length,'original_length':raw_length,'algorithm':'Dijkstra','snapped':True,'requested_start':a.path_start,'requested_end':a.path_end},'graph_reused':reused}
        else:
            angular=a.metric.startswith('Angular') or a.metric.startswith('Tulip') or a.metric in {'NAIN','NACH'}
            if angular:
                geometric=[];edge_order=[]
                for e in entry['edges']:
                    p,q=entry['nodes'][e['src']]['point'],entry['nodes'][e['dst']]['point']
                    line=Edge.ByVertices([Vertex.ByCoordinates(*p),Vertex.ByCoordinates(*q)],silent=True)
                    if line is not None:geometric.append(line);edge_order.append(e)
                sg=TGraph.SegmentGraph(geometric,silent=True)
                if sg is None:raise ValueError('No segments are available for angular analysis.')
                values=scores_for(sg,a);incident=[[] for _ in entry['nodes']]
                # SegmentGraph originators preserve each 3D navigation edge.
                source_by_coords={tuple(sorted((tuple(round(c,6) for c in entry['nodes'][e['src']]['point']),tuple(round(c,6) for c in entry['nodes'][e['dst']]['point'])))):e for e in edge_order}
                for rec,v in zip(TGraph.Vertices(sg),values):
                    origin=TGraph.VertexOriginator(sg,rec)
                    key=tuple(sorted(tuple(round(c,6) for c in Vertex.Coordinates(p)) for p in [Edge.StartVertex(origin),Edge.EndVertex(origin)]))
                    e=source_by_coords.get(key)
                    if e and v is not None and math.isfinite(v):
                        incident[e['src']].append(v);incident[e['dst']].append(v)
                scores=[sum(v)/len(v) if v else None for v in incident]
            else:scores=scores_for(graph,a)
            if isinstance(scores,dict):scores=[scores.get(i) for i in range(len(entry['nodes']))]
            if scores is None or len(scores)!=len(entry['nodes']):raise ValueError('Analysis did not return a value for each navigation point.')
            elements=[]
            for tile in entry['tiles']:
                n=entry['nodes'][tile['node']]
                if n['kind'] in {'lift','lift_door'}:continue
                val=scores[tile['node']];val=float(val) if val is not None and math.isfinite(val) else None
                elements.append({'id':len(elements),'node':tile['node'],'point':n['point'],'polygon':tile['outer'],'holes':tile.get('holes',[]),'line':tile.get('line'),'value':val,'kind':n['kind'],'storey':n['storey']})
            result={'elements':elements,'graph':gj,'name':SYNTAX[a.metric],'unit':'unitless','graph_reused':reused,'angular_mapping':'Mean of incident 3D segment scores' if angular else None}
    result.update(metric=a.metric,source='topologicpy',engine_version=version('topologicpy'),parameters=a.model_dump(exclude={'model'}),warnings=[],elapsed=time.perf_counter()-start)
    return result


def clearance_region(region,distance):
    """Conservative route-click/straightening guard using the same offset API."""
    if not distance:return region
    from topologicpy.Face import Face
    from topologicpy.Topology import Topology
    from shapely.ops import unary_union
    from .ifc_geometry import polygons,surface
    from .building_navigation import api_face,face_record
    parts=[]
    for poly in polygons(region):
        result=Face.ByOffset(api_face(surface(poly,[0,0,0],'0')),offset=distance,silent=True)
        if result is not None:
            parts.extend(shape(face_record(f)) for f in Topology.Faces(result,silent=True))
    return unary_union(parts)
