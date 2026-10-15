"""Analysis orchestration. All analytical operations delegate to TopologicPy."""
import inspect
import math
import time
from importlib.metadata import version
from fastapi import HTTPException
from topologicpy.Topology import Topology
from topologicpy.Vertex import Vertex
from topologicpy.Edge import Edge
from topologicpy.Face import Face
from topologicpy.Wire import Wire
from topologicpy.Graph import Graph
from topologicpy.TGraph import TGraph
from topologicpy.Dictionary import Dictionary
from .models import Analysis,SYNTAX,ISO,finite_coords
from .geometry import make_face,face_data,contains_point,slice_grid,prepared_floor
from .routing import shortest_route,visibility_graph,graph_data
from .serialization import clean

def graph_json(graph):
    return graph_data(graph),TGraph.Vertices(graph,asTopologic=True),TGraph.Edges(graph)

def isovist_intersection_graph(f,points,a):
    method=getattr(TGraph,'IsovistIntersectionGraph',None)
    if method is None:raise ValueError("This TopologicPy installation does not provide TGraph.IsovistIntersectionGraph. Use a version containing that method in your existing topologicpy-occ8 environment.")
    origin=Topology.Centroid(f)
    normal=Face.Normal(f)
    direction=[math.sin(math.radians(a.direction)),math.cos(math.radians(a.direction)),0]
    isovists=[]
    origins=[]
    for p in points:
        viewpoint=Vertex.ByCoordinates(*p,0)
        tip=Vertex.ByCoordinates(p[0]+direction[0],p[1]+direction[1],0)
        v=Topology.Flatten(viewpoint,origin=origin,direction=normal)
        t=Topology.Flatten(tip,origin=origin,direction=normal)
        local=[Vertex.X(t)-Vertex.X(v),Vertex.Y(t)-Vertex.Y(v),0]
        iso=Face.Isovist(f,viewpoint,direction=local,fov=a.fov,metrics=False,silent=True)
        if not iso:raise ValueError("Could not compute an isovist for intersection graph construction.")
        isovists.append(iso);origins.append(viewpoint)
    graph=method(isovists=isovists,origins=origins,minOverlap=a.min_overlap,computeOverlap=a.compute_overlap,radius=a.isovist_radius,silent=True)
    if graph is None:raise ValueError("TGraph.IsovistIntersectionGraph could not construct a graph from this floor plan.")
    return graph

def analyze(a:Analysis):
    start=time.perf_counter()
    try:
        b=next((f for f in a.model.faces if f.id==a.boundary),None)
        if not b:raise ValueError("Select a valid boundary.")
        if not finite_coords(b.outer) or any(not finite_coords(h) for h in b.holes):raise ValueError("Invalid boundary coordinates.")
        if a.kind=='path':return shortest_route(a,b,start)
        needs_grid=not (a.point or (a.kind=='syntax' and a.graph_mode in {'segments','axial','axial_generated'}))
        f,shell,samples=prepared_floor(b,a.spacing if needs_grid else None,clearance=a.clearance)
        points=[a.point[:2]] if a.point else [point for point,_ in samples]
        cell_by_point={tuple(round(c,6) for c in point):cell for point,cell in samples}
        if any(not contains_point(f,p) for p in points):raise ValueError("Viewpoint must be inside the navigable area.")
        elements=[]
        axial_report=None
        warnings=[]
        if a.kind=="isovist":
            if a.metric not in ISO:raise ValueError("Unknown isovist metric.")
            direction=[math.sin(math.radians(a.direction)),math.cos(math.radians(a.direction)),0]
            # Face.Isovist flattens the geometry but interprets its direction in
            # that flattened frame. Transform the arrow by the same operation,
            # so clockwise imported boundaries cannot mirror the viewing cone.
            origin=Topology.Centroid(f)
            normal=Face.Normal(f)
            for i,p in enumerate(points):
                viewpoint=Vertex.ByCoordinates(*p,0)
                tip=Vertex.ByCoordinates(p[0]+direction[0],p[1]+direction[1],0)
                flat_view=Topology.Flatten(viewpoint,origin=origin,direction=normal)
                flat_tip=Topology.Flatten(tip,origin=origin,direction=normal)
                local_direction=[Vertex.X(flat_tip)-Vertex.X(flat_view),Vertex.Y(flat_tip)-Vertex.Y(flat_view),0]
                iso=Face.Isovist(f,viewpoint,direction=local_direction,fov=a.fov,metrics=True,triangles=False)
                if not iso:
                    if a.point:raise ValueError("TopologicPy could not compute the isovist at this viewpoint.")
                    part=face_data(samples[i][1])
                    elements.append({"id":len(elements),"point":p,"polygon":part["outer"],"holes":part["holes"],"value":None,"metrics":{},"status":"isovist unavailable"})
                    continue
                metrics=dict(zip(Dictionary.Keys(Topology.Dictionary(iso)),Dictionary.Values(Topology.Dictionary(iso))))
                metrics['direction']=direction
                metrics['viewpoint']=[*p,0]
                centroid=Topology.Centroid(iso)
                metrics['centroid']=[Vertex.X(centroid),Vertex.Y(centroid),Vertex.Z(centroid)]
                visible=face_data(iso)
                cell=visible if a.point else face_data(samples[i][1])
                elements.append({"id":len(elements),"point":p,"polygon":cell['outer'],"holes":cell['holes'],"value":clean(metrics.get(a.metric)),"metrics":{k:clean(v) for k,v in metrics.items()},"isovist":visible['outer'],"isovist_holes":visible['holes']})
            # Overlay corresponds to actual visibility relations at sampled viewpoints.
            graph=visibility_graph(make_face(b,visibility=True),points) if len(points)>1 else TGraph.ByVerticesEdges([Vertex.ByCoordinates(*points[0],0)],[],ontology=False)
            gj,_,_=graph_json(graph)
            name=ISO[a.metric]
        else:
            if a.metric not in SYNTAX:raise ValueError("Unknown space syntax measure.")
            tulip_key={"TulipChoice":"choice","TulipIntegration":"integration","NAIN":"nain","NACH":"nach","TulipNodeCount":"nodeCount","TulipTotalDepth":"totalDepth","TulipTotalWeight":"totalWeight"}.get(a.metric)
            angular=a.metric.startswith("Angular") or tulip_key is not None
            if angular and a.graph_mode!="segments":raise ValueError("Angular measures require the imported segment network.")
            if a.graph_mode=='axial_generated':
                generate=getattr(Face,'AxialEdges',None)
                if not callable(generate):
                    raise ValueError("This TopologicPy installation does not provide Face.AxialEdges. Update the server's TopologicPy source to a version with axial-line generation; keep the existing PythonOCC environment.")
                report=generate(f,reduce=a.axial_reduce,samplingDistance=a.axial_sampling_distance,
                    maxCandidates=a.axial_max_candidates,maxSamples=a.axial_max_samples,
                    tolerance=a.axial_tolerance,returnReport=True,silent=True)
                if not isinstance(report,dict) or not report.get('edges'):
                    raise ValueError("TopologicPy could not generate axial lines for this floor boundary.")
                graph=TGraph.AxialGraph(report['edges'],tolerance=a.axial_tolerance,silent=True)
                axial_report={k:v for k,v in report.items() if k not in {'edges','samples'}}
                if report.get('truncated'):warnings.append('Axial generation reached a sampling or candidate limit; inspect the coverage report.')
                if report.get('coverageComplete') is False:warnings.append('Some sampled locations are not covered by the generated axial map.')
                if report.get('connected') is False:warnings.append('The generated axial map contains disconnected components.')
            elif a.graph_mode in {"segments","axial"}:
                edges=[]
                for segment in a.model.segments:
                    if len(segment)!=2 or any(len(p)<2 for p in segment):continue
                    if any(len(p)>2 and abs(p[2]-b.elevation)>1e-4 for p in segment):continue
                    edge=Edge.ByVertices([Vertex.ByCoordinates(*p[:2],0) for p in segment],silent=True)
                    if edge is not None and Edge.Length(edge)>1e-6 and Topology.Contains(f,edge,silent=True):edges.append(edge)
                if not edges:raise ValueError("No segment network within this boundary.")
                if len(edges)>10000:raise ValueError("More than 10000 input segments. Simplify the network.")
                graph=(TGraph.SegmentGraph if a.graph_mode=="segments" else TGraph.AxialGraph)(edges,silent=True)
            elif a.graph_mode=='grid_shell':
                graph=TGraph.ByTopology(shell,direct=True,viaSharedTopologies=False,useInternalVertex=True,ontology=False,silent=True)
            elif a.graph_mode=='isovist_intersection':
                graph=isovist_intersection_graph(f,points,a)
            else:
                graph=visibility_graph(f,points)
            if not graph:raise ValueError("TopologicPy could not construct the graph.")
            gj,vertices,edges=graph_json(graph)
            # Call the documented TopologicPy API, preserving vertex/edge result ordering.
            if tulip_key:
                data=TGraph.AngularTulipAnalysis(graph,radius=a.radius,radiusType=a.radius_type,weighting=None if a.weighting=="none" else a.weighting,tulipBins=a.tulip_bins,colorize=False,silent=True)
                if not data:raise ValueError("Angular Tulip analysis returned no result.")
                scores=data[tulip_key]
            elif a.metric in {'DepthMap','MeanDepth'}:
                if a.weight!='topological':raise ValueError('Depth analyses currently support topological distance only.')
                if a.metric=='MeanDepth':
                    method=getattr(TGraph,'MeanDepth',None)
                    if not callable(method):raise ValueError('This TopologicPy installation lacks TGraph.MeanDepth. Update TopologicPy in your existing environment.')
                    result=method(graph,silent=True)
                    scores=[result.get(v['index']) for v in TGraph.Vertices(graph)]
                else:
                    native_vertices=TGraph.Vertices(graph,asTopologic=True,useRepresentation=False)
                    native_edges=TGraph.Edges(graph,asTopologic=True,useRepresentation=False)
                    native=Graph.ByVerticesEdges(native_vertices,native_edges)
                    scores=Graph.DepthMap(native,vertices=native_vertices,type='topological')
            else:
                engine=TGraph if isinstance(graph,TGraph) else Graph
                method=engine.BetweennessCentrality if a.metric=="Choice" else engine.DegreeCentrality if a.metric=="Connectivity" else engine.ClosenessCentrality if a.metric=="Integration" else getattr(engine,a.metric)
                kwargs={"normalize":a.normalize,"nxCompatible":False,"weightKey":None if a.weight=="topological" else "length","type":a.weight,"silent":True}
                kwargs.update(radius=a.radius,radiusType=a.radius_type,algorithm=a.algorithm,weighting=None if a.weighting=="none" else a.weighting,tulipBins=a.tulip_bins,step=a.step)
                if a.metric in {"Connectivity","DegreeCentrality"}:kwargs["weightKey"]=None
                params=inspect.signature(method).parameters
                kwargs={k:v for k,v in kwargs.items() if k in params}
                scores=method(graph,**kwargs)
            if scores is None:raise ValueError("The analysis API returned no result. Check graph connectivity.")
            line_mode=a.graph_mode in {"segments","axial","axial_generated"}
            records=TGraph.Vertices(graph)
            objects=[TGraph.VertexOriginator(graph,record) for record in records] if line_mode else vertices
            if len(scores)!=len(objects):raise ValueError("Analysis result length did not match the graph elements.")
            for i,(obj,value) in enumerate(zip(objects,scores)):
                if line_mode:
                    line=[[Vertex.X(v),Vertex.Y(v)] for v in [Edge.StartVertex(obj),Edge.EndVertex(obj)]]
                    elements.append({"id":i,"point":[(line[0][0]+line[1][0])/2,(line[0][1]+line[1][1])/2],"line":line,"value":clean(value),"metrics":{"length_m":Edge.Length(obj)}})
                else:
                    p=gj['nodes'][i]
                    if a.graph_mode=='grid_shell':
                        cell=TGraph.VertexOriginator(graph,records[i])
                        if not Topology.IsInstance(cell,'Face'):raise ValueError('TGraph.ByTopology did not preserve the originating grid face.')
                    else:
                        cell=cell_by_point[tuple(round(c,6) for c in p)]
                    display=face_data(cell)
                    elements.append({"id":i,"point":p,"polygon":display['outer'],"holes":display['holes'],"value":clean(value)})
            name=SYNTAX[a.metric]
        if not elements:raise ValueError("No analysis elements could be computed.")
        unit="m²" if a.metric=="area" else "m" if a.metric in {"perimeter","d_max","d_min","d_avg","v_max","v_min","v_d","drift","closed_perimeter","average_radial"} else "unitless"
        if a.kind=='syntax' and a.weight=='metric' and a.metric in {'DepthMap','MeanDepth'}:unit='m'
        if a.kind=='syntax' and a.weight=='metric' and a.metric=='Integration' and not a.normalize:unit='1/m'
        return {"elements":elements,"graph":gj,"metric":a.metric,"name":name,"unit":unit,"source":"topologicpy","engine_version":version('topologicpy'),"parameters":a.model_dump(exclude={"model"}),"axial_report":axial_report,"warnings":warnings,"elapsed":time.perf_counter()-start}
    except Exception as exc:raise HTTPException(422,str(exc)) from exc
