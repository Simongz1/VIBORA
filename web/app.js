'use strict';
const $=s=>document.querySelector(s);
const descriptions={mesh:['▦','Mesh','GeneratedMesh'],variable:['φ','Scalar field','Lagrange · first order'],diffusion:['∇','Diffusion','MOOSE Diffusion'],boundary:['⊣','Boundary condition','DirichletBC'],solver:['ƒ','Solver','Steady / Transient'],output:['↗','Results','Exodus output']};
let catalog=[], graph={version:1,nodes:[],edges:[]}, selected=null, pending=null, generated='', drag=null, resolvedGraph=null, generationPending=false;
const clone=x=>JSON.parse(JSON.stringify(x));
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
function status(t){$('#status').textContent=t;}
function invalidate(){generated='';resolvedGraph=null;try{localStorage.setItem('vibora-draft',JSON.stringify(graph));}catch(e){}$('#issues').replaceChildren(el('p','Assembly changed. Check dependencies again.','muted'));scheduleCheck();}
let timer;
function scheduleCheck(){clearTimeout(timer);timer=setTimeout(()=>check(false,true),650);}
function spec(k){return catalog.find(x=>x.kind===k);}
function node(kind,x=80,y=60,label){return {id:'b_'+crypto.randomUUID().replaceAll('-',''),kind,label:label||descriptions[kind][1],params:clone(spec(kind).params),physics:'',method:'',implementation:'',x,y};}
function add(kind,label){const n=node(kind,60+graph.nodes.length%4*215,80+Math.floor(graph.nodes.length/4)*200,label);graph.nodes.push(n);selected=n.id;render();inspect();invalidate();}
function drawWires(){
 const svg=$('#wires');svg.replaceChildren();
 for(const e of graph.edges){
  const a=document.getElementById(e.from+'-out-'+e.out),b=document.getElementById(e.to+'-in-'+e.in);if(!a||!b)continue;
  const canvas=$('#canvas').getBoundingClientRect(),ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
  const x1=ar.right-canvas.left-5,y1=ar.top-canvas.top+ar.height/2,x2=br.left-canvas.left+5,y2=br.top-canvas.top+br.height/2;
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d','M '+x1+' '+y1+' C '+(x1+65)+' '+y1+', '+(x2-65)+' '+y2+', '+x2+' '+y2);
  const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent='Click to remove connection';path.append(title);
  path.onclick=()=>{graph.edges=graph.edges.filter(x=>x!==e);render();inspect();invalidate();};svg.append(path);
 }
}
function render(){
 const solver=graph.nodes.find(n=>n.kind==='solver');$('#model-title').textContent=(solver?.params.type||'Steady')+' diffusion / unit domain';
 $('#nodes').replaceChildren();$('#counts').textContent=graph.nodes.length+' blocks · '+graph.edges.length+' connections';
 for(const n of graph.nodes){
  const card=el('section',undefined,'node'+(selected===n.id?' selected':''));card.id=n.id;card.style.left=n.x+'px';card.style.top=n.y+'px';
  const head=el('div',undefined,'node-head');head.append(el('b',n.label),el('small',n.kind==='solver'?(n.params.type||'Steady')+' · '+(n.params.solve_type||'PJFNK'):descriptions[n.kind][2]));card.append(head);
  head.onpointerdown=e=>{if(e.button!==0)return;selected=n.id;inspect();document.querySelectorAll('.node').forEach(c=>c.classList.toggle('selected',c.id===n.id));drag={n,x:e.clientX,y:e.clientY,ox:n.x,oy:n.y};head.setPointerCapture(e.pointerId);};
  head.onpointermove=e=>{if(!drag||drag.n!==n)return;n.x=Math.max(5,Math.min(1300,drag.ox+e.clientX-drag.x));n.y=Math.max(5,Math.min(850,drag.oy+e.clientY-drag.y));card.style.left=n.x+'px';card.style.top=n.y+'px';drawWires();};
  head.onpointerup=()=>{drag=null;};
  head.onpointercancel=()=>{drag=null;};
  const ports=el('div',undefined,'ports');
  for(const dir of ['in','out']){
   const col=el('div');
   for(const p of spec(n.kind)[dir==='in'?'inputs':'outputs']){
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
 if(type!=='textarea')input.type=type;if(type==='number')input.step='any';input.value=value;input.oninput=()=>{onchange(type==='number'?Number(input.value):input.value);invalidate();render();};l.append(input);parent.append(l);
}
function inspect(){
 const box=$('#inspector');box.replaceChildren();const n=graph.nodes.find(n=>n.id===selected);
 if(!n){box.append(el('h2','Select a block'),el('p','Select a block to edit its properties.','muted'));return;}
 box.append(el('h2',descriptions[n.kind][1]));
 field(box,'Label',n.label,v=>n.label=v);
 for(const [k,v] of Object.entries(n.params))field(box,k,v,v=>n.params[k]=v,typeof v==='number'?'number':'text');
 field(box,'Physics',n.physics||'',v=>n.physics=v,'textarea');
 field(box,'Numerical method',n.method||'',v=>n.method=v,'textarea');
 field(box,'Implementation requirements',n.implementation||'',v=>n.implementation=v,'textarea');
 const note=el('p','Descriptions drive the coding agent. Example: Transient diffusion, dt = 0.1, end time = 2, backward Euler, initial u = 0. Generate to implement and review the changes.','muted');box.append(note);
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
  const response=await fetch('/api/'+(generate?'generate':'validate'),{method:'POST',headers:{'Content-Type':'application/json'},body:snapshot});
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
function example(){
 graph={version:1,nodes:[node('mesh',50,100),node('variable',290,100),node('diffusion',540,50),node('boundary',540,230,'Left · u = 0'),node('boundary',540,410,'Right · u = 1'),node('solver',800,150),node('output',1050,150)],edges:[]};
 graph.nodes[4].params={boundary:'right',value:1};
 const link=(a,out,b,input)=>graph.edges.push({from:graph.nodes[a].id,out,to:graph.nodes[b].id,in:input});
 link(0,'mesh',1,'mesh');link(1,'field',2,'field');link(1,'field',3,'field');link(1,'field',4,'field');
 link(2,'operator',5,'operator');link(3,'constraint',5,'constraint');link(4,'constraint',5,'constraint');link(5,'solution',6,'solution');
 selected=null;pending=null;$('#model-title').textContent='Steady diffusion / unit square';render();inspect();invalidate();
}
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#validate').onclick=()=>check();$('#generate').onclick=()=>check(true);
$('#save').onclick=()=>download('vibora.json',JSON.stringify(graph,null,2),'application/json');
$('#load').onclick=()=>$('#file').click();
$('#file').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 try{
  if(file.size>1024*1024)throw Error('Graph exceeds 1 MB.');
  const g=JSON.parse(await file.text());
  if(!g||!Array.isArray(g.nodes)||!Array.isArray(g.edges)||g.nodes.length>500||g.edges.length>2000)throw Error('Invalid graph structure.');
  const ids=new Set();
  for(const n of g.nodes){
   if(!n||typeof n.id!=='string'||!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(n.id)||ids.has(n.id)||!spec(n.kind)||!n.params||typeof n.params!=='object'||Array.isArray(n.params))throw Error('Invalid or duplicate block.');
   ids.add(n.id);if(typeof n.label!=='string')n.label=descriptions[n.kind][1];
   for(const key of ['physics','method','implementation'])if(typeof n[key]!=='string')n[key]='';
   n.x=Number.isFinite(n.x)?Math.max(5,Math.min(1300,n.x)):50;n.y=Number.isFinite(n.y)?Math.max(5,Math.min(850,n.y)):50;
  }
  for(const edge of g.edges)if(!edge||!['from','out','to','in'].every(k=>typeof edge[k]==='string'))throw Error('Invalid connection.');
  graph=g;selected=null;pending=null;$('#model-title').textContent=file.name;render();inspect();invalidate();
 }catch(err){status('Open failed: '+err.message);}finally{e.target.value='';}
};
$('#example').onclick=()=>{if(!graph.nodes.length||confirm('Replace the current graph with the diffusion example? Save first to keep your edits.'))example();};
$('#custom').onclick=()=>$('#creator').showModal();
$('#create').onclick=e=>{
 if(!$('#new-label').value.trim()){e.preventDefault();$('#new-label').focus();return;}
 add($('#new-kind').value,$('#new-label').value.trim());const n=graph.nodes.find(n=>n.id===selected);n.physics=$('#new-physics').value;n.method=$('#new-method').value;inspect();
};
$('#close-preview').onclick=()=>$('#preview').close();$('#download').onclick=()=>download('diffusion.i',generated,'text/plain');
$('#apply-resolved').onclick=()=>{if(!resolvedGraph)return;graph=clone(resolvedGraph);render();inspect();try{localStorage.setItem('vibora-draft',JSON.stringify(graph));}catch(e){}status('Implemented settings applied to blocks.');};
$('#save-resolved').onclick=()=>download('vibora-resolved.json',JSON.stringify(resolvedGraph,null,2),'application/json');
document.addEventListener('keydown',e=>{if(e.key==='Escape'){pending=null;render();status('Ready');}});
window.addEventListener('resize',drawWires);
async function start(){
 try{
  const res=await fetch('/api/catalog');if(!res.ok)throw Error();catalog=await res.json();
  for(const kind of ['mesh','variable','diffusion','boundary','solver','output']){
   const [symbol,title,desc]=descriptions[kind],b=el('button',undefined,'library-item'),label=el('div',title);label.append(el('small',desc));b.append(el('span',symbol,'symbol'),label);b.onclick=()=>add(kind);$('#catalog').append(b);
   const option=el('option',title);option.value=kind;$('#new-kind').append(option);
  }
  const draft=localStorage.getItem('vibora-draft');
  if(draft){try{const g=JSON.parse(draft);if(!Array.isArray(g.nodes)||!Array.isArray(g.edges)||g.nodes.some(n=>!spec(n.kind)))throw Error();graph=g;render();inspect();scheduleCheck();}catch(e){example();}}else example();
 }catch(e){status('Cannot load block catalog. Start the C++ backend.');}
}
start();
