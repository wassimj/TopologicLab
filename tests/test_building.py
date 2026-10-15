"""Checks for physical reachability, IFC semantics and analysis integration."""
import copy,json,math,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.models import Analysis
from backend.ifc_geometry import import_ifc,shape
from backend.building_navigation import build,ramp_samples
from backend.building_analysis import analyze_building,native_graph
from topologicpy.TGraph import TGraph

@pytest.fixture(scope='module')
def building():return import_ifc(Path(__file__).resolve().parents[1]/'examples/two-storey-demo.ifc','Demo')

def planar(z=0,x=0,width=4,sid='0'):
 return {'id':int(x*10),'outer':[[x,0,z],[x+width,0,z],[x+width,4,z],[x,4,z]],'holes':[],'plane':[0,0,z],'elevation':z,'storey':sid}
def connected(e,a,b):return bool(TGraph.ShortestPath(native_graph(e),a,b,edgeKey='Length',useAStar=False,silent=True))

def test_step_limit_and_horizontal_gaps():
 for rise,gap,expected in [(.17,0,True),(.171,0,False),(0,.01,False)]:
  m={'name':'join','faces':[planar(),planar(rise,4+gap)],'storeys':[{'id':'0','name':'Level','elevation':0}]}
  e,_=build(m,2);assert connected(e,0,len(e['nodes'])-1)==expected

def test_ifc_units_roof_obstacles_and_fallback(building):
 assert len(building['storeys'])==2
 assert max(p[2] for s in building['faces'] for p in s['outer'])<3.2
 assert any(abs(s['plane'][2]-3.15)<1e-4 for s in building['faces'])
 from shapely.geometry import Point
 ground=[shape(s) for s in building['faces'] if s['storey']==building['storeys'][0]['id']]
 assert not any(p.contains(Point(7.2,7.2)) for p in ground)
 assert not any(p.contains(Point(.5,4.1)) for p in ground)
 assert any(p.contains(Point(2,4.1)) for p in ground) # doorway remains open
 assert building['warnings']==[]

def test_stair_ramp_and_lift_independently_connect(building):
 for kind in ['stair','ramp','lift']:
  m=copy.deepcopy(building)
  groups={c['group'] for c in m['connectors'] if c['type']==kind}
  m['connectors']=[c for c in m['connectors'] if c['type']==kind or (c.get('kind')=='landing' and c['group'] in groups)] if kind!='lift' else []
  if kind!='lift':m['lifts']=[]
  e,_=build(m,1.5);r=analyze_building(Analysis(model=m,kind='path',spacing=1.5,path_start=[.5,.5,0],path_end=[11,8,3]))
  assert r['route']['length']>3
  if kind=='stair':assert sum(n['kind']=='tread' for n in e['nodes'])==18;assert sum(q['kind']=='stair' for q in e['edges'])==17
  if kind=='lift':assert sum(q['kind']=='lift' for q in e['edges'])==1

def test_ramp_spacing_and_tiles(building):
 runs=[c for c in building['connectors'] if c['type']=='ramp']
 assert len(runs)==3
 assert len({c['group'] for c in runs})==1
 group=runs[0]['group']
 landings=[c for c in building['connectors'] if c.get('kind')=='landing' and c['group']==group]
 assert len(landings)==2
 assert sorted(round(c['plane'][2],5) for c in landings)==[1.2,1.8]
 assert all(abs(shape(c).area-2.25)<1e-6 for c in landings)
 lengths=[]
 levels=[]
 for ramp in runs:
  samples=ramp_samples(ramp)
  assert len(samples)==8
  distances=[math.dist(a[0],b[0]) for a,b in zip(samples,samples[1:])]
  xyz=[p for face in ramp['surfaces'] for p in face['outer']]
  length=max(max(p[k] for p in xyz)-min(p[k] for p in xyz) for k in [0,1])
  lengths.append(round(length,5))
  assert all(abs(d-.15*math.hypot(length,length/20))<.002 for d in distances[:-1])
  assert all(tiles for _,tiles in samples)
  levels.append((round(samples[0][0][2],5),round(samples[-1][0][2],5)))
  assert all(abs(math.hypot(*face['plane'][:2])-.05)<1e-6 for face in ramp['surfaces'])
 assert sorted(lengths)==[12,24,24]
 assert sorted((min(a,b),max(a,b)) for a,b in levels)==[(0,1.2),(1.2,1.8),(1.8,3)]
 # With the other vertical connectors removed, routing must use all three runs
 # and the actual flat landing instead of inventing an inter-run shortcut.
 model=copy.deepcopy(building);model['lifts']=[]
 model['connectors']=[c for c in model['connectors'] if c['group']==group]
 entry,_=build(model,1.5)
 graph=native_graph(entry)
 lower=min((i for i,n in enumerate(entry['nodes']) if n['kind']=='floor'),key=lambda i:math.dist(entry['nodes'][i]['point'],[.75,.75,0]))
 upper=min((i for i,n in enumerate(entry['nodes']) if n['kind']=='floor' and n['point'][2]>2.9),key=lambda i:math.dist(entry['nodes'][i]['point'],[14.25,.75,3]))
 route=TGraph.ShortestPath(graph,lower,upper,edgeKey='Length',useAStar=False,silent=True)
 assert route
 assert sum(entry['nodes'][i]['kind']=='landing' for i in route)==2
 assert sum(math.dist(entry['nodes'][a]['point'],entry['nodes'][b]['point']) for a,b in zip(route,route[1:]))>60

def test_missing_geometry_does_not_invent_connectors(building):
 m=copy.deepcopy(building);m['connectors']=[];m['lifts']=[]
 with pytest.raises(ValueError,match='No path'):analyze_building(Analysis(model=m,kind='path',spacing=2,path_start=[.5,.5,0],path_end=[11,8,3]))

def test_storey_subgraph_excludes_other_levels(building):
 sid=building['storeys'][1]['id'];e,_=build(building,2,storey=sid)
 assert all(n['storey']==sid for n in e['nodes'])
 assert not any(q['kind']=='lift' for q in e['edges'])

def test_isovists_have_separate_eye_levels(building):
 levels={round(s['plane'][2],3) for s in building['isovist_faces']}
 assert levels=={1.6,2.8,3.4,4.6,4.75}
 a=Analysis(model=building,kind='isovist',metric='area',spacing=4,storey=building['storeys'][0]['id'])
 r=analyze_building(a);assert r['elements'];assert all(round(e['point'][2],3) in {1.6,2.8,3.4} for e in r['elements'])
 assert all(abs(p[2]-e['point'][2])<1e-6 for e in r['elements'] for p in e['polygon'])

@pytest.mark.parametrize('metric',['Integration','Choice','Connectivity','AngularIntegration','AngularChoice','AngularConnectivity','DepthMap','MeanDepth','AccessibilityCentrality','DegreeCentrality','EigenVectorCentrality','TulipChoice','TulipIntegration','NAIN','NACH','TulipNodeCount','TulipTotalDepth','TulipTotalWeight'])
def test_all_existing_measures(building,metric):
 r=analyze_building(Analysis(model=building,spacing=3,metric=metric,graph_mode='grid_shell'))
 assert r['elements'];assert len(r['graph']['nodes'])>len(r['elements']) # uncoloured lift stops
 assert all(e['kind'] not in {'lift','lift_door'} for e in r['elements'])

@pytest.mark.parametrize('mode',['grid_shell','visibility','segments','axial','axial_generated','isovist_intersection'])
def test_existing_2d_graph_modes(mode):
 floor=planar(width=6);floor['id']=0
 m={'name':'2D case','faces':[floor],'segments':[[[1,1,0],[5,1,0]],[[5,1,0],[5,3,0]],[[5,3,0],[1,3,0]],[[1,3,0],[1,1,0]] ]}
 r=analyze_building(Analysis(model=m,spacing=2,metric='Connectivity',graph_mode=mode,axial_max_candidates=200,axial_max_samples=40))
 assert r['elements'];assert all(abs(p[2])<1e-7 for p in r['graph']['nodes'])

def test_geometric_route_and_straightening():
 m={'name':'2D','faces':[planar(width=8)]}
 a=Analysis(model=m,kind='path',spacing=2,path_start=[1,1,0],path_end=[7,3,0]);raw=analyze_building(a)
 a.straighten=True;smooth=analyze_building(a)
 assert smooth['route']['length']<=raw['route']['length']
 assert smooth['route']['algorithm']=='Dijkstra'


def test_ramp_retains_turning_landing():
 from backend.ifc_geometry import surface
 from shapely.geometry import box
 parts=[surface(box(0,0,5,2),[.3,0,0],'0','ramp'),surface(box(5,0,7,2),[0,0,1.5],'0','ramp'),surface(box(5,2,7,7),[0,.3,.9],'0','ramp')]
 result=ramp_samples({'surfaces':parts})
 assert any(math.dist(p,[6,1,1.5])<1e-6 for p,_ in result)
 assert all(tiles for p,tiles in result)
 from shapely.ops import unary_union
 from shapely.geometry import LineString
 support=unary_union([shape(p) for p in parts])
 assert all(support.buffer(1e-4).covers(LineString([a[0][:2],b[0][:2]])) for a,b in zip(result,result[1:]))


@pytest.fixture(scope='module')
def duplex():
 import os
 path=Path(os.environ.get('TOPOLOGICLAB_DUPLEX_IFC',os.environ.get('SPATIAL_DUPLEX_IFC','')))
 if not path.is_file():pytest.skip('Set TOPOLOGICLAB_DUPLEX_IFC to the IFC2x3 Duplex Architecture fixture')
 return import_ifc(path,path.name)

@pytest.mark.parametrize('spacing',[1,1.5,2,4])
def test_ifc2x3_duplex_body_representations_connect_both_stairs(duplex,spacing):
 # This real IFC puts WalkingLine/Boundary representations before Body.
 # Default shape selection previously skipped both flights and many walls.
 assert any(c['type'].startswith('IfcWall') for c in duplex['context'])
 entry,_=build(duplex,spacing,'navigation')
 sources={c['source'] for c in duplex['connectors'] if c.get('kind')=='tread'}
 assert len(sources)==2
 for source in sources:
  endpoints=[]
  for edge in entry['edges']:
   if edge['kind']!='attachment':continue
   a,b=edge['src'],edge['dst']
   if entry['nodes'][a]['source']==source:endpoints.append(b)
   elif entry['nodes'][b]['source']==source:endpoints.append(a)
  endpoints.sort(key=lambda i:entry['nodes'][i]['point'][2])
  assert len(endpoints)>=2
  start,end=[entry['nodes'][i]['point'] for i in [endpoints[0],endpoints[-1]]]
  assert end[2]-start[2]>3
  result=analyze_building(Analysis(model=duplex,kind='path',spacing=spacing,path_start=start,path_end=end))
  assert result['route']['length']>3
  assert max(p[2] for p in result['route']['points'])>3


def test_topologic_ifc_reader_sends_only_furniture_and_opening_boxes(duplex):
 assert duplex['import_info']['reader']=='TopologicPy.IFC.NavigationModel'
 boxes=[c for c in duplex['context'] if c['type'] in {'IfcFurnishingElement','IfcFurniture','IfcSystemfurnitureelement','IfcOpeningElement'}]
 assert any(c['type']=='IfcOpeningElement' for c in boxes)
 assert any(c['type']=='IfcFurnishingElement' for c in boxes)
 assert all(c['simplified'] and len(c['vertices'])==8 and len(c['triangles'])==12 for c in boxes)
 assert duplex['import_info']['display_triangles']<duplex['import_info']['source_triangles']


@pytest.mark.parametrize('distance',[0,.2])
def test_clearance_building_transport_and_independent_connectors(building,distance):
 # Exercise the actual browser JSON/Pydantic round trip, including solid obstacle data.
 from backend.models import Model
 m=Model.model_validate(json.loads(json.dumps(building))).model_dump()
 for kind in ('stair','ramp','lift'):
  chosen=copy.deepcopy(m)
  groups={c['group'] for c in chosen['connectors'] if c['type']==kind}
  chosen['connectors']=[c for c in chosen['connectors'] if c['type']==kind or c.get('group') in groups]
  if kind!='lift':chosen['lifts']=[]
  a=Analysis(model=chosen,kind='path',spacing=1.5,clearance=distance,path_start=[3,1,0],path_end=[10,8,3],straighten=True)
  r=analyze_building(a)
  assert r['route']['length']>3
  assert r['parameters']['clearance']==distance


def test_clearance_cache_route_and_consumed_regions():
 from shapely.geometry import LineString,Point
 m={'name':'Room','faces':[planar(width=4)]}
 a=Analysis(model=m,kind='path',spacing=1,clearance=.4,path_start=[.6,.6,0],path_end=[3.4,3.4,0],straighten=True)
 e,reused=build(a.model,1,clearance=.4)
 assert TGraph.Dictionary(native_graph(e))['clearance']==.4
 safe=shape(planar(width=4)).buffer(-.4)
 assert all(safe.buffer(1e-5).covers(Point(n['point'][:2])) for n in e['nodes'])
 r=analyze_building(a)
 assert safe.buffer(1e-5).covers(LineString([p[:2] for p in r['route']['points']]))
 assert build(a.model,1,clearance=.4)[1]
 assert build(a.model,1,clearance=.5)[0] is not e
 with pytest.raises(ValueError,match='No walkable'):build(a.model,1,clearance=3)
 with pytest.raises(ValueError,match='reachable'):analyze_building(a.model_copy(update={'path_start':[.1,.1,0]}))


def test_clearance_isovists_keep_original_visibility_host():
 m={'name':'Room','faces':[planar(width=4)]}
 a=Analysis(model=m,kind='isovist',metric='area',spacing=1,clearance=.4)
 r=analyze_building(a)
 assert r['elements']
 assert all(e['value']==pytest.approx(16,abs=.01) for e in r['elements'])
 assert all(.4-1e-5<=p[0]<=3.6+1e-5 and .4-1e-5<=p[1]<=3.6+1e-5 for p in r['graph']['nodes'])


@pytest.mark.parametrize('distance',[-1,float('inf'),float('nan')])
def test_invalid_clearance_request(distance):
 from pydantic import ValidationError
 with pytest.raises(ValidationError):Analysis(model={'name':'Room','faces':[planar()]},clearance=distance)


def test_duplex_positive_clearance_preserves_both_stair_attachments(duplex):
 entry,_=build(duplex,1.5,clearance=.2)
 for source in {c['source'] for c in duplex['connectors'] if c.get('kind')=='tread'}:
  stairs={i for i,n in enumerate(entry['nodes']) if n.get('source')==source and n['kind']=='tread'}
  attached=[]
  for edge in entry['edges']:
   a,b=edge['src'],edge['dst']
   if a in stairs and entry['nodes'][b]['kind']=='floor':attached.append(b)
   if b in stairs and entry['nodes'][a]['kind']=='floor':attached.append(a)
  assert len({entry['nodes'][i]['storey'] for i in attached})==2
  assert connected(entry,min(attached,key=lambda i:entry['nodes'][i]['point'][2]),max(attached,key=lambda i:entry['nodes'][i]['point'][2]))



def test_imported_ifc_eye_faces_preserve_boundary_roles(building):
 from backend.models import Model
 roundtrip=Model.model_validate(json.loads(json.dumps(building))).model_dump()
 assert roundtrip['isovist_faces']
 assert all(len(s['holes'])==len(s['hole_types']) for s in roundtrip['isovist_faces'])
 labels=[role for s in roundtrip['isovist_faces'] for role in s['hole_types']]
 assert 'obstacle' in labels
 assert set(labels).issubset({'hole','obstacle'})
