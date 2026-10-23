"""Build and test a trusted development fixture (through Slurm if enabled, otherwise locally); never promotes it."""
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
result=w.start_build(jid)
(root/'.vibora/fixture-job').write_text(jid)
print(json.dumps({'job':jid,'build':result,'result_file':str(folder/'build_result.json')}))
