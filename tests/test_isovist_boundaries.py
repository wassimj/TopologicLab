"""Boundary roles survive TopologicLab transport, sampling and visibility analysis."""
import json,sys,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topologicpy.Face import Face
from topologicpy.Vertex import Vertex
from topologicpy.Navigation import Navigation
from topologicpy.Topology import Topology
from topologicpy.Dictionary import Dictionary
from backend.building_navigation import api_face,face_record,build
from backend.building_analysis import analyze_building
from backend.models import Analysis,Model


def rect(x=0,y=0,w=10,h=10,z=0):
    return Face.ByVertices([Vertex.ByCoordinates(a,b,z) for a,b in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]])


def project(obstacle=True):
    floor=Face.ByWires(Face.ExternalBoundary(rect()),[Face.ExternalBoundary(rect(x=2,y=4,w=2,h=2))])
    nav=Navigation.ByFaces([floor],obstacles=[rect(x=7,y=1,w=1,h=1)] if obstacle else [])
    floors=[{**face_record(f),'id':i,'name':'Floor'} for i,f in enumerate(nav.faces)]
    return {'name':'Voids and columns','dimension':3,'faces':floors,'navigation_faces':[face_record(f) for f in nav.faces],'obstacles':[face_record(f) for f in nav.obstacles],'storeys':nav.storeys,'isovist_faces':[face_record(f) for f in Navigation.IsovistFaces(nav)]}


def roundtrip(model):
    return Model.model_validate(json.loads(json.dumps(model))).model_dump()


def test_role_transport_restores_native_geometry_and_ignores_ring_enumeration():
    m=roundtrip(project());record=m['isovist_faces'][0]
    assert sorted(record['hole_types'])==['hole','obstacle']
    record['holes'].reverse();record['hole_types'].reverse()
    restored=face_record(api_face(record))
    assert sorted(restored['hole_types'])==['hole','obstacle']
    iso=Face.Isovist(api_face(record),Vertex.ByCoordinates(1,5,1.6),silent=True)
    assert iso is not None
    assert Vertex.IsInternal(Vertex.ByCoordinates(5,5,1.6),iso,silent=True)


@pytest.mark.parametrize('legacy',[False,True])
def test_point_isovist_sees_across_void_and_still_blocks_column(legacy):
    m=roundtrip(project())
    if legacy:
        for eye in m['isovist_faces']:eye.pop('hole_types')
    a=Analysis(model=m,kind='isovist',metric='area',point=[1,5,1.6])
    result=analyze_building(a)
    assert len(result['elements'])==1
    eye=api_face(roundtrip(project())['isovist_faces'][0])
    control=Face.Isovist(eye,Vertex.ByCoordinates(1,5,1.6),metrics=True,silent=True)
    assert result['elements'][0]['value']==pytest.approx(Face.Area(control),abs=.001)
    assert result['elements'][0]['value']<100
    from shapely.geometry import Polygon,Point
    visible=Polygon([p[:2] for p in result['elements'][0]['isovist']],[[p[:2] for p in ring] for ring in result['elements'][0].get('isovist_holes',[])])
    assert visible.contains(Point(3,5)) and visible.contains(Point(5,5))
    assert not visible.contains(Point(7.5,1.5))


@pytest.mark.parametrize('point',[[3,5,1.6],[7.5,1.5,1.6]])
def test_point_picking_exclusions_remain_invalid(point):
    with pytest.raises(ValueError,match='viewpoint'):
        analyze_building(Analysis(model=roundtrip(project()),kind='isovist',metric='area',point=point))


@pytest.mark.parametrize('clearance',[0,.2])
def test_field_sample_locations_exclude_void_but_visibility_edges_cross_it(clearance):
    m=roundtrip(project(obstacle=False))
    r=analyze_building(Analysis(model=m,kind='isovist',metric='area',spacing=1,clearance=clearance))
    assert r['elements']
    assert all(e['value']==pytest.approx(100,abs=.001) for e in r['elements'])
    from shapely.geometry import Polygon,Point,LineString
    void=Polygon([[2,4],[4,4],[4,6],[2,6]])
    assert all(not void.contains(Point(p[:2])) for p in r['graph']['nodes'])
    assert any(LineString([r['graph']['nodes'][a][:2],r['graph']['nodes'][b][:2]]).intersection(void).length>.1 for a,b in r['graph']['edges'])
    entry,_=build(Model.model_validate(m),spacing=1,clearance=clearance)
    assert all(not void.contains(Point(n['point'][:2])) for n in entry['nodes'])
    assert all(LineString([entry['nodes'][e['src']]['point'][:2],entry['nodes'][e['dst']]['point'][:2]]).intersection(void).length<1e-5 for e in entry['edges'])


def test_2d_fallback_uses_library_boundary_classification():
    m=project(obstacle=False);m.pop('isovist_faces');m.pop('navigation_faces');m['dimension']=2
    result=analyze_building(Analysis(model=roundtrip(m),kind='isovist',metric='area',point=[1,5,1.6]))
    assert result['elements'][0]['value']==pytest.approx(100,abs=.001)


def test_role_changes_invalidate_cached_hosts():
    m=roundtrip(project(obstacle=False))
    a=Analysis(model=m,kind='isovist',metric='area',point=[1,5,1.6])
    clear=analyze_building(a)['elements'][0]['value']
    m['isovist_faces'][0]['hole_types']=['obstacle']
    blocked=analyze_building(Analysis(model=m,kind='isovist',metric='area',point=[1,5,1.6]))['elements'][0]['value']
    assert clear==pytest.approx(100,abs=.001) and blocked<clear
