"""Submit a trusted development fixture; never promotes it into the capability library."""
import importlib.util,json,shutil,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('workspace',root/'scripts/moose_workspace.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
jid=uuid.uuid4().hex;folder=w.jobdir(jid)
shutil.copytree(root/'moose_app',folder/'app',ignore=shutil.ignore_patterns('build','lib','*-opt'))
for ext,category in [('h','include'),('C','src')]:
 dest=folder/'app'/category/'kernels'/('ViboraFixtureSource.'+ext);dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(root/'tests/fixtures'/dest.name,dest)
inp=(root/'tests/fixtures/poisson.i').read_text();(folder/'model.i').write_text(inp)
w.save(folder/'package.json',{'tests':[{'name':'poisson','input':inp,'checks':[{'column':'midpoint','expected':0.125,'tolerance':1e-8}]}]})
script=folder/'fixture.sbatch';script.write_text('#!/bin/bash\ncd '+str(root)+'\npython3 scripts/moose_workspace.py --build '+jid+'\n')
c=w.CONFIG['scheduler']
r=w.run(['sbatch','--parsable','--account',c['account'],'--partition',c['partition'],'--qos',c['qos'],'--gres','gpu:1','--time',c['time'],'--cpus-per-task','2','--mem','8G','--output',str(folder/'scheduler.log'),str(script)])
if r['returncode']:raise RuntimeError(r)
sid=r['stdout'].strip().split(';')[0];w.save(folder/'scheduler.json',{'id':sid})
(root/'.vibora/fixture-job').write_text(jid)
print(json.dumps({'job':jid,'scheduler':sid}))
