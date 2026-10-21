'use strict';
let modelChoices=[], selectedModel={provider:'codex',id:'default'}, currentJob=null, jobSnapshot=null, pollTimer=null;
try{selectedModel=JSON.parse(localStorage.getItem('vibora-model'))||selectedModel;}catch(e){}
async function api(path,data){
 // The server answers every job call quickly; a missing reply means the bridge or SSH tunnel is stuck.
 const controller=new AbortController(),limit=setTimeout(()=>controller.abort(),60000);let r;
 try{r=await fetch('/api/'+path,Object.assign({signal:controller.signal},data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}));}
 catch(e){throw Error(e.name==='AbortError'?'No reply from the VIBORA server after 60 s. Check the bridge terminal, then try again.':'Cannot reach the VIBORA server ('+e.message+'). Is the bridge running?');}
 finally{clearTimeout(limit);}
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
const RUN_ACTIVE=['submitting','queued','running'];
function renderLog(entries,active){
 const list=$('#job-log'),follow=list.scrollTop+list.clientHeight>=list.scrollHeight-8;
 list.replaceChildren(...entries.map(e=>{const li=el('li',e.message);li.dataset.time=new Date(e.t*1000).toLocaleTimeString();return li;}));
 const last=entries[entries.length-1];
 if(active&&last){const waited=Math.round(Date.now()/1000-last.t);if(waited>=5)list.append(el('li','Still working — '+waited+' s since the last step.','waiting'));}
 if(follow)list.scrollTop=list.scrollHeight;
}
function runText(run){
 if(!run.status)return '';
 const id=run.scheduler_id?' (Slurm job '+run.scheduler_id+')':'';
 if(run.status==='submitting')return 'Submitting to Slurm…';
 if(run.status==='queued')return 'Waiting for a compute node'+id+(run.reason?': '+run.reason:'')+'.';
 const where=run.mode==='login'?'login node ':'';
 if(run.status==='running')return 'Running on '+where+(run.node||'a compute node')+id+'.';
 if(run.status==='complete')return 'Finished on '+where+(run.node||'the compute node')+id+'.';
 if(run.status==='cancelled')return 'Cancelled'+id+'.';
 return 'Failed'+id+': '+(run.error||'MOOSE exited with code '+run.returncode)+'.';
}
function showRun(job){
 const run=job.run||{},active=RUN_ACTIVE.includes(run.status);
 $('#run-panel').hidden=job.status!=='ready';
 $('#start-run').disabled=active;$('#run-where').disabled=active;updateRunWhere(run.status&&!active);
 $('#cancel-run').hidden=!['queued','running'].includes(run.status);
 $('#run-status').textContent=runText(run);
 const details={};
 if(run.folder)details.results_folder_on_gilbreth=run.folder;
 if(run.postprocessors&&Object.keys(run.postprocessors).length)details['final_values ('+run.csv+', '+run.csv_rows+' rows)']=run.postprocessors;
 if(run.outputs?.length)details.output_files=run.outputs.map(f=>f.name+' ('+Math.max(1,Math.round(f.size/1024))+' kB)');
 if(run.scheduler_log)details.scheduler_log=run.scheduler_log;
 let text=Object.keys(details).length?JSON.stringify(details,null,2):'';
 if(run.log_tail&&!active)text+=(text?'\n\n':'')+'MOOSE log (end):\n'+run.log_tail;
 $('#run-details').hidden=!text;$('#run-details').textContent=text;
 return active;
}
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
 $('#job-details').textContent=Object.keys(details).length?JSON.stringify(details,null,2):'';$('#job-details').hidden=!Object.keys(details).length;
 const terminal=['ready','failed','needs_clarification','awaiting_approval','cancelled'].includes(job.status);
 const running=showRun(job);renderLog(job.log||[],!terminal||running);
 setBusy(!terminal);status(running?'Simulation: '+runText(job.run):job.status+': '+(job.summary||job.error||''));
 clearTimeout(pollTimer);if(!terminal||running)pollTimer=setTimeout(pollJob,2000);
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
 const started=Date.now(),tick=setInterval(()=>{$('#job-summary').textContent='Creating a MOOSE implementation job… '+Math.round((Date.now()-started)/1000)+' s';},1000);
 $('#job-questions').replaceChildren();$('#job-details').textContent='';$('#custom-approval').hidden=true;$('#view-generated').hidden=true;
 $('#job-log').replaceChildren();$('#run-panel').hidden=true;
 try{
  const job=await api('jobs/start',{graph:clone(graph),model:selectedModel});clearInterval(tick);
  localStorage.setItem('vibora-job',JSON.stringify({id:job.id,snapshot:jobSnapshot}));showJob(job);
 }catch(e){clearInterval(tick);setBusy(false);$('#job-title').textContent='Could not start';$('#job-summary').textContent=e.message;status(e.message);}
};
$('#approve-custom').onclick=async()=>{
 if(!currentJob||currentJob.status!=='awaiting_approval')return;
 if(jobSnapshot!==JSON.stringify(graph)){status('Graph changed. Generate a new proposal.');return;}
 $('#approve-custom').disabled=true;
 try{showJob(await api('jobs/approve',{id:currentJob.id,plan_hash:currentJob.plan_hash,graph_hash:currentJob.graph_hash}));}
 catch(e){$('#job-summary').textContent=e.message;$('#approve-custom').disabled=false;}
};
$('#decline-custom').onclick=async()=>{try{showJob(await api('jobs/reject',{id:currentJob.id}));}catch(e){status(e.message);}};
function updateRunWhere(again){
 const login=$('#run-where').value==='login';
 $('#run-ranks').max=login?4:128;$('#run-ranks').placeholder=login?'1 (max 4)':'Default';$('#run-time').placeholder=login?'00:10:00 (max 01:00:00)':'HH:MM:SS';
 if(again!==undefined)$('#start-run').dataset.again=again?'1':'';
 $('#start-run').textContent=($('#start-run').dataset.again?'Run again on ':'Run on ')+(login?'login node':'compute node');
}
$('#run-where').onchange=()=>updateRunWhere();
$('#start-run').onclick=async()=>{
 if(!currentJob||currentJob.status!=='ready')return;
 const where=$('#run-where').value,ranks=Number($('#run-ranks').value)||0;
 if(where==='login'&&ranks>4){$('#run-status').textContent='Login-node runs are limited to 4 MPI ranks.';return;}
 $('#start-run').disabled=true;$('#run-status').textContent=where==='login'?'Starting on the login node…':'Submitting to Slurm…';
 try{showJob(await api('jobs/run',{id:currentJob.id,where,ranks,time:$('#run-time').value.trim()}));}
 catch(e){$('#run-status').textContent=e.message;$('#start-run').disabled=false;}
};
$('#cancel-run').onclick=async()=>{
 if(!currentJob||!confirm('Cancel this simulation? Partial output stays in the run folder.'))return;
 try{showJob(await api('jobs/cancel_run',{id:currentJob.id}));}catch(e){$('#run-status').textContent=e.message;}
};
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
