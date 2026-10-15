"""TopologicPy geometry orchestration and JSON display adapters.

This module does not implement polygon booleans, tessellation, ray casting,
grid clipping, or graph construction algorithms.
"""
import math
import hashlib
import json
from collections import OrderedDict
from threading import RLock
from pathlib import Path
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Edge import Edge
from topologicpy.Wire import Wire
from topologicpy.Face import Face
from topologicpy.Cluster import Cluster
from topologicpy.Dictionary import Dictionary
from topologicpy.Grid import Grid

TOLERANCE = .0001
_floor_cache=OrderedDict()
_floor_lock=RLock()

def prepared_floor(boundary,spacing=None,clearance=0):
    """Reuse API-produced geometry without duplicating geometry algorithms."""
    key=hashlib.sha256(json.dumps({'boundary':boundary.model_dump(),'spacing':spacing,'clearance':clearance},sort_keys=True).encode()).hexdigest()
    with _floor_lock:
        if key in _floor_cache:
            result=_floor_cache.pop(key);_floor_cache[key]=result
            return result
        host=make_face(boundary)
        shell,samples=slice_grid(host,spacing,clearance) if spacing is not None else (None,[])
        result=(host,shell,samples)
        _floor_cache[key]=result
        while len(_floor_cache)>3:_floor_cache.popitem(last=False)
        return result

def coordinates(vertex):
    return [Vertex.X(vertex),Vertex.Y(vertex)]

def ring(wire):
    return [coordinates(v) for v in Wire.Vertices(wire)]

def face_data(face):
    return {'outer':ring(Face.ExternalBoundary(face)),
            'holes':[ring(w) for w in Face.InternalBoundaries(face)]}

def make_face(boundary,visibility=False):
    def make_wire(points,role=None):
        wire=Wire.ByVertices([Vertex.ByCoordinates(*p[:2],0) for p in points],close=True,silent=True)
        if wire is not None and role is not None:
            wire=Topology.SetDictionary(wire,Dictionary.ByPythonDictionary({'isovistType':role}))
        return wire
    roles=getattr(boundary,'hole_types',[]) or []
    inners=[]
    for i,ring in enumerate(boundary.holes):
        role=roles[i] if i<len(roles) else 'obstacle'
        if not visibility or role=='obstacle':inners.append(make_wire(ring,role))
    face=Face.ByWires(make_wire(boundary.outer),inners,silent=True)
    if face is None or Face.Area(face)<=1e-8:raise ValueError('TopologicPy could not construct the selected floor boundary.')
    return face


def contains_point(face,point,include_boundary=False):
    vertex=Vertex.ByCoordinates(*point[:2],0)
    return bool(Vertex.IsInternal2D([vertex],face,includeBoundary=include_boundary,silent=True)[0])

def slice_grid(host,spacing,clearance=0):
    vertices=Topology.Vertices(host)
    xs=[Vertex.X(v) for v in vertices];ys=[Vertex.Y(v) for v in vertices]
    estimate=math.ceil((max(xs)-min(xs))/spacing)*math.ceil((max(ys)-min(ys))/spacing)
    if estimate>200000:raise ValueError('Grid is too dense. Increase spacing.')
    grid=Grid.OnFace(host,spacing=spacing,mode='planar',uAlignment='start',vAlignment='start',silent=True,clearance=clearance)
    if clearance:
        inset=Face.ByOffset(host,offset=clearance,silent=True)
        if inset is None:raise ValueError('No walkable grid remains. Reduce clearance or grid spacing.')
        parts=[Topology.Slice(region,grid,silent=True) if grid is not None else region for region in Topology.Faces(inset,silent=True)]
        if not parts or any(part is None for part in parts):raise ValueError('Could not construct the clearance grid.')
        shell=Cluster.ByTopologies(parts,silent=True)
    else:
        shell=Topology.Slice(host,grid,silent=True) if grid is not None else host
    if shell is None:raise ValueError('Topology.Slice could not slice the floor plan by the grid.')
    faces=Topology.Faces(shell) or []
    if not faces:raise ValueError('No floor grid faces were produced.')
    if len(faces)>10000:raise ValueError('More than 10000 grid faces. Increase spacing.')
    samples=[]
    for i,face in enumerate(faces):
        face=Topology.SetDictionary(face,Dictionary.ByKeyValue('face_id',f'face_{i+1}'))
        vertex=Topology.InternalVertex(face,silent=True)
        if vertex is None:raise ValueError('TopologicPy could not find an internal grid viewpoint.')
        samples.append((coordinates(vertex),face))
    return shell,samples

def import_geometry(path,filename):
    suffix=Path(path).suffix.lower();warnings=[];scale=1.
    if suffix=='.obj':
        imported=Topology.ByOBJPath(str(path),transposeAxes=False,removeCoplanarFaces=True,selfMerge=True,silent=True)
        warnings.append('OBJ coordinates are interpreted as meters.')
    elif suffix in {'.brep','.brp'}:
        imported=Topology.ByBREPPath(str(path),silent=True)
    elif suffix=='.dxf':
        import ezdxf
        from ezdxf.units import conversion_factor
        doc=ezdxf.readfile(path)
        scale=conversion_factor(doc.units,6) if doc.units else 1.
        if not doc.units:warnings.append('DXF units are unspecified; interpreted as meters.')
        imported=Topology.ByDXFPath(str(path),silent=True)
    elif suffix=='.3dm':
        import rhino3dm
        doc=rhino3dm.File3dm.Read(str(path))
        if doc is None:raise ValueError('Rhino file could not be read.')
        scale=rhino3dm.UnitSystem.UnitScale(doc.Settings.ModelUnitSystem,rhino3dm.UnitSystem.Meters)
        if not math.isfinite(scale) or scale<=0:raise ValueError('Rhino units could not be converted to meters.')
        imported=Topology.By3DMPath(str(path),silent=True)
    else:raise ValueError('Use DXF, OBJ, Rhino .3dm or BREP.')
    if imported is None:raise ValueError(f'TopologicPy could not import {suffix} geometry.')
    items=imported if isinstance(imported,list) else [imported]
    items=[item for item in items if Topology.IsInstance(item,'Topology')]
    if not items:raise ValueError('TopologicPy returned no supported geometry.')
    if scale!=1:
        origin=Vertex.ByCoordinates(0,0,0)
        items=[Topology.Scale(item,origin=origin,x=scale,y=scale,z=scale) for item in items]
    topology=Topology.SelfMerge(Cluster.ByTopologies(items),silent=True)
    faces=Topology.Faces(topology) or []
    if len(faces)>1:
        topology=Topology.RemoveCoplanarFaces(topology,silent=True)
        if topology is None:raise ValueError('Topology.RemoveCoplanarFaces could not assemble the imported floor geometry.')
        faces=Topology.Faces(topology) or []
    if not faces:
        # Delegate closed linework assembly and bounded-face construction to the API.
        bounded=Face.ByEdges(Topology.Edges(topology) or [],silent=True)
        faces=Topology.Faces(bounded) or [] if bounded is not None else []
    horizontal=[]
    for face in faces:
        zs=[Vertex.Z(v) for v in Topology.Vertices(face)]
        if zs and max(zs)-min(zs)<=TOLERANCE:horizontal.append((face,zs[0]))
        else:warnings.append('Skipped non-horizontal geometry.')
    if not horizontal:raise ValueError('No horizontal floor face was returned by TopologicPy. Supply closed floor boundaries.')
    if len(horizontal)>250:raise ValueError('More than 250 boundaries. Export only the intended floor.')
    records=[]
    for i,(face,z) in enumerate(horizontal):
        records.append({'id':i,'name':f'Boundary {i+1} · z {z:g} m','elevation':z,**face_data(face)})
    segments=[[Vertex.Coordinates(Edge.StartVertex(e)),Vertex.Coordinates(Edge.EndVertex(e))] for e in Topology.Edges(topology) or []]
    return {'name':filename,'unit':'m','faces':records,'segments':segments,'warnings':list(dict.fromkeys(warnings))}
