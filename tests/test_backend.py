import copy
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import pathlib
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
import urllib.error

BINARY, WEB = sys.argv[1:3]
sys.argv = sys.argv[:1]
def example():
    kinds = ['mesh', 'variable', 'diffusion', 'boundary', 'boundary', 'solver', 'output']
    params = [{'dim': 2, 'nx': 20, 'ny': 20}, {'name': 'u'}, {}, {'boundary': 'left', 'value': 0}, {'boundary': 'right', 'value': 1}, {}, {}]
    nodes = [dict(id='b'+str(i), kind=k, params=p, label=k, x=50+i*150, y=100) for i,(k,p) in enumerate(zip(kinds,params))]
    links = [(0,'mesh',1,'mesh'),(1,'field',2,'field'),(1,'field',3,'field'),(1,'field',4,'field'),(2,'operator',5,'operator'),(3,'constraint',5,'constraint'),(4,'constraint',5,'constraint'),(5,'solution',6,'solution')]
    return dict(version=1,nodes=nodes,edges=[dict(**{'from':'b'+str(a),'out':o,'to':'b'+str(b),'in':i}) for a,o,b,i in links])

class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); cls.port=s.getsockname()[1]
        class Agent(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                graph=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                prompt=graph['nodes'][5].get('method','')
                plan={'summary':'Compiled descriptions','patches':[],'unresolved':[]}
                if prompt=='unsupported':
                    plan['unresolved']=['Solid mechanics is not supported yet.']
                elif prompt=='bad_patch':
                    plan['patches']=[dict(node='b5',key='shell',value='"bad"',reason='invalid')]
                elif prompt=='return_to_steady':
                    plan['patches']=[dict(node='b5',key='type',value='"Steady"',reason='requested')]
                    plan['patches'] += [dict(node='b5',key=k,value='null',reason='Remove transient settings') for k in ['dt','end_time','scheme']]
                else:
                    plan['patches']=[dict(node=n,key=k,value=json.dumps(v),reason='Requested in description')
                        for n,k,v in [('b5','type','Transient'),('b5','dt',0.1),('b5','end_time',1),('b1','initial_condition',0)]]
                body=json.dumps(plan).encode();self.send_response(200)
                self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
        cls.agent=ThreadingHTTPServer(('127.0.0.1',0),Agent)
        threading.Thread(target=cls.agent.serve_forever,daemon=True).start()
        env=dict(os.environ,VIBORA_AGENT_PORT=str(cls.agent.server_port))
        cls.process=subprocess.Popen([BINARY,str(cls.port),WEB],stdout=subprocess.DEVNULL,env=env)
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.url('/api/catalog'),timeout=1).close()
                break
            except OSError: time.sleep(.1)
        else:
            cls.process.terminate()
            raise RuntimeError('Server failed to start')
    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=5);cls.agent.shutdown();cls.agent.server_close()
    @classmethod
    def url(cls,path): return 'http://127.0.0.1:'+str(cls.port)+path
    def post(self,g,path='/api/validate'):
        req=urllib.request.Request(self.url(path),data=json.dumps(g).encode(),headers={'Content-Type':'application/json'})
        try: response=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e: response=e
        return response.status,json.load(response)
    def test_valid_and_generate(self):
        status,r=self.post(example(),'/api/generate')
        self.assertEqual(status,200);self.assertTrue(r['valid'])
        self.assertIn('type = Diffusion',r['input']);self.assertEqual(r['input'].count('type = DirichletBC'),2)
        self.assertIn('variable = u',r['input']);self.assertIn('type = Steady',r['input'])
    def test_missing_dependency_blocks_generation(self):
        g=example();g['edges'].pop()
        status,r=self.post(g,'/api/generate')
        self.assertEqual(status,422);self.assertNotIn('input',r)
    def test_incompatible_connection(self):
        g=example();g['edges'][0]['out']='field'
        self.assertFalse(self.post(g)[1]['valid'])
    def test_duplicate_id(self):
        g=example();g['nodes'][1]['id']='b0'
        self.assertFalse(self.post(g)[1]['valid'])
    def test_conflicting_bc(self):
        g=example();g['nodes'][4]['params']['boundary']='left'
        self.assertFalse(self.post(g)[1]['valid'])
    def test_dimension_boundary(self):
        g=example();g['nodes'][0]['params']['dim']=1;g['nodes'][4]['params']['boundary']='top'
        self.assertFalse(self.post(g)[1]['valid'])
    def test_injection(self):
        g=example();g['nodes'][1]['params']['name']='u\n[]\n[Bad]'
        self.assertFalse(self.post(g,'/api/generate')[1]['valid'])
    def test_schema_and_parameter_errors(self):
        for g in [None,[],{},dict(nodes=[None],edges=[])]:
            self.assertFalse(self.post(g)[1]['valid'])
        for val in ['two',None,{},0,1001]:
            g=example();g['nodes'][0]['params']['nx']=val
            self.assertFalse(self.post(g)[1]['valid'])
    def test_dangling_and_duplicate_edges(self):
        g=example();g['edges'][0]['from']='missing'
        self.assertFalse(self.post(g)[1]['valid'])
        g=example();g['edges'].append(copy.deepcopy(g['edges'][0]))
        self.assertFalse(self.post(g)[1]['valid'])
    def test_cli_matches_http(self):
        p=subprocess.run([BINARY,'--generate'],input=json.dumps(example()),capture_output=True,text=True)
        self.assertEqual(p.returncode,0);self.assertEqual(p.stdout,self.post(example(),'/api/generate')[1]['input'])
    def transient(self):
        g=example();g['nodes'][5]['params']={'type':'Transient','dt':0.1,'end_time':1}
        g['nodes'][1]['params']['initial_condition']=0
        return g
    def test_transient_has_accumulation_and_ic(self):
        status,r=self.post(self.transient(),'/api/generate')
        self.assertEqual(status,200)
        for text in ['type = Transient','type = TimeDerivative','initial_condition = 0','dt = 0.1','end_time = 1']:
            self.assertIn(text,r['input'])
    def test_transient_missing_requirements(self):
        for node,key in [(5,'dt'),(5,'end_time'),(1,'initial_condition')]:
            g=self.transient();del g['nodes'][node]['params'][key]
            status,r=self.post(g,'/api/generate')
            self.assertEqual(status,422);self.assertNotIn('input',r)
    def test_invalid_time_settings(self):
        for k,v in [('dt',-1),('dt',0),('end_time',0),('num_steps',1.5),('scheme','bad')]:
            g=self.transient();g['nodes'][5]['params'][k]=v
            self.assertFalse(self.post(g,'/api/generate')[1]['valid'])
    def test_agent_changes_actual_input(self):
        g=example();g['nodes'][5]['method']='Transient dt .1 end 1 initial zero'
        status,r=self.post(g,'/api/generate')
        self.assertEqual(status,200);self.assertIn('type = TimeDerivative',r['input'])
        self.assertEqual(r['resolvedGraph']['nodes'][5]['params']['type'],'Transient')
        self.assertEqual(len(r['changes']),4)
    def test_unresolved_never_returns_input(self):
        g=example();g['nodes'][5]['method']='unsupported'
        status,r=self.post(g,'/api/generate')
        self.assertEqual(status,422);self.assertNotIn('input',r)
    def test_agent_patch_allowlist(self):
        g=example();g['nodes'][5]['method']='bad_patch'
        self.assertFalse(self.post(g,'/api/generate')[1]['valid'])
    def test_agent_can_return_to_steady(self):
        g=self.transient();g['nodes'][5]['method']='return_to_steady'
        status,r=self.post(g,'/api/generate')
        self.assertEqual(status,200);self.assertIn('type = Steady',r['input'])
        self.assertNotIn('TimeDerivative',r['input']);self.assertNotIn('dt =',r['input'])
    def test_offline_agent_does_not_ignore_descriptions(self):
        g=example();g['nodes'][5]['method']='Transient'
        env=dict(os.environ);env.pop('VIBORA_AGENT_PORT',None)
        p=subprocess.run([BINARY,'--generate'],input=json.dumps(g),capture_output=True,text=True,env=env)
        self.assertNotEqual(p.returncode,0);self.assertEqual(p.stdout,'')
        self.assertIn('offline',p.stderr)
    def test_web(self):
        with urllib.request.urlopen(self.url('/')) as r:self.assertIn(b'VIBORA',r.read())
        with urllib.request.urlopen(self.url('/api/catalog')) as r:self.assertEqual(len(json.load(r)),6)

if __name__=='__main__': unittest.main()
