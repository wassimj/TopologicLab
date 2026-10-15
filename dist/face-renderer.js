/* Depth-buffered, double-sided planar faces. Stencil parity preserves concave
   boundaries and holes without a triangulation dependency or triangle fans
   incorrectly filling holes. The final plane quad writes true fragment depth. */
class BuildingFaceRenderer {
 constructor(canvas){
  this.cache=new WeakMap();this.canvas=canvas;this.gl=canvas.getContext('webgl',{alpha:false,antialias:true,depth:true,stencil:true,preserveDrawingBuffer:true});
  if(!this.gl)return;
  const gl=this.gl;
  const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s};
  this.program=gl.createProgram();gl.attachShader(this.program,shader(gl.VERTEX_SHADER,'attribute vec4 position; void main(){gl_Position=position;}'));gl.attachShader(this.program,shader(gl.FRAGMENT_SHADER,'precision mediump float; uniform vec4 colour; void main(){gl_FragColor=colour;}'));gl.linkProgram(this.program);if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(this.program));
  this.position=gl.getAttribLocation(this.program,'position');this.colour=gl.getUniformLocation(this.program,'colour');this.buffer=gl.createBuffer();
 }
 static geometry(s){
  const rings=[s.outer,...(s.holes||[])].filter(r=>r?.length>=3),outer=rings[0];if(!outer)return null;
  const sub=(a,b)=>a.map((v,i)=>v-(b[i]||0)),dot=(a,b)=>a.reduce((v,x,i)=>v+x*b[i],0),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],normalise=v=>{const n=Math.hypot(...v);return n>1e-12?v.map(x=>x/n):null};
  const origin=outer[0],u=outer.slice(1).map(p=>normalise(sub(p,origin))).find(Boolean);if(!u)return null;
  const normal=outer.slice(2).map(p=>normalise(cross(u,sub(p,origin)))).find(Boolean);if(!normal)return null;const v=cross(normal,u);
  let x0=Infinity,x1=-Infinity,y0=Infinity,y1=-Infinity;const triangles=[];
  for(const ring of rings){for(const p of ring){const q=sub(p,origin),x=dot(q,u),y=dot(q,v);x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y)}for(let i=1;i<ring.length-1;i++)triangles.push(ring[0],ring[i],ring[i+1]);}
  const at=(x,y)=>origin.map((q,k)=>q+x*u[k]+y*v[k]),a=at(x0,y0),b=at(x1,y0),c=at(x1,y1),d=at(x0,y1);
  return {triangles,quad:[a,b,c,a,c,d],rings};
 }
 static rgba(value,alpha=1){if(value.startsWith('#')){let h=value.slice(1);if(h.length===3)h=h.split('').map(c=>c+c).join('');return [0,2,4].map(i=>parseInt(h.slice(i,i+2),16)/255).concat(alpha*(h.length===8?parseInt(h.slice(6,8),16)/255:1))}const n=value.match(/[\d.]+/g).map(Number);return [n[0]/255,n[1]/255,n[2]/255,alpha*(n[3]??1)]}
 render(items,clip,referenceLines=[]){
  const gl=this.gl;if(!gl)return;gl.viewport(0,0,this.canvas.width,this.canvas.height);gl.clearColor(.949,.961,.976,1);gl.depthMask(true);gl.colorMask(true,true,true,true);gl.stencilMask(255);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT|gl.STENCIL_BUFFER_BIT);gl.useProgram(this.program);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);gl.enableVertexAttribArray(this.position);gl.vertexAttribPointer(this.position,4,gl.FLOAT,false,0,0);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthFunc(gl.LEQUAL);
  const draw=(points,mode)=>{gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points.flatMap(clip)),gl.STREAM_DRAW);gl.drawArrays(mode,0,points.length)};
  if(referenceLines.length){gl.enable(gl.DEPTH_TEST);gl.depthMask(false);gl.uniform4fv(this.colour,BuildingFaceRenderer.rgba('#dfe5ee'));draw(referenceLines,gl.LINES)}
  // Surfaces write depth. Translucent context is drawn afterwards, tests that
  // depth, and never overwrites it. Coplanar layers have explicit depth bias.
  const layers=[items.filter(i=>!i.context&&!i.element),items.filter(i=>!i.context&&i.element),items.filter(i=>i.context).sort((a,b)=>a.depth-b.depth)];
  for(const layer of layers)for(const item of layer){if(!item.fill&&!item.stroke)continue;let g=this.cache.get(item.s.outer);if(!g){g=BuildingFaceRenderer.geometry(item.s);if(g)this.cache.set(item.s.outer,g)}if(!g)continue;
   gl.stencilMask(255);gl.clear(gl.STENCIL_BUFFER_BIT);gl.enable(gl.STENCIL_TEST);gl.stencilFunc(gl.ALWAYS,0,255);gl.stencilOp(gl.KEEP,gl.KEEP,gl.INVERT);gl.disable(gl.DEPTH_TEST);gl.depthMask(false);gl.colorMask(false,false,false,false);draw(g.triangles,gl.TRIANGLES);
   gl.colorMask(true,true,true,true);gl.stencilMask(0);gl.stencilFunc(gl.NOTEQUAL,0,255);gl.stencilOp(gl.KEEP,gl.KEEP,gl.KEEP);gl.enable(gl.DEPTH_TEST);gl.depthMask(!item.context);gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(item.context?4:item.element?-1:1,item.context?4:item.element?-1:1);
   if(item.fill){gl.uniform4fv(this.colour,BuildingFaceRenderer.rgba(item.fill,item.alpha??1));draw(g.quad,gl.TRIANGLES)}
   gl.disable(gl.POLYGON_OFFSET_FILL);gl.disable(gl.STENCIL_TEST);
   if(item.stroke){gl.depthMask(false);gl.uniform4fv(this.colour,BuildingFaceRenderer.rgba(item.stroke));for(const ring of g.rings)draw(ring,gl.LINE_LOOP)}
  }
  gl.depthMask(true);gl.stencilMask(255);gl.disable(gl.STENCIL_TEST);
 }
}
