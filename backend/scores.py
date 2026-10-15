"""Shared TopologicPy score dispatch for the universal navigation graph."""
import inspect
from topologicpy.TGraph import TGraph
from topologicpy.Graph import Graph

def scores_for(graph,a):
    tulip_key={"TulipChoice":"choice","TulipIntegration":"integration","NAIN":"nain","NACH":"nach","TulipNodeCount":"nodeCount","TulipTotalDepth":"totalDepth","TulipTotalWeight":"totalWeight"}.get(a.metric)
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
            scores=[sum(TGraph.DepthMap(graph,source=v['index'],silent=True).values()) for v in TGraph.Vertices(graph)]
    else:
        engine=TGraph if isinstance(graph,TGraph) else Graph
        method=engine.BetweennessCentrality if a.metric=="Choice" else engine.DegreeCentrality if a.metric=="Connectivity" else engine.ClosenessCentrality if a.metric=="Integration" else getattr(engine,a.metric)
        kwargs={"normalize":a.normalize,"nxCompatible":False,"weightKey":None if a.weight=="topological" else "length","type":a.weight,"silent":True}
        kwargs.update(radius=a.radius,radiusType=a.radius_type,algorithm=a.algorithm,weighting=None if a.weighting=="none" else a.weighting,tulipBins=a.tulip_bins,step=a.step)
        if a.metric in {"Connectivity","DegreeCentrality"}:kwargs["weightKey"]=None
        params=inspect.signature(method).parameters
        kwargs={k:v for k,v in kwargs.items() if k in params}
        scores=method(graph,**kwargs)
    return scores
