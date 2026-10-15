"""TopologicLab: geometry adapters and analysis service."""
from __future__ import annotations
import os
import tempfile
import time
import json
from pathlib import Path
from importlib.metadata import version

# Select the engine before any TopologicPy import initializes the Core facade.
os.environ.setdefault("TOPOLOGICPY_CORE_BACKEND", "pythonocc")

from fastapi import FastAPI, UploadFile, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from topologicpy.Face import Face
from topologicpy.Topology import Topology
from topologicpy.TGraph import TGraph
from topologicpy.Core import Core
from .geometry import import_geometry
from .routing import prepare
from .ifc_geometry import import_ifc
from .building_analysis import analyze_building,prepare_building

ENGINE = Core.Backend()

app = FastAPI(title="TopologicLab", version="1.0.0")
origins = os.environ.get("ALLOWED_ORIGINS", "http://127.0.0.1:8017,http://localhost:8017,http://127.0.0.1:8000,http://localhost:8000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"],expose_headers=["Server-Timing"])
app.add_middleware(GZipMiddleware,minimum_size=1000,compresslevel=5)

class RequestTimingMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope.get('path','').startswith('/api/'):
            return await self.app(scope,receive,send)
        started=time.perf_counter()
        async def timed_send(message):
            if message['type']=='http.response.start':
                headers=list(message.get('headers',[]))
                timing=f'request;dur={(time.perf_counter()-started)*1000:.3f}'.encode()
                for i,(key,value) in enumerate(headers):
                    if key.lower()==b'server-timing':headers[i]=(key,value+b', '+timing);break
                else:headers.append((b'server-timing',timing))
                message={**message,'headers':headers}
            await send(message)
        await self.app(scope,receive,timed_send)
app.add_middleware(RequestTimingMiddleware)

def auth(authorization: str | None = Header(default=None)):
    token = os.environ.get("TOPOLOGICLAB_API_TOKEN") or os.environ.get("SPATIAL_API_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "Invalid analysis service token.")

from .models import Analysis,Boundary,Model,SYNTAX,ISO,finite_coords
from .analysis import analyze

@app.get("/api/health", dependencies=[Depends(auth)])
def health():
    return {"status":"ok","app_name":"TopologicLab","app_revision":"topologiclab-20261015-1","version":version("topologicpy"),"backend":type(ENGINE).__name__,"metrics":SYNTAX,"isovist_metrics":ISO,"capabilities":{"axial_lines":callable(getattr(Face,"AxialEdges",None)),"ifc":True,"building_3d":True,"navigation_api":True,"clearance":True,"isovist_boundary_types":True},"limits":{"upload_mb":25,"points":10000}}

@app.get("/api/example", dependencies=[Depends(auth)])
async def example_building():
    return await run_in_threadpool(import_ifc,Path(__file__).resolve().parents[1]/"examples"/"two-storey-demo.ifc","Two-storey demo")

@app.post("/api/import", dependencies=[Depends(auth)])
async def import_file(file: UploadFile):
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in {".dxf",".obj",".3dm",".brep",".brp",".ifc"}:raise HTTPException(400,"Unsupported file format.")
    content=await file.read(25*1024*1024+1)
    if len(content)>25*1024*1024:raise HTTPException(413,"Maximum floor plan size is 25 MB.")
    try:
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/("plan"+suffix);path.write_bytes(content)
            return await run_in_threadpool(import_ifc if suffix==".ifc" else import_geometry,path,Path(file.filename).name)
    except Exception as exc:raise HTTPException(422,str(exc)) from exc

@app.post('/api/path/prepare',dependencies=[Depends(auth)])
def prepare_path_graph(a:Analysis):
    started=time.perf_counter()
    try:
        entry,reused=prepare_building(a)
        return {'status':'ready','graph_reused':reused,'nodes':len(entry['nodes']),'edges':len(entry['edges']),'graph':{'nodes':[n['point'] for n in entry['nodes']],'edges':[[e['src'],e['dst']] for e in entry['edges']]},'elapsed':time.perf_counter()-started}
    except Exception as error:raise HTTPException(422,str(error)) from error

@app.post("/api/analyze", dependencies=[Depends(auth)])
def analyze_endpoint(a:Analysis):
    started=time.perf_counter()
    try:result=analyze_building(a)
    except HTTPException:raise
    except Exception as exc:raise HTTPException(422,str(exc)) from exc
    analysis_ms=(time.perf_counter()-started)*1000
    serial_started=time.perf_counter()
    # The result is already plain JSON data. Avoid a second recursive conversion
    # of every grid coordinate and graph record by FastAPI's jsonable_encoder.
    response=JSONResponse(result)
    serialize_ms=(time.perf_counter()-serial_started)*1000
    response.headers['Server-Timing']=f'analysis;dur={analysis_ms:.3f}, serialize;dur={serialize_ms:.3f}'
    return response

app.mount("/",StaticFiles(directory=Path(__file__).resolve().parents[1]/"dist",html=True),name="workspace")
