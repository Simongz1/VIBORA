import copy
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
        cls.process=subprocess.Popen([BINARY,str(cls.port),WEB],stdout=subprocess.DEVNULL)
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
        cls.process.terminate();cls.process.wait(timeout=5)
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
    def test_web(self):
        with urllib.request.urlopen(self.url('/')) as r:self.assertIn(b'VIBORA',r.read())
        with urllib.request.urlopen(self.url('/api/catalog')) as r:self.assertEqual(len(json.load(r)),6)

if __name__=='__main__': unittest.main()
