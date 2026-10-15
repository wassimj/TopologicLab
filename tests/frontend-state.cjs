const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root=require('path').join(__dirname,'../dist/'),map=new Map();
function element(id=''){return {get id(){return id},set id(v){id=v;map.set(v,this)},value:'',checked:false,hidden:false,disabled:false,style:{},children:[],options:[],dataset:{},classList:{toggle(){},add(){},remove(){}},parentElement:{before(){},after(){},querySelector(){return element()}},previousElementSibling:{},selectedOptions:[{textContent:'Ground floor'}],append(...items){this.children.push(...items)},prepend(){},insertBefore(){},after(){},before(){},replaceChildren(...items){this.children=items;if(items[0]?.value)this.value=items[0].value},querySelector(){return element()},querySelectorAll(){return []},addEventListener(name,fn){this['on'+name]=fn},getBoundingClientRect(){return {width:900,height:600}},setPointerCapture(){},showModal(){},close(){},click(){},getContext(type){return type==='webgl'?null:context},set innerHTML(text){parse(text)},get innerHTML(){return ''}}}
function parse(text){for(const match of text.matchAll(/<(input|select|canvas|button|div|span|p|section|dialog|strong|small)[^>]*\bid="([^"]+)"[^>]*>/g)){const tag=match[0],id=match[2],e=map.get(id)||element(id);e.value=tag.match(/\bvalue="([^"]*)"/)?.[1]||e.value;e.checked=/\bchecked\b/.test(tag);map.set(id,e)}for(const m of text.matchAll(/<select[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){const e=map.get(m[1]);e.value=m[2].match(/<option value="([^"]*)"/)?.[1]||''}}
const context=new Proxy({},{get(o,k){if(!(k in o))o[k]=()=>{};return o[k]},set(o,k,v){o[k]=v;return true}});
parse(fs.readFileSync(root+'index.html','utf8'));
const sandbox={console,structuredClone,Path2D:class{moveTo(){}lineTo(){}closePath(){}},devicePixelRatio:1,location:{origin:'http://localhost'},document:{getElementById:id=>map.get(id),createElement:()=>element(),querySelector:()=>element(),querySelectorAll:()=>[],body:element(),addEventListener(){}},ResizeObserver:class{observe(){}},Option:class{constructor(text,value){this.textContent=text;this.value=value}},fetch:async()=>{throw Error('No network in unit test')},setTimeout,clearTimeout,setInterval,clearInterval,Blob,URL,FormData:class{}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(root+'default-plan.js','utf8'),sandbox);vm.runInContext(fs.readFileSync(root+'face-renderer.js','utf8'),sandbox);vm.runInContext(fs.readFileSync(root+'building.js','utf8'),sandbox);
vm.runInContext(`
 state.view.scale=5; if(!state.model.faces.length)throw Error('Default model failed to load');
 const face={outer:[[0,0,0],[4,0,1],[4,4,2],[0,4,1]]};
 for(const yaw of [-3,-1,.4,2,Math.PI])for(const pitch of [-1,-.3,.2,.8,Math.PI/2]){state.view.yaw=yaw;state.view.pitch=pitch;const p=[2,1,.75],q=project(p),r=unprojectOnPlane(q[0],q[1],face);if(Math.max(...p.map((v,i)=>Math.abs(v-r[i])))>1e-7)throw Error('3D picking projection mismatch')}
 // Perspective foreshortening, GPU clip coordinates and camera-plane picking agree.
 state.view.yaw=0;state.view.pitch=.5;state.view.centre=[0,0,0];state.view.pan=[31,-17];state.view.scale=5;
 const cam=camera(),at=(x,depth)=>cam.right.map((v,i)=>x*v+cam.toward[i]*depth);
 if(Math.abs(project(at(1,2))[0]-state.width/2-state.view.pan[0])<=Math.abs(project(at(1,-2))[0]-state.width/2-state.view.pan[0]))throw Error('Camera is still orthographic');
 const world=[2,1,.75],gpu=clipPosition(world),pixel=project(world);
 if(Math.abs((gpu[0]/gpu[3]+1)*state.width/2-pixel[0])>1e-8||Math.abs((1-gpu[1]/gpu[3])*state.height/2-pixel[1])>1e-8)throw Error('GPU projection mismatch');
 const vertical={outer:[[0,0,0],[0,4,0],[0,4,4],[0,0,4]]},vp=[0,2,1],vscreen=project(vp),back=unprojectOnPlane(vscreen[0],vscreen[1],vertical);
 // At yaw=0 the x=0 plane is edge-on. Pick a nonparallel camera angle.
 state.view.yaw=.7;const vpix=project(vp),vback=unprojectOnPlane(vpix[0],vpix[1],vertical);if(!vback||Math.hypot(...vp.map((v,i)=>v-vback[i]))>1e-7)throw Error('Vertical face picking');
 const clipped=clipRing([at(-1,cam.distance+1),at(1,cam.distance-2),at(-1,cam.distance-2)]);if(clipped.length<3||clipped.some(p=>cameraPoint(p).w<camera().near-1e-7))throw Error('Near-plane clipping');
 state.tab='syntax';setMetrics();updateContext();const q=request();if(q.storey!==null)throw Error('Whole-building scope must be default');
 $('scope').value='storey';if(request().storey!==$('boundary').value)throw Error('Storey scope missing');
 state.tab='isovist';setMetrics();updateContext();if(request().storey!==$('boundary').value)throw Error('Isovists must stay on selected storey');
 $('clearance').value='.25';if(request().clearance!==.25)throw Error('Clearance missing from request');
 const r={elements:[{id:0,point:[1,1,0],polygon:[[0,0,0],[2,0,0],[2,2,0]],storey:'0',value:3}],graph:{nodes:[[1,1,0]],edges:[]},name:'Connectivity',unit:'unitless'};setResult(r);if($('rangeMin').value!==3||$('rangeMax').value!==3)throw Error('Palette range');
`,sandbox);
vm.runInContext(`
 const transported=normalizeModel({...state.model,isovist_faces:[{outer:[[0,0,1.6],[4,0,1.6],[4,4,1.6]],holes:[[[1,1,1.6],[2,1,1.6],[2,2,1.6]]],hole_types:['hole'],storey:'0'}]});
 if(transported.isovist_faces[0].hole_types[0]!=='hole')throw Error('Boundary roles lost during browser normalization');
 state.tab='path';state.result={route:{points:[[0,0,0],[1,1,0]],length:2}};$('pathLength').textContent='2 m';
 $('clearance').onchange();if(state.result!==null||$('pathLength').textContent!=='—')throw Error('Clearance must clear stale paths');
`,sandbox);
console.log('PASS frontend initialization, 3D projection/picking algebra, scope controls and colour-range state (mock DOM; not visual browser QA)');
