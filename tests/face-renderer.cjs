const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const sandbox={console};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist/face-renderer.js'),'utf8'),sandbox);
vm.runInContext(`
const concave={outer:[[0,0,0],[4,0,0],[4,1,0],[1,1,0],[1,4,0],[0,4,0]],holes:[[[.2,.2,0],[.8,.2,0],[.8,.8,0],[.2,.8,0]]]};
const data=BuildingFaceRenderer.geometry(concave);
function inside(p,a,b,c){const side=(p,a,b)=>(p[0]-b[0])*(a[1]-b[1])-(a[0]-b[0])*(p[1]-b[1]);const d=[side(p,a,b),side(p,b,c),side(p,c,a)];return !(d.some(v=>v<0)&&d.some(v=>v>0))}
function parity(p,g){let count=0;for(let i=0;i<g.triangles.length;i+=3)if(inside(p,...g.triangles.slice(i,i+3)))count++;return count%2===1}
for(const [p,expected] of [[[3,.6],true],[[2.13,2.07],false],[[.45,.5],false],[[.5,3],true]])if(parity(p,data)!==expected)throw Error('Concave/holed face stencil parity');
const reverse=BuildingFaceRenderer.geometry({outer:[...concave.outer].reverse(),holes:concave.holes.map(r=>[...r].reverse())});
for(const p of [[3,.6],[2.13,2.07],[.45,.5],[.5,3]])if(parity(p,data)!==parity(p,reverse))throw Error('Winding changes surface visibility '+JSON.stringify(p)+' '+parity(p,data)+' '+parity(p,reverse));
const calls=[],constants=['VERTEX_SHADER','FRAGMENT_SHADER','COMPILE_STATUS','LINK_STATUS','ARRAY_BUFFER','FLOAT','CULL_FACE','BLEND','SRC_ALPHA','ONE_MINUS_SRC_ALPHA','LEQUAL','COLOR_BUFFER_BIT','DEPTH_BUFFER_BIT','STENCIL_BUFFER_BIT','STENCIL_TEST','ALWAYS','KEEP','INVERT','DEPTH_TEST','TRIANGLES','NOTEQUAL','POLYGON_OFFSET_FILL','LINE_LOOP','STREAM_DRAW'];
const gl=Object.fromEntries(constants.map((name,i)=>[name,1<<i]));
for(const name of ['createShader','createProgram','createBuffer'])gl[name]=()=>({});
for(const name of ['getShaderParameter','getProgramParameter'])gl[name]=()=>true;
gl.getAttribLocation=()=>0;gl.getUniformLocation=()=>({});
for(const name of ['shaderSource','compileShader','attachShader','linkProgram','viewport','clearColor','depthMask','colorMask','stencilMask','clear','useProgram','bindBuffer','enableVertexAttribArray','vertexAttribPointer','disable','enable','blendFunc','depthFunc','bufferData','drawArrays','stencilFunc','stencilOp','polygonOffset','uniform4fv'])gl[name]=(...args)=>calls.push([name,...args]);
const renderer=new BuildingFaceRenderer({width:800,height:600,getContext:()=>gl});
renderer.render([{s:concave,fill:'#abcdef',depth:0},{s:concave,fill:'rgb(20,40,60)',element:{},depth:0},{s:concave,fill:'rgba(80,90,100,0.2)',context:true,depth:0}],p=>[...p,1]);
if(!calls.some(([n,v])=>n==='disable'&&v===gl.CULL_FACE))throw Error('Back-face culling remains enabled');
if(!calls.some(([n,v])=>n==='enable'&&v===gl.DEPTH_TEST))throw Error('Depth test missing');
if(!calls.some(([n,v])=>n==='stencilOp'&&v===gl.KEEP))throw Error('Stencil hole mask missing');
if(!calls.some(([n,a,b])=>n==='polygonOffset'&&a===-1&&b===-1))throw Error('Analysis layer has no coplanar depth bias');
if(!calls.some(([n,v])=>n==='depthMask'&&v===false))throw Error('Translucent context overwrites scene depth');
`,sandbox);
console.log('PASS face geometry parity, reversed winding, depth/stencil passes and coplanar layer bias (mock WebGL)');
