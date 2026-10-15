"""Viewport mesh adapter using TopologicPy IFC; navigation extraction is in IFC.NavigationModel."""
import math
from collections import defaultdict
import numpy as np
from topologicpy.IFC import IFC

BOX_TRIANGLES=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
def box_mesh(bounds):
 lo,hi=bounds;x,y,z=lo;X,Y,Z=hi
 return {'vertices':[[x,y,z],[X,y,z],[X,Y,z],[x,Y,z],[x,y,Z],[X,y,Z],[X,Y,Z],[x,Y,Z]],'triangles':BOX_TRIANGLES,'bounds':bounds,'bounding_box':True}

def triangulate(vertices,face):
 ids=list(face)
 if len(ids)<3:return []
 if len(ids)==3:return [ids]
 pts=np.asarray([vertices[i] for i in ids]);normal=np.sum(np.cross(pts,np.roll(pts,-1,axis=0)),axis=0);axis=int(np.argmax(np.abs(normal)));p=np.delete(pts,axis,axis=1)
 cross=lambda a,b,c:float((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
 area=sum(p[i,0]*p[(i+1)%len(p),1]-p[(i+1)%len(p),0]*p[i,1] for i in range(len(p)));sign=1 if area>=0 else -1
 remaining=list(range(len(ids)));out=[]
 while len(remaining)>3:
  found=False
  for k,b in enumerate(remaining):
   a,c=remaining[k-1],remaining[(k+1)%len(remaining)];turn=sign*cross(p[a],p[b],p[c])
   if abs(turn)<1e-12:remaining.pop(k);found=True;break
   if turn<0:continue
   if any(all(sign*cross(p[u],p[v],p[j])>=-1e-12 for u,v in [(a,b),(b,c),(c,a)]) for j in remaining if j not in [a,b,c]):continue
   out.append([ids[a],ids[b],ids[c]]);remaining.pop(k);found=True;break
  if not found:return []
 if len(remaining)==3:out.append([ids[i] for i in remaining])
 return out

def orient_prisms(vertices,faces):
 # The fast IFC reader emits extrusion caps in profile order; orient their
 # paired caps and side strips consistently before finding upward surfaces.
 faces=[list(f) for f in faces];v=np.asarray(vertices);i=0
 while i+1<len(faces):
  bottom,top=faces[i:i+2];n=len(bottom)
  if n<3 or len(top)!=n or i+n+2>len(faces):i+=1;continue
  delta=v[top[::-1]]-v[bottom]
  if np.max(np.abs(delta-delta.mean(axis=0)))>1e-7 or np.linalg.norm(delta.mean(axis=0))<1e-10:i+=1;continue
  allowed=set(bottom+top);sides=faces[i+2:i+n+2]
  if any(len(f)!=4 or not set(f)<=allowed for f in sides):i+=1;continue
  pts=v[bottom];normal=np.sum(np.cross(pts,np.roll(pts,-1,axis=0)),axis=0)
  if np.dot(normal,delta.mean(axis=0))>0:
   faces[i]=bottom[::-1];faces[i+1]=top[::-1]
  else:
   for k in range(i+2,i+n+2):faces[k]=faces[k][::-1]
  i+=n+2
 return faces

class Product:
 def __init__(self,entity):self.entity=entity;self.type=entity.type;self.Name=entity.args[2] if len(entity.args)>2 else '';self.ObjectType=entity.args[4] if len(entity.args)>4 else ''
 def id(self):return self.entity.id
 def is_a(self,name=None):
  if name is None:return 'Ifc'+self.type[3:].title().replace('Standardcase','StandardCase').replace('Stairflight','StairFlight').replace('Rampflight','RampFlight').replace('Openingelement','OpeningElement').replace('Furnishingelement','FurnishingElement').replace('Transportelement','TransportElement').replace('Buildingelementproxy','BuildingElementProxy').replace('Wallstandardcase','WallStandardCase').replace('Slabstandardcase','SlabStandardCase')
  name=name.upper()
  if name=='IFCOPENINGELEMENT':return self.type in {'IFCOPENINGELEMENT','IFCOPENINGSTANDARDCASE','IFCVOIDINGFEATURE','IFCFEATUREELEMENTSUBTRACTION'}
  if name=='IFCFURNISHINGELEMENT':return self.type in {'IFCFURNISHINGELEMENT','IFCFURNITURE','IFCSYSTEMFURNITUREELEMENT'}
  return self.type==name or (name in {'IFCWALL','IFCSLAB','IFCDOOR','IFCWINDOW'} and self.type.startswith(name))
 @property
 def PredefinedType(self):return self.entity.args[8] if len(self.entity.args)>8 and self.type in {'IFCSLAB','IFCSLABSTANDARDCASE','IFCSLABELEMENTEDCASE','IFCROOF','IFCTRANSPORTELEMENT'} else None

def read_ifc(path):
 model=IFC.ModelByPath(str(path),silent=True)
 if model is None:raise ValueError('TopologicPy could not parse this IFC file.')
 entities=IFC.Entities(model,silent=True)
 # TopologicPy's parsed reference token is REF (case normalised here).
 def ref(value):return entities.get(value[1]) if isinstance(value,tuple) and len(value)==2 and str(value[0]).upper()=='REF' else None
 def refs(values):return [e for v in values or [] if (e:=ref(v)) is not None]
 parents={};contained={};children=defaultdict(list);voids=defaultdict(list)
 for e in entities.values():
  if len(e.args)<6:continue
  if e.type in {'IFCRELAGGREGATES','IFCRELNESTS'}:
   parent=ref(e.args[4]);
   if parent:
    for child in refs(e.args[5]):parents[child.id]=parent.id;children[parent.id].append(child.id)
  elif e.type=='IFCRELCONTAINEDINSPATIALSTRUCTURE':
   target=ref(e.args[5]);
   if target:
    for child in refs(e.args[4]):contained[child.id]=target.id
  elif e.type=='IFCRELVOIDSELEMENT':
   host,opening=ref(e.args[4]),ref(e.args[5])
   if host and opening:voids[host.id].append(opening.id)
 def ancestor(ident,types):
  seen=set()
  while ident not in seen:
   seen.add(ident);parent=parents.get(ident)
   if parent is None:return None
   if entities[parent].type in types:return parent
   ident=parent
 def container(ident):
  seen=set()
  while ident not in seen:
   seen.add(ident)
   if ident in contained:return contained[ident]
   if ident not in parents:return None
   ident=parents[ident]
  return None
 # Unit-aware storey placements use the same parsed STEP entities. Geometry
 # itself is returned in world metres by IFC.MeshData.
 prefixes={'EXA':1e18,'PETA':1e15,'TERA':1e12,'GIGA':1e9,'MEGA':1e6,'KILO':1e3,'HECTO':1e2,'DECA':10,'DECI':.1,'CENTI':.01,'MILLI':.001,'MICRO':1e-6,'NANO':1e-9,None:1}
 def numeric(v):
  if isinstance(v,(int,float)):return float(v)
  if isinstance(v,tuple) and len(v)==3:return numeric(v[2][0])
  return float(v)
 def unit(e,seen=None):
  seen=set() if seen is None else seen
  if e is None or e.id in seen:raise ValueError('Invalid IFC length unit')
  seen.add(e.id)
  if e.type=='IFCSIUNIT':return prefixes.get(e.args[2],1)
  if e.type in {'IFCCONVERSIONBASEDUNIT','IFCCONVERSIONBASEDUNITWITHOFFSET'}:
   measure=ref(e.args[3]);return numeric(measure.args[0])*unit(ref(measure.args[1]),seen)
  raise ValueError('Unsupported IFC length unit')
 scale=1.;angle_scale=1.
 for assignment in entities.values():
  if assignment.type=='IFCUNITASSIGNMENT':
   for u in refs(assignment.args[0]):
    if len(u.args)>1 and u.args[1]=='LENGTHUNIT':scale=unit(u)
    elif len(u.args)>1 and u.args[1]=='PLANEANGLEUNIT':angle_scale=unit(u)
 placement_cache={}
 def direction(value,default):
  e=ref(value);v=np.array(e.args[0] if e else default,dtype=float);v=np.pad(v,(0,3-len(v)));length=np.linalg.norm(v);return v/length if length else np.array(default,dtype=float)
 def axis(value):
  e=ref(value);matrix=np.eye(4)
  if e is None:return matrix
  point=ref(e.args[0]);p=list(point.args[0]) if point else [0,0,0];matrix[:3,3]=(p+[0,0,0])[:3]
  if e.type=='IFCAXIS2PLACEMENT2D':
   x=direction(e.args[1] if len(e.args)>1 else None,[1,0,0]);z=np.array([0,0,1]);y=np.cross(z,x)
  else:
   z=direction(e.args[1] if len(e.args)>1 else None,[0,0,1]);x=direction(e.args[2] if len(e.args)>2 else None,[1,0,0]);y=np.cross(z,x);y/=max(np.linalg.norm(y),1e-12);x=np.cross(y,z)
  matrix[:3,:3]=np.column_stack([x,y,z]);return matrix
 def placement(value,seen=None):
  e=ref(value)
  if e is None:return np.eye(4)
  if e.id in placement_cache:return placement_cache[e.id]
  seen=set() if seen is None else seen
  if e.id in seen:return np.eye(4)
  seen.add(e.id);matrix=placement(e.args[0],seen)@axis(e.args[1]);placement_cache[e.id]=matrix;return matrix
 storeys=[]
 for e in entities.values():
  if e.type=='IFCBUILDINGSTOREY':
   z=placement(e.args[5])[2,3]*scale if ref(e.args[5]) else float(e.args[9] or 0)*scale
   storeys.append({'id':str(e.id),'name':e.args[2] or f'Storey {len(storeys)+1}','elevation':float(z)})
 represented_types=sorted({e.type for e in entities.values() if len(e.args)>6 and (definition:=ref(e.args[6])) is not None and definition.type=='IFCPRODUCTDEFINITIONSHAPE'})
 data=IFC.MeshData(model,includeTypes=represented_types,excludeTypes=['IfcSpace','IfcAnnotation'],dictionaryMode='none',ontology=False,silent=True)
 if not data:raise ValueError('TopologicPy could not extract IFC geometry.')
 # Fill representation gaps using the same parsed entities, without a
 # second IFC parser. Composite-curve tread profiles are used by the duplex.
 def curve_points(e):
  if e is None:return []
  if e.type=='IFCPOLYLINE':return [(list(p.args[0])+[0,0,0])[:3] for p in refs(e.args[0])]
  if e.type=='IFCCOMPOSITECURVE':
   result=[]
   for segment in refs(e.args[0]):
    points=curve_points(ref(segment.args[2]))
    if segment.args[1] is False:points=points[::-1]
    if result and points and np.linalg.norm(np.array(result[-1])-points[0])<1e-7:points=points[1:]
    result.extend(points)
   return result
  if e.type=='IFCTRIMMEDCURVE':
   basis=ref(e.args[0])
   if basis is None or basis.type!='IFCCIRCLE':return []
   matrix=axis(basis.args[0]);radius=float(basis.args[1])
   def parameter(values):
    for value in values:
     point=ref(value)
     if point is not None:
      p=np.linalg.inv(matrix)@np.array([*(list(point.args[0])+[0,0,0])[:3],1]);return math.atan2(p[1],p[0])
     try:return numeric(value)*angle_scale
     except (ValueError,TypeError):continue
    return 0.
   start,end=parameter(e.args[1]),parameter(e.args[2]);sense=e.args[3] is not False
   if sense:
    while end<start:end+=2*math.pi
   else:
    while end>start:end-=2*math.pi
   angles=np.linspace(start,end,max(2,int(math.ceil(abs(end-start)/(math.pi/12)))+1))
   return [(matrix@np.array([radius*math.cos(t),radius*math.sin(t),0,1]))[:3].tolist() for t in angles]
  return []
 imported={p['id'] for p in data['product_ranges']}
 for e in entities.values():
  if len(e.args)<7:continue
  definition=ref(e.args[6])
  if definition is None or definition.type!='IFCPRODUCTDEFINITIONSHAPE':continue
  bodies=[r for r in refs(definition.args[2]) if str(r.args[1]).upper()=='BODY']
  for representation in bodies:
   for item in refs(representation.args[3]):
    direct=False;verts=[];faces=[];matrix=placement(e.args[5])
    if item.type in {'IFCPOLYGONALFACESET','IFCTRIANGULATEDFACESET'} and e.id not in imported:
     coords=ref(item.args[0]);verts=[(matrix@np.array([*p,1]))[:3].tolist() for p in coords.args[0]]
     if item.type=='IFCPOLYGONALFACESET':faces=[[int(i)-1 for i in f.args[0]] for f in refs(item.args[2])]
     else:faces=[[int(i)-1 for i in f] for f in item.args[3]]
     direct=True
    elif item.type=='IFCEXTRUDEDAREASOLID':
     profile=ref(item.args[0]);curve=ref(profile.args[2]) if profile and profile.type=='IFCARBITRARYCLOSEDPROFILEDEF' else None
     if curve is None or curve.type!='IFCCOMPOSITECURVE':continue
     points=curve_points(curve)
     if len(points)>1 and np.linalg.norm(np.array(points[0])-points[-1])<1e-7:points=points[:-1]
     if len(points)<3:continue
     n=len(points);vector=direction(item.args[2],[0,0,1])*float(item.args[3]);matrix=matrix@axis(item.args[1]);local=points+[(np.array(p)+vector).tolist() for p in points]
     verts=[(matrix@np.array([*p,1]))[:3].tolist() for p in local]
     faces=[list(range(n)),list(range(2*n-1,n-1,-1))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
    if not verts:continue
    verts=[[c*scale for c in p] for p in verts];start=len(data['vertices']);face_start=len(data['faces']);data['vertices'].extend(verts);data['faces'].extend([[i+start for i in f] for f in faces])
    data['product_ranges'].append({'id':e.id,'start':start,'end':len(data['vertices']),'face_start':face_start,'face_end':len(data['faces']),'tessellated':direct})
 def has_extrusion(entity):
  stack=[ref(entity.args[6])];seen=set()
  def walk(value):
   target=ref(value)
   if target is not None:stack.append(target)
   elif isinstance(value,(list,tuple)):
    for item in value:walk(item)
  while stack:
   item=stack.pop()
   if item is None or item.id in seen:continue
   seen.add(item.id)
   if item.type=='IFCEXTRUDEDAREASOLID':return True
   walk(item.args)
  return False
 meshes={};objects={};original_vertices=original_triangles=0
 for product in data['product_ranges']:
  ident=product['id'];obj=Product(entities[ident]);start,end=product['start'],product['end'];verts=data['vertices'][start:end]
  if not verts:continue
  faces=[[i-start for i in f] for f in data['faces'][product['face_start']:product['face_end']]]
  bounds=[np.min(verts,axis=0).tolist(),np.max(verts,axis=0).tolist()]
  if obj.is_a('IfcFurnishingElement') or obj.is_a('IfcOpeningElement'):
   if ident in meshes:bounds=[np.minimum(meshes[ident]['bounds'][0],bounds[0]).tolist(),np.maximum(meshes[ident]['bounds'][1],bounds[1]).tolist()]
   meshes[ident]=box_mesh(bounds);objects[ident]=obj
   original_vertices+=len(verts);original_triangles+=sum(max(0,len(f)-2) for f in faces)
   continue
  if not product.get('tessellated') and has_extrusion(entities[ident]):faces=orient_prisms(verts,faces)
  triangles=[t for face in faces for t in triangulate(verts,face)]
  if not triangles:continue
  v=np.asarray(verts);volume=sum(float(np.dot(v[t[0]],np.cross(v[t[1]],v[t[2]]))) for t in triangles)
  if volume<0:triangles=[t[::-1] for t in triangles]
  if ident in meshes:
   previous=meshes[ident];offset=len(previous['vertices']);previous['vertices'].extend(verts);previous['triangles'].extend([[i+offset for i in t] for t in triangles]);previous['bounds']=[np.minimum(previous['bounds'][0],bounds[0]).tolist(),np.maximum(previous['bounds'][1],bounds[1]).tolist()]
  else:meshes[ident]={'vertices':list(verts),'triangles':triangles,'bounds':bounds}
  objects[ident]=obj;original_vertices+=len(verts);original_triangles+=sum(max(0,len(f)-2) for f in faces)
 for ident,mesh in list(meshes.items()):
  if objects[ident].is_a('IfcFurnishingElement') or objects[ident].is_a('IfcOpeningElement'):meshes[ident]=box_mesh(mesh['bounds'])
 return {'model':model,'entities':entities,'meshes':meshes,'objects':objects,'storeys':storeys,'parents':parents,'children':children,'voids':voids,'container':container,'ancestor':ancestor,'scale':scale,'ref':ref,'placement':placement,'original_vertices':original_vertices,'original_triangles':original_triangles}
