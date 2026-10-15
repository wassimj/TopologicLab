"""Run with the existing server environment before installing this revision."""
import inspect
import os
import sys
from importlib.metadata import version
os.environ.setdefault('TOPOLOGICPY_CORE_BACKEND','pythonocc')
from topologicpy.Core import Core
from topologicpy.Topology import Topology
from topologicpy.Grid import Grid
from topologicpy.TGraph import TGraph
from topologicpy.Face import Face
from topologicpy.IFC import IFC
from topologicpy.Navigation import Navigation
from topologicpy.Vertex import Vertex
from topologicpy.Wire import Wire
try:
    from topologicpy.Rhino import Rhino
except ImportError:
    Rhino=None

def main():
    baseline='--baseline' in sys.argv
    print('Check mode:', 'existing API baseline' if baseline else 'complete refactor')
    print('TopologicPy:',version('topologicpy'))
    print('Backend:',type(Core.Backend()).__name__)
    required={
        'Navigation.Graph':Navigation.Graph,
        'Navigation.ByFaces':Navigation.ByFaces,
        'Navigation.IsovistFaces':Navigation.IsovistFaces,
        'IFC.NavigationModel':IFC.NavigationModel,
        'IFC.ModelByPath':getattr(IFC,'ModelByPath',None),
        'IFC.MeshData':getattr(IFC,'MeshData',None),
        'IFC.Entities':getattr(IFC,'Entities',None),
        'Grid.OnFace':getattr(Grid,'OnFace',None),
        'Topology.Slice':getattr(Topology,'Slice',None),
        'Topology.ByOBJPath':getattr(Topology,'ByOBJPath',None),
        'Topology.ByDXFPath':getattr(Topology,'ByDXFPath',None),
        'Topology.By3DMPath':getattr(Topology,'By3DMPath',None),
        'TGraph.ByTopology':getattr(TGraph,'ByTopology',None),
        'TGraph.ShortestPath':getattr(TGraph,'ShortestPath',None),
        'TGraph.MeanDepth':getattr(TGraph,'MeanDepth',None),
        'TGraph.VertexOriginator':getattr(TGraph,'VertexOriginator',None),
        'TGraph.ByJSONData':getattr(TGraph,'ByJSONData',None),
        'TGraph.JSONData':getattr(TGraph,'JSONData',None),
        'TGraph.VisibilityGraph':getattr(TGraph,'VisibilityGraph',None),
        'TGraph.IsovistIntersectionGraph':getattr(TGraph,'IsovistIntersectionGraph',None),
        'Face.AxialEdges':getattr(Face,'AxialEdges',None),
        'Vertex.IsInternal2D':getattr(Vertex,'IsInternal2D',None),
        'Wire.Straighten':getattr(Wire,'Straighten',None),
        'Rhino.ByMesh':getattr(Rhino,'ByMesh',None),
    }
    missing=[]
    for name,method in required.items():
        present=callable(method);print(name+':',present)
        if not present and not (baseline and name=='Rhino.ByMesh'):missing.append(name)
    if 'clearance' not in inspect.signature(Navigation.Graph).parameters:missing.append('Navigation.Graph clearance')
    if 'holes' not in inspect.signature(Face.Isovist).parameters:missing.append('Face.Isovist holes')
    if 'boundaryTypeKey' not in inspect.signature(Navigation.IsovistFaces).parameters:missing.append('Navigation.IsovistFaces boundary roles')
    shortest=required['TGraph.ShortestPath']
    topology=required['TGraph.ByTopology']
    if callable(topology):
        has_host='host' in inspect.signature(topology).parameters
        print('TGraph.ByTopology host:',has_host)
        if not has_host and not baseline:missing.append('TGraph.ByTopology host')
    if callable(shortest):
        for name in ['useAStar','snapEndpoints']:
            present=name in inspect.signature(shortest).parameters
            print('ShortestPath '+name+':',present)
            if not present:missing.append('ShortestPath '+name)
    if missing:
        print('Missing API capabilities:',', '.join(missing))
        print('Keep the running app unchanged until these API capabilities are resolved.')
        return 1
    print('API capability check passed.')
    return 0

if __name__=='__main__':sys.exit(main())
