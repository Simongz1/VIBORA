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
