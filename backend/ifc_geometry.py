"""Browser geometry serialization around TopologicPy IFC/Navigation APIs."""
from collections import defaultdict
from shapely.geometry import Polygon
from shapely.ops import unary_union

EPS=1e-5

def polygons(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g] if g.area>EPS*EPS else []
    return [p for part in getattr(g,'geoms',[]) for p in polygons(part)]

def surface(poly,plane,storey,kind='floor',source=None):
    a,b,c=plane
    xyz=lambda ring:[[float(x),float(y),float(a*x+b*y+c)] for x,y in list(ring.coords)[:-1]]
    return {'outer':xyz(poly.exterior),'holes':[xyz(r) for r in poly.interiors], 'plane':list(plane),'storey':storey,'kind':kind,'source':source}

def shape(s):return Polygon([p[:2] for p in s['outer']],[[p[:2] for p in h] for h in s.get('holes',[])])
def height(s,x,y):
    a,b,c=s.get('plane',[0,0,s.get('elevation',0)])
    return a*x+b*y+c

def import_ifc(path,filename):
    from .ifc_adapter import read_ifc
    from .building_navigation import face_record
    from topologicpy.IFC import IFC
    from topologicpy.Navigation import Navigation
    # The display adapter and navigation API share one parsed IFC model.
    parsed=read_ifc(path)
    nav=IFC.NavigationModel(parsed['model'])
    # Use API-produced floor tiles for obstacle-cut display boundaries as well.
    from topologicpy.TGraph import TGraph
    import json
    display=Navigation.Graph(nav,spacing=1000,graphType='tgraph')
    grouped=defaultdict(list)
    for tile in json.loads(TGraph.Dictionary(display).get('navigationTiles','[]')):
        if tile['kind']=='floor':grouped[(tile['storey'],tuple(tile['plane']))].append(shape(tile))
    faces=[surface(p,list(plane),sid) for (sid,plane),parts in grouped.items() for p in polygons(unary_union(parts))]
    for i,s in enumerate(faces):s.update(id=i,name=f"Surface {i+1}")
    connectors=[];lifts=[]
    for c in nav.connectors:
        if c['type']=='lift':
            lifts.append({**c,'footprint':face_record(c['footprint']) if c.get('footprint') is not None else None})
        elif c['type']=='ramp':
            connectors.append({k:v for k,v in c.items() if k!='faces'}|{'surfaces':[face_record(f) for f in c['faces']]})
        else:
            connectors.extend({**face_record(f),**{k:v for k,v in c.items() if k!='faces'}} for f in c['faces'])
    context=[]
    for ident,mesh in parsed['meshes'].items():
        container=parsed['container'](ident)
        if container is not None and parsed['entities'][container].type!='IFCBUILDINGSTOREY':container=parsed['ancestor'](container,{'IFCBUILDINGSTOREY'})
        sid=str(container) if container is not None else min(nav.storeys,key=lambda st:abs(st['elevation']-mesh['bounds'][0][2]))['id'] if nav.storeys else '0'
        context.append({'storey':sid,'type':parsed['objects'][ident].is_a(),'vertices':mesh['vertices'],'triangles':mesh['triangles'],'simplified':bool(mesh.get('bounding_box')),'source':str(ident)})
    return {'name':filename,'unit':'m','dimension':3,'faces':faces,'storeys':nav.storeys,'connectors':connectors,'lifts':lifts,'doors':[],'obstacles':[face_record(f) for f in nav.obstacles],'isovist_faces':[face_record(f) for f in Navigation.IsovistFaces(nav)],'context':context,'navigation_faces':[face_record(f) for f in nav.faces],'navigation_ifc':{k:v for k,v in nav._ifc.items() if k!='_obstacle_faces'},'segments':[],'warnings':[],'import_info':{'reader':'TopologicPy.IFC.NavigationModel','furniture_openings':'bounding boxes','source_vertices':parsed['original_vertices'],'display_vertices':sum(len(c['vertices']) for c in context),'source_triangles':parsed['original_triangles'],'display_triangles':sum(len(c['triangles']) for c in context)}}
