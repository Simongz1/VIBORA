import copy,importlib.util,json,tempfile,types,unittest
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
  self.tmp=tempfile.TemporaryDirectory();self.old=(workspace.ROOT,workspace.STATE)
  workspace.ROOT=Path(self.tmp.name);workspace.STATE=workspace.ROOT/'.vibora';workspace.STATE.mkdir()
  (workspace.ROOT/'moose_app/src/base').mkdir(parents=True);(workspace.ROOT/'moose_app/src/base/App.C').write_text('base')
  self.jid='a'*32
 def tearDown(self):
  workspace.ROOT,workspace.STATE=self.old;self.tmp.cleanup()
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
