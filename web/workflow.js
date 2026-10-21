'use strict';
let modelChoices=[], selectedModel={provider:'codex',id:'default'}, currentJob=null, jobSnapshot=null, pollTimer=null;
try{selectedModel=JSON.parse(localStorage.getItem('vibora-model'))||selectedModel;}catch(e){}
async function api(path,data){
 const r=await fetch('/api/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const text=await r.text();let result;
 try{result=JSON.parse(text);}catch(e){throw Error('Server returned HTTP '+r.status+(text?': '+text.slice(0,300):' with an empty response'));}
 if(!r.ok)throw Error(result.error||'Request failed (HTTP '+r.status+')');return result;
}
function modelLabel(){return selectedModel.provider+' / '+selectedModel.id;}
function setBusy(busy){generationPending=busy;$('#generate').disabled=busy;}
async function refreshModels(){
 $('#model-availability').textContent='Connecting to providers…';
 try{
  const data=await api('models');modelChoices=data.models;$('#model-select').replaceChildren();
  modelChoices.forEach((m,i)=>{const option=el('option',m.name);option.value=String(i);option.selected=m.provider===selectedModel.provider&&m.id===selectedModel.id;$('#model-select').append(option);});
  $('#model-availability').textContent=Object.entries(data.providers).map(([k,v])=>k+': '+v).join(' · ');
 }catch(e){$('#model-availability').textContent=e.message;}
}
$('#models').onclick=()=>{$('#models-dialog').showModal();refreshModels();};
$('#refresh-models').onclick=refreshModels;
$('#close-models').onclick=()=>$('#models-dialog').close();
$('#choose-model').onclick=()=>{
 const choice=modelChoices[Number($('#model-select').value)];if(!choice)return;
 selectedModel={provider:choice.provider,id:choice.id};localStorage.setItem('vibora-model',JSON.stringify(selectedModel));
 $('#models').textContent='LLM: '+choice.id;$('#models-dialog').close();status('Selected '+modelLabel());
};
$('#model-request').oninput=()=>{graph.request=$('#model-request').value;invalidate();};
$('#new-model').onclick=()=>{
 if(graph.nodes.length&&!confirm('Start a new model? Save the current graph first to keep a portable copy.'))return;
 graph={version:2,title:'New MOOSE model',request:'',nodes:[node('component',100,100,'Model physics')],edges:[]};
 selected=graph.nodes[0].id;pending=null;render();inspect();invalidate();
};
function showJob(job){
 currentJob=job;$('#job-status').hidden=false;
 $('#job-title').textContent=job.status.replaceAll('_',' ');
 $('#job-model').textContent=(job.model?.provider||'')+' / '+(job.model?.id||'');
 $('#job-summary').textContent=job.summary||job.error||'';
 $('#job-questions').replaceChildren();
 for(const q of job.questions||[])$('#job-questions').append(el('p',q,'issue'));
 $('#custom-approval').hidden=job.status!=='awaiting_approval';
 $('#custom-rationale').textContent=job.rationale||'';
 $('#approve-custom').disabled=jobSnapshot!==JSON.stringify(graph);
 if(job.status==='awaiting_approval'&&$('#approve-custom').disabled)$('#job-questions').append(el('p','The graph changed. Generate a new proposal before approving custom code.','issue'));
 $('#view-generated').hidden=job.status!=='ready';
 const details={};
 if(job.scheduler_id)details.scheduler_job=job.scheduler_id;
 if(job.files)details.source_files=job.files;
 if(job.verification)details.verification=job.verification;
 if(job.validation)details.moose_validation=job.validation;
 if(job.test_result)details.build_and_tests=job.test_result;
 if(job.retained)details.retained_capability=job.retained;
 if(job.error)details.error=job.error;
 $('#job-details').textContent=Object.keys(details).length?JSON.stringify(details,null,2):'';
 const terminal=['ready','failed','needs_clarification','awaiting_approval','cancelled'].includes(job.status);
 setBusy(!terminal);status(job.status+': '+(job.summary||job.error||''));
 if(terminal)clearTimeout(pollTimer);else pollTimer=setTimeout(pollJob,2000);
}
async function pollJob(){
 if(!currentJob)return;
 try{showJob(await api('jobs/status',{id:currentJob.id}));}
 catch(e){setBusy(false);$('#job-summary').textContent='Connection interrupted: '+e.message;status(e.message);}
}
$('#generate').onclick=async()=>{
 if(generationPending)return;
 clearTimeout(timer);generated='';resolvedGraph=null;setBusy(true);jobSnapshot=JSON.stringify(graph);
 $('#job-dialog').showModal();$('#job-title').textContent='Starting';$('#job-summary').textContent='Creating a MOOSE implementation job…';
 $('#job-questions').replaceChildren();$('#job-details').textContent='';$('#custom-approval').hidden=true;$('#view-generated').hidden=true;
 try{
  const job=await api('jobs/start',{graph:clone(graph),model:selectedModel});
  localStorage.setItem('vibora-job',JSON.stringify({id:job.id,snapshot:jobSnapshot}));showJob(job);
 }catch(e){setBusy(false);$('#job-summary').textContent=e.message;status(e.message);}
};
$('#approve-custom').onclick=async()=>{
 if(!currentJob||currentJob.status!=='awaiting_approval')return;
 if(jobSnapshot!==JSON.stringify(graph)){status('Graph changed. Generate a new proposal.');return;}
 $('#approve-custom').disabled=true;
 try{showJob(await api('jobs/approve',{id:currentJob.id,plan_hash:currentJob.plan_hash,graph_hash:currentJob.graph_hash}));}
 catch(e){$('#job-summary').textContent=e.message;$('#approve-custom').disabled=false;}
};
$('#decline-custom').onclick=async()=>{try{showJob(await api('jobs/reject',{id:currentJob.id}));}catch(e){status(e.message);}};
$('#close-job').onclick=()=>$('#job-dialog').close();
$('#job-status').onclick=()=>{$('#job-dialog').showModal();pollJob();};
$('#view-generated').onclick=()=>{
 if(!currentJob?.input)return;
 generated=currentJob.input;$('#input-preview').textContent=generated;$('#agent-summary').textContent=currentJob.summary;
 $('#agent-changes').replaceChildren(el('li',currentJob.verification||''));
 if(currentJob.retained)$('#agent-changes').append(el('li','Retained capability: '+currentJob.retained.capability+(currentJob.retained.sync_pending?' · GitHub synchronization pending.':'')));
 $('#apply-resolved').hidden=true;$('#save-resolved').hidden=true;
 $('#job-dialog').close();$('#preview').showModal();
};
try{
 const saved=JSON.parse(localStorage.getItem('vibora-job'));
 if(saved){jobSnapshot=saved.snapshot;currentJob={id:saved.id};$('#job-status').hidden=false;pollTimer=setTimeout(pollJob,1500);}
}catch(e){}
