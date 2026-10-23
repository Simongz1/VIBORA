import copy,importlib.util,json,os,subprocess,tempfile,time,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
engine=load('workflow','scripts/workflow_engine.py')
workspace=load('workspace','scripts/moose_workspace.py')
def graph():return {'nodes':[{'id':'physics','kind':'component','physics':'thermoelasticity','params':{}}],'edges':[]}
class FakeEngine(engine.Engine):
 def __init__(self):
  super().__init__(types.SimpleNamespace(ssh_host='test',remote_dir='/test',codex='codex'))
  self.saved={};self.operations=[];self.launched=[]
 def rpc(self,payload,timeout=220):
  self.operations.append(payload['op'])
  if payload['op']=='save_job':self.saved[payload['id']]=copy.deepcopy(payload['state']);return {}
  if payload['op']=='load_job':return copy.deepcopy(self.saved[payload['id']])
  return {}
 def launch(self,j,fn):self.launched.append(fn.__name__)
 def models(self):return {'models':[{'provider':'local','id':'test-model'}]}
class WorkflowTests(unittest.TestCase):
 def test_general_graph_has_no_diffusion_cardinality(self):self.assertEqual(engine.graph_errors(graph()),[])
 def test_coupled_cycles_are_allowed(self):
  g=graph();g['nodes'].append({'id':'other','params':{}})
  g['edges']=[{'from':'physics','to':'other'},{'from':'other','to':'physics'}]
  self.assertEqual(engine.graph_errors(g),[])
 def test_duplicate_and_dangling_graphs_rejected(self):
  g=graph();g['nodes']*=2;self.assertTrue(engine.graph_errors(g))
  g=graph();g['edges']=[{'from':'physics','to':'absent'}];self.assertTrue(engine.graph_errors(g))
 def test_selected_model_persisted(self):
  e=FakeEngine();j=e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'}})
  self.assertEqual(j['model']['id'],'test-model');self.assertEqual(e.launched,['plan'])
 def test_start_returns_without_waiting_on_the_moose_host(self):
  e=FakeEngine();j=e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'}})
  self.assertEqual(e.operations,[]);self.assertEqual(j['log'][0]['message'][:11],'Job created')
 def test_model_list_cached_and_refreshed_for_new_models(self):
  e=FakeEngine();calls=[]
  models=[[{'provider':'local','id':'a'}],[{'provider':'local','id':'a'},{'provider':'claude-code','id':'opus'}]]
  e.models=lambda:calls.append(1) or {'models':models[min(len(calls)-1,1)]}
  e.start({'graph':graph(),'model':{'provider':'local','id':'a'}});e.start({'graph':graph(),'model':{'provider':'local','id':'a'}})
  self.assertEqual(len(calls),1)
  e.start({'graph':graph(),'model':{'provider':'claude-code','id':'opus'}});self.assertEqual(len(calls),2)
 def test_unavailable_model_rejected(self):
  with self.assertRaises(ValueError):FakeEngine().start({'graph':graph(),'model':{'provider':'local','id':'not-installed'}})
 def pending(self):
  e=FakeEngine();public=e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'}});j=e.jobs[public['id']]
  j.update(status='awaiting_approval',plan_hash='plan')
  return e,j
 def test_custom_not_started_before_approval(self):
  e,j=self.pending();self.assertNotIn('authorize',e.operations);self.assertNotIn('custom',e.launched)
 def test_matching_approval_starts_custom(self):
  e,j=self.pending();e.approve({'id':j['id'],'plan_hash':'plan','graph_hash':j['graph_hash']})
  self.assertIn('authorize',e.operations);self.assertEqual(j['status'],'coding');self.assertIn('custom',e.launched)
 def test_stale_plan_and_graph_approval_rejected(self):
  for plan,gh in [('wrong',None),('plan','changed')]:
   e,j=self.pending()
   with self.assertRaises(ValueError):e.approve({'id':j['id'],'plan_hash':plan,'graph_hash':gh or j['graph_hash']})
   self.assertNotIn('authorize',e.operations)
 def test_decline_never_starts_custom(self):
  e,j=self.pending();e.reject({'id':j['id']})
  self.assertEqual(j['status'],'cancelled');self.assertNotIn('custom',e.launched)
 def test_public_response_omits_internal_code_context(self):
  e,j=self.pending();j.update(context={'source':'x'},coding_prompt='y',package={'files':[]})
  response=e.public(j)
  for k in ('graph','context','coding_prompt','package'):self.assertNotIn(k,response)

class FakeClaudeSDK:
 class AnthropicError(Exception):pass
 class APIConnectionError(AnthropicError):pass
 class APIStatusError(AnthropicError):
  def __init__(self,message,status_code=500):super().__init__(message);self.message=message;self.status_code=status_code
 class AuthenticationError(APIStatusError):pass
 class RateLimitError(APIStatusError):pass
class FakeClaudeClient:
 def __init__(self,stop_reason='end_turn',text='{"objects":["Kernels/ADHeatConduction"],"questions":[]}',ids=()):
  self.requests=[];self.ids=ids;client=self
  class Stream:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def get_final_message(self):
    return types.SimpleNamespace(stop_reason=stop_reason,stop_details=None,content=[types.SimpleNamespace(type='text',text=text)])
  def stream(**kwargs):client.requests.append(kwargs);return Stream()
  self.beta=types.SimpleNamespace(messages=types.SimpleNamespace(stream=stream))
  self.models=types.SimpleNamespace(list=lambda **kwargs:[types.SimpleNamespace(id=i) for i in client.ids])
 def with_options(self,**kwargs):return self
class ClaudeProviderTests(unittest.TestCase):
 def use(self,client):
  original=engine.claude_client;engine.claude_client=lambda:(FakeClaudeSDK,client)
  self.addCleanup(setattr,engine,'claude_client',original)
  return FakeEngine()
 def test_structured_request_uses_schema_and_fallback(self):
  client=FakeClaudeClient();e=self.use(client)
  answer=e.llm({'provider':'anthropic','id':'claude-opus-5-5'},'plan this',engine.DISCOVERY)
  self.assertEqual(answer['objects'],['Kernels/ADHeatConduction'])
  request=client.requests[0]
  self.assertEqual(request['output_config']['format'],{'type':'json_schema','schema':engine.DISCOVERY})
  self.assertEqual(request['fallbacks'],'default');self.assertEqual(request['betas'],['server-side-fallback-2026-07-01'])
 def test_fallback_omitted_for_models_without_server_fallback(self):
  client=FakeClaudeClient();self.use(client).llm({'provider':'anthropic','id':'claude-haiku-5-5'},'p',engine.DISCOVERY)
  self.assertNotIn('fallbacks',client.requests[0]);self.assertNotIn('betas',client.requests[0])
 def test_refusal_and_truncation_fail_the_job_step(self):
  for reason in ('refusal','max_tokens'):
   with self.assertRaises(RuntimeError):
    self.use(FakeClaudeClient(stop_reason=reason)).llm({'provider':'anthropic','id':'claude-opus-5-5'},'p',engine.DISCOVERY)
 def test_only_advertised_supported_models_listed(self):
  e=self.use(FakeClaudeClient(ids=['claude-haiku-5-5','claude-opus-5-5','claude-3-haiku']))
  listed=[m['id'] for m in engine.Engine.models(e)['models'] if m['provider']=='anthropic']
  self.assertEqual(listed,['claude-opus-5-5','claude-haiku-5-5'])
 def test_missing_sdk_or_key_reported_as_provider_status(self):
  original=engine.claude_client
  def missing():raise RuntimeError('Set ANTHROPIC_API_KEY before starting the bridge')
  engine.claude_client=missing;self.addCleanup(setattr,engine,'claude_client',original)
  status=engine.Engine.models(FakeEngine())['providers']['anthropic']
  self.assertIn('ANTHROPIC_API_KEY',status)

class ClaudeCodeProviderTests(unittest.TestCase):
 def use(self,stdout,returncode=0):
  calls=[]
  def run(cmd,**kwargs):calls.append((cmd,kwargs));return types.SimpleNamespace(returncode=returncode,stdout=stdout(cmd) if callable(stdout) else stdout,stderr='')
  original=engine.subprocess.run;engine.subprocess.run=run;self.addCleanup(setattr,engine.subprocess,'run',original)
  e=FakeEngine();e.args.claude='/bin/claude';return e,calls
 def test_structured_output_returned_without_tools(self):
  e,calls=self.use(json.dumps({'is_error':False,'structured_output':{'objects':['Kernels/ADHeatConduction'],'questions':[]}}))
  answer=e.llm({'provider':'claude-code','id':'opus'},'plan this',engine.DISCOVERY)
  self.assertEqual(answer['objects'],['Kernels/ADHeatConduction'])
  cmd,kwargs=calls[0]
  self.assertEqual(json.loads(cmd[cmd.index('--json-schema')+1]),engine.DISCOVERY)
  self.assertEqual(cmd[cmd.index('--tools')+1],'');self.assertIn('--strict-mcp-config',cmd);self.assertEqual(kwargs['input'],'plan this')
 def test_usage_read_from_cli_json(self):
  e,calls=self.use(json.dumps({'is_error':False,'structured_output':{'objects':[],'questions':[]},
   'usage':{'input_tokens':120,'cache_creation_input_tokens':30,'cache_read_input_tokens':5000,'output_tokens':80}}))
  e.llm({'provider':'claude-code','id':'opus'},'p',engine.DISCOVERY)
  self.assertEqual(e.usage.value,{'input':5150,'cached':5000,'output':80})
 def test_cli_errors_fail_the_job_step(self):
  for stdout,code in [(json.dumps({'is_error':True,'result':'Not logged in · Please run /login'}),1),('not json',1)]:
   e,calls=self.use(stdout,code)
   with self.assertRaises(RuntimeError):e.llm({'provider':'claude-code','id':'opus'},'p',engine.DISCOVERY)
 def test_models_listed_only_when_signed_in(self):
  for signed_in in (True,False):
   e,calls=self.use(lambda cmd:json.dumps({'loggedIn':signed_in}) if cmd[1:3]==['auth','status'] else '')
   result=engine.Engine.models(e)
   listed=[m['id'] for m in result['models'] if m['provider']=='claude-code']
   self.assertEqual(listed,engine.CLAUDE_CODE_MODELS if signed_in else [])
   if not signed_in:self.assertIn('claude auth login',result['providers']['claude-code'])

class ActivityLogTests(unittest.TestCase):
 def test_model_calls_and_steps_are_logged(self):
  e=FakeEngine();j={'id':'a'*32,'model':{'provider':'local','id':'m'},'summary':''}
  e.llm=lambda *a:{'status':'builtin','objects':['Kernels/Diffusion'],'questions':[],'summary':'ok'}
  e.ask(j,'design the MOOSE input','prompt',engine.PLAN)
  e.update(j,summary='Checking the input.');e.update(j,summary='Checking the input.')
  messages=[x['message'] for x in j['log']]
  self.assertIn('local / m to design the MOOSE input',messages[0]);self.assertIn('Kernels/Diffusion',messages[1])
  self.assertEqual(messages.count('Checking the input.'),1)
 def test_failed_model_call_is_logged_and_raised(self):
  e=FakeEngine();j={'id':'a'*32,'model':{'provider':'local','id':'m'}}
  def fail(*a):raise RuntimeError('usage limit')
  e.llm=fail
  with self.assertRaises(RuntimeError):e.ask(j,'plan','p',engine.PLAN)
  self.assertIn('usage limit',j['log'][-1]['message'])
 def test_log_is_bounded(self):
  e=FakeEngine();j={}
  for i in range(400):e.log(j,str(i))
  self.assertEqual(len(j['log']),300);self.assertEqual(j['log'][-1]['message'],'399')

class SimulationRunTests(unittest.TestCase):
 def ready(self,states=()):
  e=FakeEngine();public=e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'}});j=e.jobs[public['id']]
  j.update(status='ready',input='[Mesh]\n[]');queue=list(states);rpc=e.rpc;e.calls=[]
  def fake(payload,timeout=220):
   e.calls.append(payload)
   if payload['op']=='run_submit':return {'scheduler_id':'123','ranks':payload['ranks'] or 2,'time':payload['time'] or '00:20:00','folder':'/r/run'}
   if payload['op']=='run_status':return queue.pop(0)
   return rpc(payload,timeout)
  e.rpc=fake;return e,j
 def test_run_requires_ready_job(self):
  e,j=self.ready();j['status']='needs_clarification'
  with self.assertRaises(ValueError):e.run({'id':j['id']})
  self.assertFalse(any(c['op']=='run_submit' for c in e.calls))
 def test_invalid_resources_rejected_before_submission(self):
  for request in ({'ranks':500},{'ranks':'two'},{'time':'1 hour'}):
   e,j=self.ready()
   with self.assertRaises(ValueError):e.run(dict(request,id=j['id']))
   self.assertFalse(any(c['op']=='run_submit' for c in e.calls))
 def test_submission_sends_validated_input_and_starts_monitor(self):
  e,j=self.ready();e.run({'id':j['id'],'ranks':4,'time':'01:00:00'})
  submit=[c for c in e.calls if c['op']=='run_submit'][0]
  self.assertEqual((submit['input'],submit['ranks'],submit['time']),('[Mesh]\n[]',4,'01:00:00'))
  self.assertEqual(j['run']['status'],'queued');self.assertIn('monitor_run',e.launched)
  with self.assertRaises(ValueError):e.run({'id':j['id']})

 def test_invalid_run_requests_rejected_before_submission(self):
  # Machine-local limits come from local_runs in the config and are enforced by the workspace; the engine checks the rest.
  for request in ({'ranks':500},{'time':'1 hour'},{'where':'gpu-cluster'}):
   e,j=self.ready()
   with self.assertRaises(ValueError):e.run(dict({'where':'login'},**request,id=j['id']))
   self.assertFalse(any(c['op']=='run_submit' for c in e.calls))
 def test_login_run_starts_running_immediately(self):
  e,j=self.ready();rpc=e.rpc
  e.rpc=lambda p,timeout=220:{'mode':'login','scheduler_id':None,'node':'login03','ranks':4,'time':'00:10:00','folder':'/r/run'} if p['op']=='run_submit' else rpc(p,timeout)
  e.run({'id':j['id'],'where':'login','ranks':4})
  self.assertEqual(j['run']['status'],'running');self.assertIn('started on login03',j['log'][-1]['message'])
 def test_monitor_reports_completion_without_changing_job_status(self):
  done={'status':'complete','node':'node001','outputs':[{'name':'model_out.csv','size':10}],'folder':'/r/run','postprocessors':{'avg':'1'}}
  e,j=self.ready([{'status':'running','node':'node001'},done])
  e.run({'id':j['id']})
  original=engine.time.sleep;engine.time.sleep=lambda s:None;self.addCleanup(setattr,engine.time,'sleep',original)
  e.monitor_run(j)
  self.assertEqual(j['run']['status'],'complete');self.assertEqual(j['status'],'ready')
  self.assertTrue(any('running on node001' in x['message'] for x in j['log']))
 def test_lost_scheduler_marks_only_the_run_failed(self):
  e,j=self.ready();e.run({'id':j['id']})
  def broken(payload,timeout=220):raise RuntimeError('ssh dropped')
  e.rpc=broken;e.persist=lambda j:None;e.monitor_run(j)
  self.assertEqual(j['run']['status'],'failed');self.assertEqual(j['status'],'ready')

class ModelSummaryTests(unittest.TestCase):
 def test_example_input_summary(self):
  summary=engine.summarize_input((ROOT/'examples/mechanics.i').read_text())
  self.assertEqual(summary['mesh_size'],'1 × 1 (x: 0 to 1, y: 0 to 1)')
  self.assertEqual(summary['resolution'],'20 × 20 = 400 QUAD4 elements')
  self.assertIn('ComputeLagrangianCompressibleNeoHookeanStress (bulk_modulus = 1e9 (bulk), shear_modulus = 1e9 (shear)',summary['constitutive_model'][0])
  self.assertEqual(summary['constitutive_model'][-1],'Kinematics: UPDATED formulation, FINITE strain')
 def test_mesh_generator_and_missing_blocks(self):
  summary=engine.summarize_input('[Mesh]\n [gen]\n  type = GeneratedMeshGenerator\n  dim = 3\n  nx = 4\n  ny = 5\n  nz = 2\n  xmax = 2e-3 # mm\n []\n[]')
  self.assertEqual(summary['resolution'],'4 × 5 × 2 = 40 HEX8 elements');self.assertTrue(summary['mesh_size'].startswith('0.002 × 1 × 1'))
  self.assertEqual(summary['constitutive_model'],['No material blocks in the input'])
  self.assertEqual(engine.summarize_input('[Mesh]\n file = part.e\n[]')['resolution'],'From mesh file part.e')
 def test_older_block_syntax_is_read(self):
  summary=engine.summarize_input('[Mesh]\n  [./gen]\n    type = GeneratedMeshGenerator\n    dim = 2\n    nx = 3\n    ny = 3\n  [../]\n[]\n[Materials]\n  [./k]\n    type = GenericConstantMaterial\n    prop_names = conductivity\n    prop_values = 5\n  [../]\n[]')
  self.assertEqual(summary['resolution'],'3 × 3 = 9 QUAD4 elements');self.assertEqual(summary['constitutive_model'],['GenericConstantMaterial (conductivity = 5)'])
 def test_public_job_includes_summary_only_with_input(self):
  e=FakeEngine();self.assertNotIn('model_summary',e.public({'id':'x'}))
  self.assertIn('resolution',e.public({'id':'x','input':'[Mesh]\n dim = 1\n nx = 8\n[]'})['model_summary'])

class TokenSavingTests(unittest.TestCase):
 def planning_engine(self,answers,check_valid=True,found=None):
  e=FakeEngine();prompts=[];queue=list(answers)
  def llm(model,prompt,schema):
   prompts.append(prompt);e.record_usage(input=1000,cached=400,output=50);return queue.pop(0)
  e.llm=llm;rpc=e.rpc
  source='SOURCE_CODE_MARKER '*500
  def fake(payload,timeout=220):
   op=payload['op']
   if op=='context':return {'object_paths':['NameOnlyInFullList%d'%i for i in range(3000)],'relevant_objects':[{'path':'/Kernels/Diffusion','description':'d'}],
                            'capabilities':[{'id':'c1','summary':'neo-Hookean','objects':['NeoHooke'],'files':['x.C'],'source':[{'path':'x.C','content':source}]}]}
   if op=='details':return [{'path':'/Kernels/'+n,'description':'doc','parameters':{'variable':{'required':True,'description':'v'*500},'control_tags':{'description':'tags'}},
                             'source':[{'path':'k.C','source':source}]} for n in payload['paths']]
   if op=='check':return {'valid':check_valid,'stdout':'*** ERROR: unknown parameter foo\n'+'noise line\n'*6000,'stderr':''}
   if op=='find_ready':return found
   return rpc(payload,timeout)
  e.rpc=fake;return e,prompts
 def plan_answer(self,**kw):
  return dict({'status':'builtin','summary':'s','rationale':'','objects':['Diffusion'],'questions':[],'input':'[Mesh]\n[]'},**kw)
 def job(self,e):
  j=e.jobs[e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'}})['id']];return j
 def test_usage_logged_per_call_and_totalled(self):
  e,prompts=self.planning_engine([{'objects':['Diffusion'],'questions':[]},self.plan_answer()])
  j=self.job(e);e.plan(j)
  self.assertEqual(j['status'],'ready');self.assertEqual(j['usage'],{'calls':2,'input':2000,'cached':800,'output':100,'total':0,'unreported':0})
  self.assertTrue(any('1.0k input tokens, 400 from cache, 50 output' in x['message'] for x in j['log']))
  self.assertTrue(any(x['message'].startswith('Model usage so far: 2 call(s) (2.0k input tokens, 800 from cache, 100 output)') for x in j['log']))
 def test_unreported_usage_is_counted(self):
  e=FakeEngine();j={'model':{}};e.llm=lambda *a:{}
  e.ask(j,'plan','p',engine.PLAN)
  self.assertEqual(j['usage']['unreported'],1);self.assertIn('token usage not reported',j['log'][-1]['message'])
 def test_prompts_leave_out_full_object_list_source_and_boilerplate(self):
  e,prompts=self.planning_engine([{'objects':['Diffusion'],'questions':[]},self.plan_answer()])
  e.plan(self.job(e))
  for prompt in prompts:
   for absent in ('NameOnlyInFullList','SOURCE_CODE_MARKER','control_tags','v'*201):self.assertNotIn(absent,prompt)
  self.assertIn('neo-Hookean',prompts[0]);self.assertIn('/Kernels/Diffusion',prompts[1])
 def test_repair_sends_diagnostics_not_the_planning_prompt(self):
  e,prompts=self.planning_engine([{'objects':['Diffusion'],'questions':[]},self.plan_answer(),self.plan_answer(),self.plan_answer()],check_valid=False)
  j=self.job(e);e.plan(j)
  repair=prompts[2];self.assertEqual(j['status'],'failed')
  self.assertIn('unknown parameter foo',repair);self.assertNotIn('discovery_questions',repair)
  self.assertLess(len(repair),len(prompts[1])+8000);self.assertLess(repair.count('noise line'),400)
 def test_unchanged_graph_reuses_validated_input_without_model_calls(self):
  found={'id':'b'*32,'input':'[Mesh]\n[]','summary':'earlier','model':{'provider':'claude-code','id':'opus'}}
  e,prompts=self.planning_engine([],found=found)
  j=self.job(e);e.plan(j)
  self.assertEqual(prompts,[]);self.assertEqual((j['status'],j['reused_from'],j['input']),('ready','b'*32,'[Mesh]\n[]'))
  self.assertIn('no model calls',j['verification'])
 def test_reuse_falls_back_when_recheck_fails_and_can_be_forced_off(self):
  found={'id':'b'*32,'input':'old','model':{}}
  e,prompts=self.planning_engine([{'objects':[],'questions':['Which material?']},self.plan_answer(status='needs_clarification',questions=['Which material?']),
                                   self.plan_answer(status='needs_clarification',questions=['Which material?'])],check_valid=False,found=found)
  e.plan(self.job(e));self.assertEqual(len(prompts),3)
  e,prompts=self.planning_engine([{'objects':[],'questions':[]},self.plan_answer()],found=found)
  calls=[];rpc=e.rpc;e.rpc=lambda p,timeout=220:calls.append(p['op']) or rpc(p,timeout)
  j=e.jobs[e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'},'force':True})['id']];e.plan(j)
  self.assertNotIn('find_ready',calls);self.assertNotIn('reused_from',j)
 def test_semantic_hash_ignores_layout_and_matches_workspace(self):
  g=graph();g['nodes'][0].update(x=10,y=20);moved=copy.deepcopy(g);moved['nodes'][0].update(x=400,y=90)
  self.assertEqual(engine.semantic_hash(g),engine.semantic_hash(moved));self.assertEqual(engine.semantic_hash(g),workspace.semantic_hash(g))
  changed=copy.deepcopy(g);changed['nodes'][0]['params']={'value':1}
  self.assertNotEqual(engine.semantic_hash(g),engine.semantic_hash(changed))

def mechanics_graph(visualize=None,output_params=None,shear='1e9'):
 solver={'id':'solver','kind':'solver','params':dict({'type':'Transient'},**({'visualize':visualize} if visualize else {})),'x':1,'y':2}
 return {'request':'push the left edge','nodes':[{'id':'mat','kind':'component','category':'Materials','params':{'shear':shear}},solver,
         {'id':'out','kind':'output','params':output_params or {},'x':5,'y':6}],'edges':[{'from':'solver','out':'solution','to':'out','in':'solution'}]}
class OutputEditTests(unittest.TestCase):
 def engine_with_previous(self,previous,answers=()):
  e=FakeEngine();prompts=[];queue=list(answers);rpc=e.rpc
  def llm(model,prompt,schema):prompts.append(prompt);return queue.pop(0)
  e.llm=llm
  found={'id':'f'*32,'input':(ROOT/'examples/mechanics.i').read_text(),'graph':previous,'summary':'neo-Hookean push','model':{'provider':'claude-code','id':'opus'}}
  def fake(payload,timeout=220):
   if payload['op']=='find_ready':return found if payload.get('base_hash')==engine.base_hash(previous) else None
   if payload['op']=='check':return {'valid':True,'stdout':'','stderr':''}
   if payload['op']=='context':return {'object_paths':[],'relevant_objects':[],'capabilities':[]}
   if payload['op']=='details':return []
   return rpc(payload,timeout)
  e.rpc=fake;return e,prompts
 def start(self,e,g):
  j=e.jobs[e.start({'graph':g,'model':{'provider':'local','id':'test-model'}})['id']];e.plan(j);return j
 def test_hashes_separate_output_settings_from_the_model(self):
  g=mechanics_graph();vis=mechanics_graph('cauchy_stress_xx');out=mechanics_graph(output_params={'time_step_interval':2});phys=mechanics_graph(shear='2e9')
  self.assertEqual(len({engine.base_hash(x) for x in (g,vis,out)}),1);self.assertEqual(len({engine.semantic_hash(x) for x in (g,vis,out)}),3)
  self.assertNotEqual(engine.base_hash(g),engine.base_hash(phys));self.assertEqual(engine.base_hash(vis),workspace.base_hash(vis))
  self.assertEqual(engine.visualize_list(mechanics_graph('cauchy_stress_xx, temperature  disp_x')),['cauchy_stress_xx','temperature','disp_x'])
 def test_quantities_already_written_by_the_input(self):
  text=(ROOT/'examples/mechanics.i').read_text()
  self.assertTrue(engine.already_written(text,'disp_x'));self.assertTrue(engine.already_written(text,'cauchy_stress'))
  self.assertTrue(engine.already_written(text,'cauchy_stress_xy'));self.assertFalse(engine.already_written(text,'vonmises_cauchy_stress'))
 def test_already_written_quantity_needs_no_model_call(self):
  e,prompts=self.engine_with_previous(mechanics_graph())
  j=self.start(e,mechanics_graph('cauchy_stress_xx disp_x'))
  self.assertEqual(prompts,[]);self.assertEqual((j['status'],j['output_edit_from']),('ready','f'*32))
  self.assertEqual(j['input'],(ROOT/'examples/mechanics.i').read_text())
 def test_new_output_request_is_a_small_edit_of_the_previous_input(self):
  edited=(ROOT/'examples/mechanics.i').read_text().replace("cauchy_stress_xy'","cauchy_stress_xy vonmises_cauchy_stress'")
  e,prompts=self.engine_with_previous(mechanics_graph(),[{'status':'builtin','summary':'Added von Mises output.','rationale':'','objects':[],'questions':[],'input':edited}])
  j=self.start(e,mechanics_graph('vonmises_cauchy_stress',{'time_step_interval':2}))
  self.assertEqual(len(prompts),1);self.assertEqual((j['status'],j['input']),('ready',edited))
  self.assertIn('previous_input',prompts[0]);self.assertIn('time_step_interval',prompts[0]);self.assertIn('vonmises_cauchy_stress',prompts[0])
  self.assertNotIn('relevant_objects',prompts[0]);self.assertLess(len(prompts[0]),8000)
 def test_physics_change_regenerates_normally(self):
  e,prompts=self.engine_with_previous(mechanics_graph(),[{'objects':[],'questions':[]},{'status':'builtin','summary':'s','rationale':'','objects':[],'questions':[],'input':'x'}])
  j=self.start(e,mechanics_graph('cauchy_stress_xx',shear='2e9'))
  self.assertNotIn('output_edit_from',j);self.assertEqual(len(prompts),2)
 def test_generation_prompt_explains_visualize(self):
  self.assertIn('never write visualize itself into the input',engine.INSTRUCTIONS)

class PromoteSyncTests(unittest.TestCase):
 """promote() with real git repositories: a bare origin, the MOOSE host checkout, and a laptop clone."""
 def git(self,cwd,*args):
  return subprocess.run(['git','-c','user.name=T','-c','user.email=t@t','-c','init.defaultBranch=main']+list(args),cwd=cwd,check=True,capture_output=True,text=True).stdout.strip()
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();base=Path(self.tmp.name)
  self.old=(workspace.ROOT,workspace.STATE)
  self.origin=base/'origin.git';self.git(base,'init','--bare','-b','main',str(self.origin))
  root=base/'moose-host';self.git(base,'clone',str(self.origin),str(root))
  (root/'moose_app/src/base').mkdir(parents=True);(root/'moose_app/src/base/App.C').write_text('base')
  (root/'README.md').write_text('readme\n');(root/'.gitignore').write_text('.vibora/\n')
  self.git(root,'add','.');self.git(root,'commit','-m','initial');self.git(root,'push','origin','main')
  self.laptop=base/'laptop';self.git(base,'clone',str(self.origin),str(self.laptop))
  workspace.ROOT=root;workspace.STATE=root/'.vibora';workspace.STATE.mkdir()
  self.jid='c'*32;folder=workspace.jobdir(self.jid)
  workspace.save(folder/'build_result.json',{'passed':True,'executable':'/apps/vibora-opt'})
  workspace.save(folder/'baseline.json',{'digest':workspace.app_digest()})
  workspace.save(folder/'approval.json',{'plan_hash':'p'})
  workspace.save(folder/'package.json',{'summary':'test kernel','objects':['Test'],'tests':[],'input':'[Mesh]\n[]','files':[{'path':'src/kernels/Test.C'}]})
  (folder/'app/src/kernels').mkdir(parents=True);(folder/'app/src/kernels/Test.C').write_text('verified kernel\n')
 def tearDown(self):
  workspace.ROOT,workspace.STATE=self.old;self.tmp.cleanup()
 def laptop_commit(self,path,text):
  f=self.laptop/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
  self.git(self.laptop,'add',path);self.git(self.laptop,'commit','-m','laptop change '+path);self.git(self.laptop,'push','origin','main')
 def origin_log(self):return self.git(workspace.ROOT,'log','--format=%s','origin/main')
 def test_push_without_newer_github_commits(self):
  r=workspace.promote(self.jid)
  self.assertFalse(r['sync_pending']);self.assertEqual(r['sync']['pulled'],[])
  self.git(workspace.ROOT,'fetch','origin');self.assertIn('Add verified custom MOOSE capability cccccccc',self.origin_log())
 def test_rebases_onto_newer_github_commits_then_pushes(self):
  self.laptop_commit('README.md','readme\nnew docs\n')
  r=workspace.promote(self.jid)
  self.assertFalse(r['sync_pending'],r['sync_message']);self.assertEqual(len(r['sync']['pulled']),1);self.assertFalse(r['sync']['rebuild_needed'])
  self.git(workspace.ROOT,'fetch','origin')
  self.assertEqual(self.git(workspace.ROOT,'rev-parse','HEAD'),self.git(workspace.ROOT,'rev-parse','origin/main'))
  self.assertEqual(self.origin_log().splitlines()[:2],['Add verified custom MOOSE capability cccccccc','laptop change README.md'])
  self.assertEqual((workspace.ROOT/'README.md').read_text(),'readme\nnew docs\n')
 def test_backend_changes_from_github_ask_for_rebuild(self):
  self.laptop_commit('backend/main.cpp','int main(){}\n')
  r=workspace.promote(self.jid)
  self.assertTrue(r['sync']['rebuild_needed']);self.assertIn('rebuild',r['sync_message'])
 def test_conflict_aborts_rebase_and_keeps_commit_local(self):
  self.laptop_commit('moose_app/src/kernels/Test.C','a different kernel\n')
  before=self.git(self.laptop,'rev-parse','HEAD')
  r=workspace.promote(self.jid)
  self.assertTrue(r['sync_pending']);self.assertIn('conflict',r['sync_message']);self.assertIn('Test.C',r['sync']['conflict'])
  self.assertFalse((workspace.ROOT/'.git/rebase-merge').exists());self.assertFalse((workspace.ROOT/'.git/rebase-apply').exists())
  self.assertEqual(self.git(workspace.ROOT,'log','-1','--format=%s'),'Add verified custom MOOSE capability cccccccc')
  self.assertEqual(self.git(workspace.ROOT,'status','--porcelain','--untracked-files=no'),'')
  self.assertEqual(self.git(workspace.ROOT,'rev-parse','origin/main'),before)
 def test_uncommitted_changes_block_the_rebase(self):
  self.laptop_commit('README.md','from github\n');(workspace.ROOT/'README.md').write_text('local edit\n')
  r=workspace.promote(self.jid)
  self.assertTrue(r['sync_pending']);self.assertIn('uncommitted changes',r['sync_message']);self.assertEqual(r['sync']['dirty'],['M README.md'])
  self.assertEqual((workspace.ROOT/'README.md').read_text(),'local edit\n')

class CustomRepairTests(unittest.TestCase):
 def package(self):
  return {'summary':'hotspot','objects':['ViboraHotspotMaterial'],'input':'[ICs] twice',
          'files':[{'path':'src/materials/A.C','content':'a'},{'path':'include/materials/A.h','content':'h'}],
          'tests':[{'name':'t','input':'x','checks':[{'column':'v','expected':1,'tolerance':0.1}]}]}
 def engine(self,repairs,results):
  e=FakeEngine();j={'id':'d'*32,'status':'coding','model':{},'coding_prompt':'code it','package':self.package(),'summary':''}
  staged=[];queue=list(results);rpc=e.rpc
  def fake(payload,timeout=220):
   op=payload['op']
   if op=='stage':
    if not payload['package']['files'] or not payload['package']['tests']:raise RuntimeError('Custom code requires source files and executable quantitative tests')
    staged.append(copy.deepcopy(payload['package']));return {}
   if op=='submit':return {'scheduler_id':'local','status':'running'}
   if op=='build_status':return queue.pop(0)
   if op=='promote':return {'retained':True,'capability':'d'*32}
   return rpc(payload,timeout)
  e.rpc=fake;answers=list(repairs);e.llm=lambda *a:answers.pop(0)
  return e,j,staged
 failed_check={'status':'complete','result':{'passed':False,'phase':'input_check','validation':{'stderr':'*** ERROR ***\nThe initial condition is being defined twice'}}}
 passed={'status':'complete','result':{'passed':True,'phase':'tests','tests':[{'passed':True}]}}
 def test_input_only_repair_keeps_source_files_and_tests(self):
  e,j,staged=self.engine([{'summary':'','objects':[],'input':'[ICs] once','files':[],'tests':[]}],[self.failed_check,self.passed])
  e.monitor(j)
  self.assertEqual(j['status'],'ready');self.assertEqual(len(staged),1)
  self.assertEqual([f['path'] for f in staged[0]['files']],['src/materials/A.C','include/materials/A.h'])
  self.assertEqual((staged[0]['input'],len(staged[0]['tests']),staged[0]['summary']),('[ICs] once',1,'hotspot'))
 def test_repair_replaces_changed_files_by_path(self):
  e,j,staged=self.engine([{'summary':'fixed','objects':[],'input':'','files':[{'path':'src/materials/A.C','content':'a2'},{'path':'include/materials/A.h','content':''}],'tests':[]}],[self.failed_check,self.passed])
  e.monitor(j)
  self.assertEqual(staged[0]['files'],[{'path':'src/materials/A.C','content':'a2'}]);self.assertEqual(staged[0]['input'],'[ICs] twice')
 def test_unbuildable_package_fails_with_clear_reason(self):
  e,j,staged=self.engine([],[])
  j['package']['tests']=[];e.submit_package(j)
  self.assertEqual(j['status'],'failed');self.assertIn('cannot be built',j['error']);self.assertIn('0 test(s)',j['error'])
 def test_repair_prompt_asks_for_complete_package(self):
  prompts=[];e,j,staged=self.engine([],[self.failed_check,self.passed])
  e.llm=lambda model,prompt,schema:prompts.append(prompt) or {'input':'[ICs] once','files':[],'tests':[]}
  e.monitor(j)
  self.assertIn('every source file (unchanged ones too)',prompts[0]);self.assertIn('initial condition is being defined twice',prompts[0])

class RetainedCapabilityPromptTests(unittest.TestCase):
 caps=[{'id':'h'*32,'summary':'hotspot JWL with J2','objects':['ViboraHotspotJWLJ2'],'source':[{'path':'src/materials/ViboraHotspotJWLJ2.C','content':'params.addRequiredParam<Real>("detonation_velocity","D");'}]},
       {'id':'n'*32,'summary':'neo-Hookean','objects':['NeoHooke'],'source':[{'path':'x.C','content':'NEO_SOURCE'}]}]
 def test_source_only_for_needed_objects_missing_from_the_catalog(self):
  out=engine.brief_capabilities(self.caps,['Materials/ViboraHotspotJWLJ2','GeneratedMesh'],['/Mesh/GeneratedMesh'])
  self.assertIn('detonation_velocity',json.dumps(out[0]));self.assertNotIn('source',out[1])
  documented=engine.brief_capabilities(self.caps,['ViboraHotspotJWLJ2'],['/Materials/ViboraHotspotJWLJ2'])
  self.assertNotIn('source',documented[0])
  self.assertEqual(engine.brief_capabilities(self.caps),[{'id':'h'*32,'summary':'hotspot JWL with J2','objects':['ViboraHotspotJWLJ2']},{'id':'n'*32,'summary':'neo-Hookean','objects':['NeoHooke']}])
 def test_planning_and_review_prompts_carry_the_needed_interface(self):
  e=FakeEngine();prompts=[];rpc=e.rpc
  answers=[{'objects':['ViboraHotspotJWLJ2'],'questions':[]},
           {'status':'needs_clarification','summary':'s','rationale':'','objects':['ViboraHotspotJWLJ2'],'questions':['Which interface?'],'input':''},
           {'status':'needs_clarification','summary':'s','rationale':'','objects':['ViboraHotspotJWLJ2'],'questions':['Which interface?'],'input':''}]
  e.llm=lambda model,prompt,schema:prompts.append(prompt) or answers.pop(0)
  def fake(payload,timeout=220):
   if payload['op']=='context':return {'object_paths':[],'relevant_objects':[],'capabilities':self.caps}
   if payload['op']=='details':return []
   return rpc(payload,timeout)
  e.rpc=fake;j=e.jobs[e.start({'graph':graph(),'model':{'provider':'local','id':'test-model'}})['id']];e.plan(j)
  self.assertNotIn('detonation_velocity',prompts[0]);self.assertIn('detonation_velocity',prompts[1]);self.assertIn('detonation_velocity',prompts[2])
  self.assertNotIn('NEO_SOURCE',prompts[1]+prompts[2])
  self.assertTrue(any('does not document: ViboraHotspotJWLJ2' in x['message'] for x in j['log']))

class InferenceTests(unittest.TestCase):
 def setup_graph(self):
  return {'request':'Run for 10 seconds with dt=0.1', 'nodes':[
   {'id':'mesh','kind':'mesh','params':{'dim':2,'nx':20,'ny':20}},
   {'id':'ux','label':'disp_x','kind':'variable','params':{'name':'disp_x'}},
   {'id':'uy','label':'disp_y','kind':'variable','params':{'name':'disp_y'}},
   {'id':'ic','category':'ICs','physics':'zero displacement','params':{}},
   {'id':'material','category':'Materials','params':{}}],
   'edges':[{'from':'mesh','out':'mesh','to':'ux','in':'mesh'},
            {'from':'ic','out':'IC','to':'ux','in':'IC'},
            {'from':'ic','out':'IC','to':'uy','in':'IC'}]}
 def test_structured_dimension_and_shared_ic_are_exposed_without_mutation(self):
  g=self.setup_graph();original=copy.deepcopy(g);e=engine.graph_evidence(g)
  self.assertEqual(e['blocks'][0]['specified_parameters'],{'dim':2,'nx':20,'ny':20})
  self.assertEqual(e['blocks'][0]['template_defaults']['xmax'],1)
  self.assertEqual(e['blocks'][1]['template_defaults']['family'],'LAGRANGE')
  self.assertEqual(e['blocks'][1]['incoming'][0]['source_parameters']['dim'],2)
  self.assertEqual(e['blocks'][1]['incoming'][1]['source_id'],'ic')
  self.assertEqual(e['blocks'][2]['incoming'][0]['source_id'],'ic')
  self.assertEqual(e['blocks'][4]['specified_parameters'],{})
  self.assertEqual(g,original)
 def test_redundant_questions_are_reviewed_before_publishing(self):
  e=FakeEngine();j={'id':'test','graph':self.setup_graph(),'model':{'provider':'local','id':'test'}}
  prompts=[]
  def answer(model,prompt,schema):
   prompts.append(prompt)
   return {'status':'needs_clarification','summary':'Need material data','rationale':'','objects':[],
           'questions':['What are the material constants?'],'input':''}
  e.llm=answer
  p={'status':'needs_clarification','summary':'Missing mesh','rationale':'','objects':[],
     'questions':['What is the mesh dimension?','What are the material constants?'],'input':''}
  e.finish_plan(j,p,'plan')
  self.assertEqual(j['questions'],['What are the material constants?'])
  self.assertIn('"dim": 2',prompts[0]);self.assertIn('Run for 10 seconds',prompts[0])
  self.assertNotIn('check',e.operations)
 def test_fully_answered_questions_continue_to_moose_validation(self):
  e=FakeEngine();j={'id':'test','graph':self.setup_graph(),'model':{}}
  e.llm=lambda *args:{'status':'builtin','summary':'2D setup','rationale':'','objects':[],'questions':[],'input':'model'}
  rpc=e.rpc
  e.rpc=lambda p,**kw: {'valid':True} if p['op']=='check' else rpc(p,**kw)
  e.finish_plan(j,{'status':'needs_clarification','questions':['Dimension?']},'plan')
  self.assertEqual(j['status'],'ready')
 def test_valid_plan_does_not_spend_a_review_call(self):
  e=FakeEngine();e.llm=lambda *a: self.fail('Unexpected LLM call')
  p={'status':'builtin','questions':[]};self.assertIs(e.review_questions({},p,''),p)

class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=(workspace.ROOT,workspace.STATE,workspace.MOOSE,dict(workspace.CONFIG))
  # Registered first, so it runs after every other cleanup (cleanups run last-in, first-out, after tearDown).
  config=dict(workspace.CONFIG);self.addCleanup(lambda:(workspace.CONFIG.clear(),workspace.CONFIG.update(config)))
  workspace.ROOT=Path(self.tmp.name);workspace.STATE=workspace.ROOT/'.vibora';workspace.STATE.mkdir()
  # Keep the real home folder (and any real conda environments next to MOOSE) out of these tests.
  workspace.MOOSE=workspace.ROOT/'src'/'moose'
  workspace.CONFIG['scheduler']={'enabled':True,'account':'acct','partition':'cpu','qos':'','memory':'8G','gpus':0}
  (workspace.ROOT/'moose_app/src/base').mkdir(parents=True);(workspace.ROOT/'moose_app/src/base/App.C').write_text('base')
  self.jid='a'*32
 def tearDown(self):
  workspace.ROOT,workspace.STATE,workspace.MOOSE=self.old[:3];self.tmp.cleanup()
 def test_run_submit_requires_ready_state_and_exact_input(self):
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':'good'})
  with self.assertRaises(ValueError):workspace.run_submit(self.jid,'tampered',1,'')
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'checking','input':'good'})
  with self.assertRaises(ValueError):workspace.run_submit(self.jid,'good',1,'')
 def test_run_submit_builds_slurm_request(self):
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':'[Mesh]\n[]'})
  calls=[];original=workspace.run
  workspace.run=lambda args,**kw:calls.append(args) or {'returncode':0,'stdout':'4242\n','stderr':''}
  self.addCleanup(setattr,workspace,'run',original)
  result=workspace.run_submit(self.jid,'[Mesh]\n[]',3,'00:45:00')
  args=calls[0];self.assertEqual(args[0],'sbatch')
  self.assertEqual(args[args.index('--ntasks')+1],'3');self.assertEqual(args[args.index('--time')+1],'00:45:00')
  folder=workspace.jobdir(self.jid)/'run'
  self.assertEqual(result['scheduler_id'],'4242');self.assertEqual((folder/'model.i').read_text(),'[Mesh]\n[]')
  self.assertIn('mpiexec -n 3',(folder/'run.sbatch').read_text())
 def test_finished_run_reports_final_csv_values(self):
  folder=workspace.jobdir(self.jid)/'run';folder.mkdir()
  workspace.save(folder/'scheduler.json',{'id':'7'});(folder/'exit_code').write_text('0\n');(folder/'node').write_text('node001\n')
  (folder/'model_out.csv').write_text('time,avg\n0,0\n1,2.5\n');(folder/'moose.log').write_text('Solve Converged!')
  status=workspace.run_status(self.jid)
  self.assertEqual(status['status'],'complete');self.assertEqual(status['postprocessors'],{'time':'1','avg':'2.5'})
  self.assertEqual(status['node'],'node001');self.assertEqual([f['name'] for f in status['outputs']],['model_out.csv','moose.log'])
 def test_cancelled_run_is_not_reported_as_failure(self):
  folder=workspace.jobdir(self.jid)/'run';folder.mkdir()
  workspace.save(folder/'scheduler.json',{'id':'7','cancelled':True});(folder/'exit_code').write_text('143')
  self.assertEqual(workspace.run_status(self.jid)['status'],'cancelled')

 def login_tools(self,moose_body):
  # Stand-ins for GNU timeout, mpiexec and the MOOSE executable on the login node.
  bin=workspace.ROOT/'bin';bin.mkdir()
  for name,body in (('timeout','shift 2\nexec "$@"'),('mpiexec',moose_body)):
   (bin/name).write_text('#!/bin/bash\n'+body+'\n');(bin/name).chmod(0o755)
  old=(dict(workspace.CONFIG),workspace.BASE)
  workspace.CONFIG['toolchain_bin']=[str(bin)];workspace.BASE=bin/'moose-opt'
  self.addCleanup(lambda:(workspace.CONFIG.clear(),workspace.CONFIG.update(old[0]),setattr(workspace,'BASE',old[1])))
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':'[Mesh]\n[]'})
 def wait_for(self,statuses,limit=20):
  for _ in range(limit*5):
   status=workspace.run_status(self.jid)
   if status['status'] in statuses:return status
   time.sleep(.2)
  self.fail('Run never reached '+str(statuses)+': '+str(status))
 def test_login_run_completes_without_slurm(self):
  self.login_tools('printf "time,avg\\n1,4.5\\n" > model_out.csv; echo "ranks=$2"')
  result=workspace.run_submit(self.jid,'[Mesh]\n[]',3,'','login')
  self.assertEqual((result['mode'],result['ranks'],result['time']),('login',3,'00:10:00'))
  status=self.wait_for(('complete','failed'))
  self.assertEqual(status['status'],'complete');self.assertEqual(status['postprocessors'],{'time':'1','avg':'4.5'})
  self.assertIn('ranks=3',status['log_tail'])
 def test_login_run_cancelled_through_shared_flag(self):
  self.login_tools('sleep 60')
  workspace.run_submit(self.jid,'[Mesh]\n[]',1,'','login')
  self.assertEqual(self.wait_for(('running',))['mode'],'login')
  workspace.run_cancel(self.jid)
  self.assertEqual(self.wait_for(('cancelled','failed','complete'))['status'],'cancelled')
 def test_login_run_limits(self):
  self.login_tools('true')
  for ranks,wall in ((5,''),(2,'02:00:00')):
   with self.assertRaises(ValueError):workspace.run_submit(self.jid,'[Mesh]\n[]',ranks,wall,'login')
 def test_login_run_without_heartbeat_reports_failure(self):
  folder=workspace.jobdir(self.jid)/'run';folder.mkdir()
  workspace.save(folder/'scheduler.json',{'mode':'login','node':'login03','time':'00:10:00','submitted_at':time.time()-600})
  status=workspace.run_status(self.jid)
  self.assertEqual(status['status'],'failed');self.assertIn('stopped without finishing',status['error'])

 def test_run_scripts_write_exodus_and_render_images(self):
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':'[Mesh]\n[]'})
  original=workspace.run;workspace.run=lambda args,**kw:{'returncode':0,'stdout':'5\n','stderr':''}
  self.addCleanup(setattr,workspace,'run',original)
  self.conda_config(render_conda_prefix=str(workspace.ROOT/'envs/moose'))
  workspace.run_submit(self.jid,'[Mesh]\n[]',2,'')
  script=(workspace.jobdir(self.jid)/'run/run.sbatch').read_text()
  self.assertIn('Outputs/exodus=true',script);self.assertIn('render_results.py',script)
  self.assertLess(script.index('code=$?'),script.index('render_results.py'));self.assertTrue(script.rstrip().endswith('echo $code > exit_code'))
 def test_run_status_reports_rendered_images(self):
  folder=workspace.jobdir(self.jid)/'run';(folder/'images').mkdir(parents=True)
  workspace.save(folder/'scheduler.json',{'id':'7'});(folder/'exit_code').write_text('0')
  workspace.save(folder/'images/manifest.json',{'deformed':True,'images':[{'variable':'temp','time':1.0,'step':3,'file':'temp_003.png'}]})
  status=workspace.run_status(self.jid)
  self.assertEqual(status['images'][0]['file'],'temp_003.png');self.assertTrue(status['images_deformed'])
  self.assertNotIn('images',[f['name'] for f in status['outputs']])
  workspace.save(folder/'images/manifest.json',{'error':'Result images need numpy'})
  self.assertEqual(workspace.run_status(self.jid)['images_error'],'Result images need numpy')

 def conda_config(self,**settings):
  old=dict(workspace.CONFIG);self.addCleanup(lambda:(workspace.CONFIG.clear(),workspace.CONFIG.update(old)))
  for k in ('render_python','render_conda_prefix','render_conda_env'):workspace.CONFIG.pop(k,None)
  workspace.CONFIG.update(settings)
 def fake_home(self):
  home=workspace.ROOT/'home';home.mkdir(exist_ok=True)
  environ=dict(os.environ);self.addCleanup(lambda:(os.environ.clear(),os.environ.update(environ)))
  os.environ['HOME']=str(home);os.environ.pop('CONDA_EXE',None)
  which=workspace.shutil.which;workspace.shutil.which=lambda name:None;self.addCleanup(setattr,workspace.shutil,'which',which)
  return home
 def fake_env(self,prefix):
  # A python that records the environment it was started with instead of rendering.
  (prefix/'bin').mkdir(parents=True);python=prefix/'bin'/'python'
  python.write_text('#!/bin/bash\necho "$CONDA_PREFIX|$CONDA_DEFAULT_ENV|${PATH%%:*}|$1" > ran_in\n');python.chmod(0o755)
  return prefix
 def run_render_command(self):
  folder=workspace.ROOT/'run';folder.mkdir(exist_ok=True)
  subprocess.run(['bash','-c',workspace.render_command()],cwd=folder,check=True)
  return folder
 def test_images_render_inside_moose_conda_env(self):
  home=self.fake_home();prefix=self.fake_env(home/'miniforge3/envs/moose');self.conda_config()
  folder=self.run_render_command()
  self.assertEqual((folder/'ran_in').read_text().strip(),str(prefix)+'|moose|'+str(prefix/'bin')+'|'+str(workspace.ROOT/'scripts/render_results.py'))
 def test_conda_env_found_through_conda_env_list(self):
  home=self.fake_home();prefix=self.fake_env(workspace.ROOT/'elsewhere/envs/moose');self.conda_config()
  conda=home/'conda';conda.write_text('#!/bin/bash\necho \'{"envs": ["/opt/base", "'+str(prefix)+'"]}\'\n');conda.chmod(0o755)
  os.environ['CONDA_EXE']=str(conda)
  self.assertEqual(workspace.conda_env_prefix('moose'),prefix)
 def test_explicit_prefix_and_interpreter_override(self):
  self.fake_home();prefix=self.fake_env(workspace.ROOT/'custom/moose');self.conda_config(render_conda_prefix=str(prefix))
  self.assertIn(str(prefix/'bin'/'python'),workspace.render_command())
  self.conda_config(render_python='/usr/bin/python3');self.assertTrue(workspace.render_command().startswith('/usr/bin/python3 '))
 def test_missing_conda_env_is_explained_in_gallery(self):
  self.fake_home();self.conda_config(render_conda_env='moose')
  folder=self.run_render_command()
  error=json.loads((folder/'images/manifest.json').read_text())['error']
  self.assertIn('"moose" was not found',error);self.assertIn('render_conda_prefix',error)

 def test_find_ready_returns_newest_matching_ready_job(self):
  g=graph();h=workspace.semantic_hash(g)
  for jid,status,updated,stored in (('1'*32,'ready',5,h),('2'*32,'ready',9,None),('3'*32,'failed',20,h),('4'*32,'ready',30,h)):
   workspace.save(workspace.jobdir(jid)/'state.json',{'id':jid,'status':status,'updated_at':updated,'input':'in'+jid[0],'graph':g,**({'semantic_hash':stored} if stored else {})})
  self.assertEqual(workspace.find_ready(h,exclude='4'*32)['id'],'2'*32)
  self.assertEqual(workspace.find_ready(h)['id'],'4'*32);self.assertIsNone(workspace.find_ready('other'))

 def test_find_ready_by_base_hash_returns_graph(self):
  g=mechanics_graph('temperature');workspace.save(workspace.jobdir('1'*32)/'state.json',{'id':'1'*32,'status':'ready','input':'in','graph':g,'updated_at':1})
  found=workspace.find_ready(workspace.base_hash(mechanics_graph('cauchy_stress_xx')),key='base_hash')
  self.assertEqual((found['id'],found['graph']),('1'*32,g))
  self.assertIsNone(workspace.find_ready(workspace.semantic_hash(mechanics_graph('cauchy_stress_xx'))))
 def test_run_writes_visualize_list_for_images(self):
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':'[Mesh]\n[]','graph':mechanics_graph('cauchy_stress_xx temperature')})
  original=workspace.run;workspace.run=lambda args,**kw:{'returncode':0,'stdout':'5\n','stderr':''}
  self.addCleanup(setattr,workspace,'run',original)
  workspace.run_submit(self.jid,'[Mesh]\n[]',2,'')
  self.assertEqual(json.loads((workspace.jobdir(self.jid)/'run/visualize.json').read_text()),{'names':['cauchy_stress_xx','temperature']})
 def test_slurm_arguments_skip_empty_settings(self):
  workspace.CONFIG['scheduler']={'enabled':True,'account':'','partition':'gpu','qos':'','memory':'','gpus':2,'extra_args':['--constraint=a100']}
  args=workspace.slurm_args('00:05:00',['--ntasks',4])
  self.assertEqual(args,['sbatch','--parsable','--time','00:05:00','--partition','gpu','--gres','gpu:2','--constraint=a100','--ntasks','4'])
 def test_compute_node_runs_need_slurm_enabled(self):
  workspace.CONFIG['scheduler']={'enabled':False}
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':'in'})
  with self.assertRaises(ValueError) as e:workspace.run_submit(self.jid,'in',2,'','slurm')
  self.assertIn('scheduler.enabled',str(e.exception))
 def test_local_run_limits_come_from_config(self):
  workspace.CONFIG['local_runs']={'max_ranks':8,'max_time':'00:30:00','default_time':'00:05:00'}
  self.login_tools('true')
  self.assertEqual(workspace.run_submit(self.jid,'[Mesh]\n[]',8,'','login')['time'],'00:05:00')
  self.wait_for(('complete','failed'))
  with self.assertRaises(ValueError):workspace.run_submit(self.jid,'[Mesh]\n[]',2,'00:45:00','login')
 def test_local_run_wall_time_is_enforced_without_gnu_timeout(self):
  self.login_tools('sleep 30')
  workspace.run_submit(self.jid,'[Mesh]\n[]',1,'00:00:01','login')
  status=self.wait_for(('failed','complete','cancelled'),limit=30)
  self.assertEqual(status['status'],'failed');self.assertIn('Wall time limit',status['error'])
 def test_builds_run_locally_without_slurm(self):
  workspace.CONFIG['scheduler']={'enabled':False}
  folder=workspace.jobdir(self.jid);workspace.save(folder/'approval.json',{'plan_hash':'x'})
  started=[];original=workspace.subprocess.Popen
  class Process:
   pid=os.getpid()
   def __init__(self,args,**kw):started.append(args)
  workspace.subprocess.Popen=Process;self.addCleanup(setattr,workspace.subprocess,'Popen',original)
  self.assertEqual(workspace.submit(self.jid),{'scheduler_id':'local','status':'running'})
  self.assertEqual(started[0][-2:],['--build',self.jid]);self.assertEqual(workspace.build_status(self.jid)['status'],'running')
  workspace.save(folder/'build_result.json',{'passed':True});self.assertEqual(workspace.build_status(self.jid)['status'],'complete')
 def test_output_overrides_only_for_missing_outputs(self):
  sub_block='[Outputs]\n  [exodus]\n    type = Exodus\n    time_step_interval = 2\n  []\n[]'
  self.assertEqual(workspace.output_overrides(sub_block),['Outputs/csv=true'])
  typed='[Outputs]\n  [./out]\n    type = CSV # postprocessors\n  [../]\n  [field]\n    type = Exodus\n  []\n[]'
  self.assertEqual(workspace.output_overrides(typed),[])
  path_syntax='[Outputs/csv]\n  type = CSV\n[]\n[Outputs]\n  exodus = true\n[]'
  self.assertEqual(workspace.output_overrides(path_syntax),[])
  self.assertEqual(workspace.output_overrides('[Outputs]\n  exodus = false\n  csv = true\n[]'),['Outputs/exodus=true'])
  self.assertEqual(workspace.output_overrides('[Mesh]\n  [exodus]\n  []\n[]'),['Outputs/csv=true','Outputs/exodus=true'])
  self.assertEqual(workspace.output_overrides(sub_block,('csv',)),['Outputs/csv=true'])
 def test_run_script_skips_exodus_switch_when_input_has_exodus_block(self):
  text='[Mesh]\n[]\n[Outputs]\n  [exodus]\n    type = Exodus\n  []\n[]'
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'ready','input':text})
  original=workspace.run;workspace.run=lambda args,**kw:{'returncode':0,'stdout':'5\n','stderr':''}
  self.addCleanup(setattr,workspace,'run',original)
  workspace.run_submit(self.jid,text,2,'')
  script=(workspace.jobdir(self.jid)/'run/run.sbatch').read_text()
  self.assertIn('-i model.i Outputs/csv=true > moose.log',script);self.assertNotIn('Outputs/exodus',script)

 def test_catalog_comes_from_the_active_app_and_refreshes_after_rebuild(self):
  exe=workspace.ROOT/'vibora_physics-opt'
  def build(kind):
   exe.write_text('#!/bin/bash\necho \'**START JSON DATA**{"blocks":{"Materials":{"star":{"subblock_types":{"%s":{"description":"d","parameters":{"p":{}}}}}}}}**END JSON DATA**\'\n'%kind);exe.chmod(0o755)
  build('ViboraHotspotJWLJ2');workspace.save(workspace.STATE/'active_app.json',{'executable':str(exe)})
  self.assertIn('ViboraHotspotJWLJ2',workspace.catalog())
  self.assertTrue(all(f.name.startswith('vibora_physics-opt-') for f in (workspace.STATE/'catalog').glob('*.json')))
  build('ViboraHotspotJWLJ2Plus');os.utime(exe,(1,1))
  self.assertIn('ViboraHotspotJWLJ2Plus',workspace.catalog())
 def test_no_approval_no_staging(self):
  with self.assertRaises(ValueError):workspace.stage(self.jid,{'files':[],'tests':[]})
  self.assertFalse((workspace.jobdir(self.jid)/'app').exists())
 def package(self):
  return {'summary':'test','input':'[Mesh]\n[]','objects':['Test'],
   'files':[{'path':'src/kernels/Test.C','content':'test'}],
   'tests':[{'name':'small','input':'test','checks':[{'column':'u','expected':1,'tolerance':1e-8}]}]}
 def allow(self):workspace.save(workspace.jobdir(self.jid)/'approval.json',{'plan_hash':'x'})
 def test_path_traversal_rejected(self):
  self.allow();p=self.package();p['files'][0]['path']='../../outside.C'
  with self.assertRaises(ValueError):workspace.stage(self.jid,p)
 def test_existing_source_cannot_be_overwritten(self):
  self.allow();p=self.package();dest=workspace.ROOT/'moose_app'/p['files'][0]['path'];dest.parent.mkdir(parents=True);dest.write_text('original')
  with self.assertRaises(ValueError):workspace.stage(self.jid,p)
  self.assertEqual(dest.read_text(),'original')
 def test_quantitative_assertions_required(self):
  self.allow();p=self.package();p['tests'][0]['checks']=[]
  with self.assertRaises(ValueError):workspace.stage(self.jid,p)
 def test_source_stays_isolated_before_verification(self):
  self.allow();p=self.package();workspace.stage(self.jid,p)
  self.assertTrue((workspace.jobdir(self.jid)/'app/src/kernels/Test.C').exists())
  self.assertFalse((workspace.ROOT/'moose_app/src/kernels/Test.C').exists())
 def test_failed_build_cannot_be_promoted(self):
  workspace.save(workspace.jobdir(self.jid)/'build_result.json',{'passed':False})
  with self.assertRaises(ValueError):workspace.promote(self.jid)
 def test_approval_requires_pending_matching_plan(self):
  workspace.save(workspace.jobdir(self.jid)/'state.json',{'status':'awaiting_approval','plan_hash':'correct','graph_hash':'graph'})
  with self.assertRaises(ValueError):workspace.authorize(self.jid,'wrong')
  self.assertFalse((workspace.jobdir(self.jid)/'approval.json').exists())
  self.assertTrue(workspace.authorize(self.jid,'correct')['approved'])
if __name__=='__main__':unittest.main()
