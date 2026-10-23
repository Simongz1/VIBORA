'use strict';
const $=s=>document.querySelector(s);
const descriptions={component:['◇','MOOSE component','Any registered physics'],mesh:['▦','Mesh','GeneratedMesh'],variable:['φ','Scalar field','Lagrange · first order'],diffusion:['∇','Diffusion','MOOSE Diffusion'],boundary:['⊣','Boundary condition','DirichletBC'],solver:['ƒ','Solver','Steady / Transient'],output:['↗','Results','Exodus output']};
let catalog=[], graph={version:1,nodes:[],edges:[]}, selected=null, pending=null, generated='', drag=null, resolvedGraph=null, generationPending=false;
const clone=x=>JSON.parse(JSON.stringify(x));
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
function status(t){$('#status').textContent=t;}
function invalidate(){generated='';resolvedGraph=null;try{localStorage.setItem('vibora-draft',JSON.stringify(graph));}catch(e){}$('#issues').replaceChildren(el('p','Assembly changed. Check dependencies again.','muted'));scheduleCheck();}
let timer;
// Display zoom only: block coordinates stay unscaled, so saved graphs and layouts are unaffected.
let zoom=1;const ZOOM_MIN=0.1,ZOOM_MAX=2;
function scheduleCheck(){clearTimeout(timer);timer=setTimeout(()=>check(false,true),650);}
function spec(k){return catalog.find(x=>x.kind===k)||(k==='component'?{kind:k,params:{},inputs:[{name:'dependency',type:'object'}],outputs:[{name:'object',type:'object'}]}:undefined);}
function node(kind,x=80,y=60,label){return {id:'b_'+crypto.randomUUID().replaceAll('-',''),kind,label:label||descriptions[kind][1],params:clone(spec(kind).params),physics:'',method:'',implementation:'',x,y};}
const mooseCategories=['Materials','ICs','BCs','Postprocessors','Kernels','Variables','AuxVariables','AuxKernels','Functions','UserObjects','VectorPostprocessors','ScalarKernels','AuxScalarKernels','InterfaceKernels','DGKernels','Constraints','Mesh','MeshModifiers','Executioner','Preconditioning','Outputs','MultiApps','Transfers','Controls','Dampers','Adaptivity'];
function sizeCanvas(){
 const width=Math.max(1500,...graph.nodes.map(n=>n.x+240)),height=Math.max(1000,...graph.nodes.map(n=>n.y+240));
 $('#canvas').style.width=width+'px';$('#canvas').style.height=height+'px';
 $('#canvas').style.transform='scale('+zoom+')';
 $('#zoom-area').style.width=width*zoom+'px';$('#zoom-area').style.height=height*zoom+'px';
 $('#zoom-reset').textContent=Math.round(zoom*100)+'%';
}
function setZoom(value,anchorX,anchorY){
 // Keeps the canvas point under (anchorX, anchorY), in viewport pixels, in place; defaults to the view centre.
 const view=$('#viewport'),next=Math.min(ZOOM_MAX,Math.max(ZOOM_MIN,value));
 if(anchorX===undefined){anchorX=view.clientWidth/2;anchorY=view.clientHeight/2;}
 const x=(view.scrollLeft+anchorX)/zoom,y=(view.scrollTop+anchorY)/zoom;
 zoom=next;sizeCanvas();drawWires();
 view.scrollLeft=x*zoom-anchorX;view.scrollTop=y*zoom-anchorY;
}
function zoomToFit(onlyIfLarger){
 // A hidden tab or collapsed pane has no size to fit into; keep the current zoom then.
 const view=$('#viewport'),cards=[...document.querySelectorAll('.node')];if(!cards.length||view.clientWidth<60||view.clientHeight<60)return;
 const left=Math.min(...graph.nodes.map(n=>n.x)),top=Math.min(...graph.nodes.map(n=>n.y));
 const right=Math.max(...cards.map(c=>c.offsetLeft+c.offsetWidth)),bottom=Math.max(...cards.map(c=>c.offsetTop+c.offsetHeight));
 const fit=Math.min((view.clientWidth-40)/(right-left),(view.clientHeight-40)/(bottom-top),1);
 if(onlyIfLarger&&fit>=zoom)return;
 zoom=Math.min(ZOOM_MAX,Math.max(ZOOM_MIN,fit));sizeCanvas();drawWires();
 view.scrollLeft=left*zoom-20;view.scrollTop=top*zoom-20;
}
function add(kind,label,properties={}){
 const view=$('#viewport');let x=view.scrollLeft/zoom+Math.max(20,(view.clientWidth/zoom-188)/2),y=view.scrollTop/zoom+40;
 while(graph.nodes.some(n=>Math.abs(n.x-x)<195&&Math.abs(n.y-y)<130))y+=150;
 const n=Object.assign(node(kind,x,y,label),properties);graph.nodes.push(n);selected=n.id;render();inspect();invalidate();
 view.scrollTo({left:Math.max(0,n.x*zoom-(view.clientWidth-188*zoom)/2),top:Math.max(0,(n.y-40)*zoom)});status('Added '+n.label);return n;
}
function drawWires(){
 const svg=$('#wires');svg.replaceChildren();
 for(const e of graph.edges){
  const a=document.getElementById(e.from+'-out-'+e.out),b=document.getElementById(e.to+'-in-'+e.in);if(!a||!b)continue;
  const canvas=$('#canvas').getBoundingClientRect(),ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
  // Screen rectangles are scaled by the zoom; the SVG lives in unscaled canvas coordinates.
  const x1=(ar.right-canvas.left)/zoom-5,y1=(ar.top-canvas.top+ar.height/2)/zoom,x2=(br.left-canvas.left)/zoom+5,y2=(br.top-canvas.top+br.height/2)/zoom;
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d','M '+x1+' '+y1+' C '+(x1+65)+' '+y1+', '+(x2-65)+' '+y2+', '+x2+' '+y2);
  const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent='Click to remove connection';path.append(title);
  path.onclick=()=>{graph.edges=graph.edges.filter(x=>x!==e);render();inspect();invalidate();};svg.append(path);
 }
}
function render(){
 sizeCanvas();
 if(document.activeElement!==$('#model-request'))$('#model-request').value=graph.request||'';
 const solver=graph.nodes.find(n=>n.kind==='solver');$('#model-title').textContent=graph.title||'MOOSE model assembly';
 $('#nodes').replaceChildren();$('#counts').textContent=graph.nodes.length+' blocks · '+graph.edges.length+' connections';
 if(!graph.nodes.length){const hint=el('div',undefined,'empty-hint');hint.append(el('b','Start a model'),el('span','Add blocks from the library (or MOOSE objects with ＋ Add MOOSE object), connect their ports, and describe the physics. Open loads a saved graph.'));$('#nodes').append(hint);}
 for(const n of graph.nodes){
  const card=el('section',undefined,'node'+(selected===n.id?' selected':''));card.id=n.id;card.style.left=n.x+'px';card.style.top=n.y+'px';
  const head=el('div',undefined,'node-head');head.append(el('b',n.label),el('small',n.kind==='solver'?(n.params.type||'Steady')+' · '+(n.params.solve_type||'PJFNK'):(n.category||descriptions[n.kind][2])+(n.object_type?' · '+n.object_type:'')));card.append(head);
  head.onpointerdown=e=>{if(e.button!==0)return;selected=n.id;inspect();document.querySelectorAll('.node').forEach(c=>c.classList.toggle('selected',c.id===n.id));drag={n,x:e.clientX,y:e.clientY,ox:n.x,oy:n.y};head.setPointerCapture(e.pointerId);};
  head.onpointermove=e=>{if(!drag||drag.n!==n)return;n.x=Math.max(5,drag.ox+(e.clientX-drag.x)/zoom);n.y=Math.max(5,drag.oy+(e.clientY-drag.y)/zoom);card.style.left=n.x+'px';card.style.top=n.y+'px';drawWires();};
  head.onpointerup=()=>{drag=null;sizeCanvas();invalidate();};
  head.onpointercancel=()=>{drag=null;};
  const ports=el('div',undefined,'ports');
  for(const dir of ['in','out']){
   const col=el('div');
   for(const p of (n[dir==='in'?'inputs':'outputs']||spec(n.kind)[dir==='in'?'inputs':'outputs'])){
    const b=el('button',p.name,'port '+(dir==='out'?'output':'')+(pending&&pending.id===n.id&&pending.port===p.name?' pending':''));
    b.id=n.id+'-'+dir+'-'+p.name;b.title=p.type+' '+(dir==='in'?'input':'output');
    b.onclick=()=>{
     if(dir==='out'){pending={id:n.id,port:p.name,type:p.type};status('Choose a '+p.type+' input · Esc to cancel');render();return;}
     if(!pending){status('Select an output first.');return;}
     if(pending.type!==p.type){status('Incompatible ports: '+pending.type+' → '+p.type);return;}
     const edge={from:pending.id,out:pending.port,to:n.id,in:p.name};
     if(!graph.edges.some(e=>JSON.stringify(e)===JSON.stringify(edge)))graph.edges.push(edge);
     pending=null;render();inspect();invalidate();status('Connected');
    };col.append(b);
   }ports.append(col);
  }card.append(ports);$('#nodes').append(card);
 }drawWires();
}
function field(parent,label,value,onchange,type='text'){
 const l=el('label',label),input=el(type==='textarea'?'textarea':'input');
 if(type!=='textarea')input.type=type;if(type==='number')input.step='any';input.value=value;input.oninput=()=>{try{onchange(type==='number'?Number(input.value):input.value);input.setCustomValidity('');invalidate();render();}catch(e){input.setCustomValidity(e.message);status(e.message);}};l.append(input);parent.append(l);
}
function inspect(){
 const box=$('#inspector');box.replaceChildren();const n=graph.nodes.find(n=>n.id===selected);
 if(!n){box.append(el('h2','Select a block'),el('p','Select a block to edit its properties.','muted'));return;}
 box.append(el('h2',descriptions[n.kind][1]));
 field(box,'Label',n.label,v=>n.label=v);
 if(n.kind==='component'){
  field(box,'MOOSE category',n.category||'',v=>n.category=v);
  field(box,'MOOSE object type (optional)',n.object_type||'',v=>n.object_type=v);
  field(box,'Object parameters (JSON)',JSON.stringify(n.params,null,2),v=>{const p=JSON.parse(v);if(!p||Array.isArray(p)||typeof p!=='object')throw Error('Parameters must be a JSON object.');n.params=p;},'textarea');
 }
 else if(n.kind==='output')field(box,'Output settings (JSON, e.g. {"time_step_interval": 2})',JSON.stringify(n.params,null,2),v=>{const p=JSON.parse(v);if(!p||Array.isArray(p)||typeof p!=='object')throw Error('Settings must be a JSON object.');n.params=p;},'textarea');
 else for(const [k,v] of Object.entries(n.params))if(k!=='visualize')field(box,k,v,v=>n.params[k]=v,typeof v==='number'?'number':'text');
 if(n.kind==='solver'){
  // VIBORA setting, not a MOOSE parameter: these quantities are written to Exodus and shown as result images.
  field(box,'Visualize (space-separated, e.g. cauchy_stress_xx temperature)',n.params.visualize||'',v=>{if(v.trim())n.params.visualize=v.trim();else delete n.params.visualize;});
  box.append(el('p','Variables, aux variables, stress components or material properties to show after a run. Changing only this or the Results block edits the existing input instead of regenerating the model.','muted'));
 }
 for(const direction of ['inputs','outputs']){
  const ports=n[direction]||spec(n.kind)[direction];
  field(box,direction+' (name:type, …)',ports.map(p=>p.name+':'+p.type).join(', '),value=>{
   const parsed=value.trim()?value.split(',').map(item=>{const [name,type]=item.trim().split(':');if(!name||!type||!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)||!/^[A-Za-z_][A-Za-z0-9_]*$/.test(type))throw Error('Use port:type identifiers.');return {name,type};}):[];
   n[direction]=parsed;
  });
 }
 field(box,'Physics',n.physics||'',v=>n.physics=v,'textarea');
 field(box,'Numerical method',n.method||'',v=>n.method=v,'textarea');
 field(box,'Implementation requirements',n.implementation||'',v=>n.implementation=v,'textarea');
 const note=el('p','Descriptions drive a MOOSE-aware coding agent. Specify the physics and numerical requirements; the agent checks registered objects and asks before implementing custom C++.','muted');box.append(note);
 const connections=el('div',undefined,'connections');connections.append(el('b','Connections · click to remove'));
 for(const e of graph.edges.filter(e=>e.from===n.id||e.to===n.id)){
  const a=graph.nodes.find(n=>n.id===e.from),b=graph.nodes.find(n=>n.id===e.to),btn=el('button',(a?.label||e.from)+' → '+(b?.label||e.to)+' ×');
  btn.onclick=()=>{graph.edges=graph.edges.filter(x=>x!==e);render();inspect();invalidate();};connections.append(btn);
 }box.append(connections);
 const del=el('button','Delete block','danger');del.onclick=()=>{graph.nodes=graph.nodes.filter(x=>x.id!==n.id);graph.edges=graph.edges.filter(e=>e.from!==n.id&&e.to!==n.id);selected=null;render();inspect();invalidate();};box.append(del);
}
let requestId=0;
async function check(generate=false,quiet=false){
 if(generate&&generationPending)return;
 if(!generate&&generationPending)return;
 const rid=++requestId,snapshot=JSON.stringify(graph);
 if(generate){clearTimeout(timer);generationPending=true;$('#generate').disabled=true;status('Coding agent is implementing block descriptions…');}

 try{
  const response=await fetch((generate?'/api/generate':'/api/graph/check'),{method:'POST',headers:{'Content-Type':'application/json'},body:snapshot});
  const data=await response.json();if(rid!==requestId||snapshot!==JSON.stringify(graph)){status('Assembly changed during generation. Generate again to use current descriptions.');return;}
  $('#issues').replaceChildren();
  if(data.valid)$('#issues').append(el('div','✓ Graph connections are consistent. Generate to implement descriptions.','issue success'));
  else for(const i of data.issues||[])$('#issues').append(el('div',(graph.nodes.find(n=>n.id===i.node)?.label?graph.nodes.find(n=>n.id===i.node).label+': ':'')+i.message,'issue'));
  status(data.valid?'Graph valid · ready to generate':'Check found '+data.issues.length+' issue(s)');
  if(generate&&data.valid){
   generated=data.input;resolvedGraph=data.resolvedGraph;
   $('#input-preview').textContent=generated;
   $('#agent-summary').textContent=data.summary||'';
   $('#agent-changes').replaceChildren();
   for(const c of data.changes||[]){
    const label=graph.nodes.find(n=>n.id===c.node)?.label||c.node;
    $('#agent-changes').append(el('li',label+' · '+c.key+': '+JSON.stringify(c.before)+' → '+JSON.stringify(c.after)+'. '+c.reason));
   }
   $('#preview').showModal();
  }
 }catch(e){status('Backend unavailable. Start the C++ server and reconnect.');if(!quiet)$('#issues').replaceChildren(el('p','Cannot reach the C++ backend.','issue'));}
 finally{if(generate){generationPending=false;$('#generate').disabled=false;}}
}
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#validate').onclick=()=>check();$('#generate').onclick=()=>check(true);
$('#save').onclick=()=>download('vibora.json',JSON.stringify(graph,null,2),'application/json');
$('#load').onclick=()=>$('#file').click();
// Shared by Open and Import input: validates a graph, normalizes block fields and shows it.
function loadGraph(g,title){
  if(!g||!Array.isArray(g.nodes)||!Array.isArray(g.edges)||g.nodes.length>500||g.edges.length>2000)throw Error('Invalid graph structure.');
  const ids=new Set();
  for(const n of g.nodes){
   if(!n||typeof n.id!=='string'||!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(n.id)||ids.has(n.id)||!spec(n.kind)||!n.params||typeof n.params!=='object'||Array.isArray(n.params))throw Error('Invalid or duplicate block.');
   ids.add(n.id);if(typeof n.label!=='string')n.label=descriptions[n.kind][1];
   for(const key of ['physics','method','implementation'])if(typeof n[key]!=='string')n[key]='';
   n.x=Number.isFinite(n.x)?Math.max(5,n.x):50;n.y=Number.isFinite(n.y)?Math.max(5,n.y):50;
  }
  for(const edge of g.edges)if(!edge||!['from','out','to','in'].every(k=>typeof edge[k]==='string'))throw Error('Invalid connection.');
  graph=g;selected=null;pending=null;$('#model-title').textContent=title;render();inspect();invalidate();zoomToFit(true);
}
$('#file').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 try{if(file.size>1024*1024)throw Error('Graph exceeds 1 MB.');loadGraph(JSON.parse(await file.text()),file.name);}
 catch(err){status('Open failed: '+err.message);}finally{e.target.value='';}
};
$('#import-input').onclick=()=>{if(!graph.nodes.length||confirm('Replace the current graph with one built from a MOOSE input file? Save first to keep your edits.'))$('#input-file').click();};
$('#input-file').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 try{
  if(file.size>500*1024)throw Error('Input file exceeds 500 kB.');
  status('Importing '+file.name+'…');
  const r=await fetch('/api/graph/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:file.name,text:await file.text()})});
  const g=await r.json();if(!r.ok)throw Error(g.error||'Import failed');
  loadGraph(g,file.name);
  status('Imported '+file.name+': '+g.nodes.length+' blocks, '+g.edges.length+' connections. Implement & generate checks this input without calling the model until you change the graph.');
 }catch(err){status('Import failed: '+err.message);}finally{e.target.value='';}
};
$('#custom').onclick=()=>$('#creator').showModal();
$('#create').onclick=e=>{
 if(!$('#new-label').value.trim()){e.preventDefault();$('#new-label').focus();return;}
 add($('#new-kind').value,$('#new-label').value.trim(),{category:$('#new-category').value.trim(),object_type:$('#new-object-type').value.trim(),physics:$('#new-physics').value,method:$('#new-method').value});
};
$('#close-preview').onclick=()=>$('#preview').close();$('#download').onclick=()=>download('model.i',generated,'text/plain');
$('#apply-resolved').onclick=()=>{if(!resolvedGraph)return;graph=clone(resolvedGraph);render();inspect();try{localStorage.setItem('vibora-draft',JSON.stringify(graph));}catch(e){}status('Implemented settings applied to blocks.');};
$('#save-resolved').onclick=()=>download('vibora-resolved.json',JSON.stringify(resolvedGraph,null,2),'application/json');
document.addEventListener('keydown',e=>{if(e.key==='Escape'){pending=null;render();status('Ready');}});
window.addEventListener('resize',drawWires);
async function start(){
 try{
  const res=await fetch('/api/catalog');if(!res.ok)throw Error();catalog=await res.json();
  // General building blocks only; any MOOSE object is added as a component with its category.
  for(const kind of ['component','mesh','solver','output']){
   const [symbol,title,desc]=descriptions[kind],b=el('button',undefined,'library-item'),label=el('div',title);label.append(el('small',desc));b.append(el('span',symbol,'symbol'),label);b.onclick=()=>add(kind);$('#catalog').append(b);
   const option=el('option',title);option.value=kind;$('#new-kind').append(option);
  }
  for(const category of mooseCategories){const option=el('option');option.value=category;$('#moose-categories').append(option);}
  for(const category of ['Variables','Materials','ICs','BCs','Kernels','AuxVariables','AuxKernels','Postprocessors']){const b=el('button','＋ '+category,'library-item');b.onclick=()=>add('component',category,{category});$('#catalog').append(b);}
  const draft=localStorage.getItem('vibora-draft');
  if(draft){try{const g=JSON.parse(draft);if(!Array.isArray(g.nodes)||!Array.isArray(g.edges)||g.nodes.some(n=>!spec(n.kind)))throw Error();graph=g;render();inspect();scheduleCheck();}catch(e){render();}}else render();
 }catch(e){status('Cannot load block catalog. Start the C++ backend.');}
}
start();

$('#zoom-in').onclick=()=>setZoom(zoom*1.25);
$('#zoom-out').onclick=()=>setZoom(zoom/1.25);
$('#zoom-reset').onclick=()=>setZoom(1);
$('#zoom-fit').onclick=()=>zoomToFit(false);
// Ctrl/Cmd + wheel, and trackpad pinch (reported as a ctrl wheel), zoom around the pointer; a plain wheel still scrolls.
$('#viewport').addEventListener('wheel',e=>{
 if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();
 const r=$('#viewport').getBoundingClientRect();setZoom(zoom*Math.exp(-e.deltaY*0.0015),e.clientX-r.left,e.clientY-r.top);
},{passive:false});
