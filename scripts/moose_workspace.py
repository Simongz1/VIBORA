#!/usr/bin/env python3
"""SSH JSON RPC for catalog discovery, isolated MOOSE builds and persistent capabilities."""
import csv, fcntl, hashlib, json, math, os, re, shlex, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.vibora'
STATE.mkdir(exist_ok=True)
CONFIG=json.loads((ROOT/'config.example.json').read_text())
if (ROOT/'config.local.json').exists():CONFIG.update(json.loads((ROOT/'config.local.json').read_text()))
MOOSE=Path(CONFIG['moose_dir'])
BASE=Path(CONFIG['moose_executable'])
def run(args,cwd=None,timeout=120,env=None):
 p=subprocess.run([str(x) for x in args],cwd=cwd,text=True,capture_output=True,timeout=timeout,env=env)
 return {'returncode':p.returncode,'stdout':p.stdout[-60000:],'stderr':p.stderr[-10000:]}
def jobdir(jid):
 if not re.fullmatch(r'[a-f0-9]{32}',jid):raise ValueError('Invalid job identifier')
 p=STATE/'jobs'/jid;p.mkdir(parents=True,exist_ok=True);return p
def save(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2));temp.replace(path)
def app_digest():
 h=hashlib.sha256()
 for p in sorted((ROOT/'moose_app').rglob('*')):
  if p.is_file() and (p.suffix in ('.C','.h') or p.name=='Makefile'):
   h.update(str(p.relative_to(ROOT)).encode());h.update(p.read_bytes())
 return h.hexdigest()
def catalog():
 path=STATE/'catalog'/'ml.json'
 if not path.exists():
  p=subprocess.run([str(BASE),'--json'],text=True,capture_output=True,timeout=180)
  text=p.stdout.split('**START JSON DATA**')[-1].split('**END JSON DATA**')[0]
  data=json.loads(text);path.parent.mkdir(exist_ok=True);save(path,data)
 data=json.loads(path.read_text());entries={}
 def walk(obj,path=''):
  if not isinstance(obj,dict):return
  if 'parameters' in obj and ('description' in obj or 'action_path' in obj):
   entries[path]={'path':path,'description':obj.get('description',''),'parameters':obj['parameters'],'file_info':obj.get('file_info',{}),'syntax':obj.get('action_path','')}
  for k,v in obj.items():
   if k not in ('parameters','file_info') and isinstance(v,dict):walk(v,path+'/'+k)
 walk(data.get('blocks',{}))
 unique={}
 for path,e in sorted(entries.items(),key=lambda item:len(item[0])):
  unique.setdefault(path.rsplit('/',1)[-1],e)
 return unique
def context(request):
 entries=catalog();words=set(re.findall(r'[a-z]{4,}',json.dumps(request.get('graph',{})).lower()))
 ranked=sorted(entries.values(),key=lambda e:sum(w in (e['path']+' '+e['description']).lower() for w in words),reverse=True)
 capabilities=[]
 for p in sorted((ROOT/'capabilities').glob('*/manifest.json')):
  m=json.loads(p.read_text())
  capabilities.append({k:m[k] for k in ('id','summary','objects','files')})
  capabilities[-1]['source']=[{'path':f,'content':(ROOT/'moose_app'/f).read_text()} for f in m['files']]
 return {'object_paths':list(entries),'relevant_objects':[{'path':e['path'],'description':e['description'][:200]} for e in ranked[:150]],
         'capabilities':capabilities,'application':'MARLINS (mlApp), all registered MOOSE modules','custom_application':'ViboraPhysicsApp',
         'source_digest':app_digest()}
def details(paths):
 entries=catalog();result=[]
 paths=[p.rsplit('/',1)[-1] for p in paths]
 for key in paths[:35]:
  if key not in entries:continue
  e=dict(entries[key]);e['parameters']={k:{a:v for a,v in p.items() if a in ('required','default','cpp_type','description','options')} for k,p in e['parameters'].items()}
  snippets=[]
  for raw in list(e.get('file_info',{}))[:1]:
   p=Path(raw)
   if p.is_file() and (MOOSE in p.parents or BASE.parent in p.parents):
    snippets.append({'path':raw,'source':p.read_text()[:14000]})
  e['source']=snippets;result.append(e)
 return result
def executable():
 p=STATE/'active_app.json'
 if p.exists():
  candidate=Path(json.loads(p.read_text())['executable'])
  if candidate.exists():return candidate
 return BASE
def check_input(jid,text):
 if not isinstance(text,str) or not text.strip() or len(text)>200000:raise ValueError('Input is empty or too large')
 folder=jobdir(jid)/'builtin';folder.mkdir(exist_ok=True)
 path=folder/'model.i';path.write_text(text)
 result=run([executable(),'-i',path,'--check-input'],cwd=folder,timeout=120)
 result['valid']=result['returncode']==0;result['executable']=str(executable());result['input_path']=str(path)
 save(folder/'validation.json',result);return result
def semantic_hash(g):
 # Must match semantic_hash in workflow_engine.py: canvas positions do not change the model.
 nodes=sorted(({k:v for k,v in n.items() if k not in ('x','y')} for n in g.get('nodes',[])),key=lambda n:str(n.get('id')))
 edges=sorted(g.get('edges',[]),key=lambda e:json.dumps(e,sort_keys=True))
 return hashlib.sha256(json.dumps({'request':g.get('request',''),'nodes':nodes,'edges':edges},sort_keys=True).encode()).hexdigest()
def find_ready(semantic,exclude=None):
 # Newest ready job for the same model; older jobs without a stored hash are hashed from their graph.
 best=None
 for path in (STATE/'jobs').glob('*/state.json'):
  try:state=json.loads(path.read_text())
  except (OSError,ValueError):continue
  if state.get('id')==exclude or state.get('status')!='ready' or not state.get('input'):continue
  h=state.get('semantic_hash') or (semantic_hash(state['graph']) if isinstance(state.get('graph'),dict) else None)
  if h==semantic and (best is None or state.get('updated_at',0)>best.get('updated_at',0)):best=state
 return {k:best[k] for k in ('id','input','plan','summary','model','retained','updated_at') if k in best} if best else None
def authorize(jid,plan_hash):
 path=jobdir(jid)/'state.json'
 data=json.loads(path.read_text())
 if data['status']!='awaiting_approval' or data.get('plan_hash')!=plan_hash:raise ValueError('Approval does not match the pending plan')
 save(jobdir(jid)/'approval.json',{'plan_hash':plan_hash,'approved_at':time.time(),'graph_hash':data['graph_hash']})
 return {'approved':True}
def stage(jid,package):
 folder=jobdir(jid)
 if not (folder/'approval.json').exists():raise ValueError('Custom implementation requires explicit approval')
 app=folder/'app'
 # Each repair starts from the retained, verified project.
 if app.exists():shutil.rmtree(app)
 shutil.copytree(ROOT/'moose_app',app,ignore=shutil.ignore_patterns('build','lib','*-opt','*.o','*.lo','*.d','*.la'))
 files=package.get('files',[]);tests=package.get('tests',[])
 if not files or not tests:raise ValueError('Custom code requires source files and executable quantitative tests')
 seen=set()
 for f in files:
  path=f['path']
  if not re.fullmatch(r'(include|src)/(kernels|materials|bcs|auxkernels|functions|userobjects|postprocessors|ics)/[A-Za-z][A-Za-z0-9_]*\.(h|C)',path):raise ValueError('Invalid custom source path: '+path)
  if path in seen or (ROOT/'moose_app'/path).exists():raise ValueError('Custom source must use a new, unique file path: '+path)
  if len(f['content'])>100000:raise ValueError('Source file too large')
  seen.add(path);p=app/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(f['content'])
 for t in tests:
  if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,50}',t['name']):raise ValueError('Invalid test name')
  if not t.get('checks'):raise ValueError('A test needs numerical CSV assertions')
  for c in t['checks']:
   if not math.isfinite(float(c['expected'])) or not math.isfinite(float(c['tolerance'])) or c['tolerance']<0:raise ValueError('Invalid numeric check')
 (folder/'build_result.json').unlink(missing_ok=True)
 (folder/'scheduler.json').unlink(missing_ok=True)
 save(folder/'package.json',package)
 save(folder/'baseline.json',{'digest':app_digest()})
 (folder/'model.i').write_text(package['input'])
 return {'staged':True,'files':[f['path'] for f in files],'tests':[t['name'] for t in tests]}
def run_tests(exe,folder,tests,env=None):
 outcomes=[]
 for t in tests:
  p=folder/t['name'];p.mkdir(parents=True,exist_ok=True);inp=p/'test.i';inp.write_text(t['input'])
  r=run(['mpiexec','-n','1',exe,'-i',inp,'Outputs/csv=true','Outputs/file_base=result'],cwd=p,timeout=120,env=env)
  checks=[]
  if r['returncode']==0:
   csvpath=p/'result.csv'
   if not csvpath.exists():r['returncode']=1;r['stderr']+='\nExpected result.csv was not produced.'
   else:
    with csvpath.open() as f:rows=list(csv.DictReader(f))
    for c in t['checks']:
     try:actual=float(rows[-1][c['column']]);ok=math.isfinite(actual) and abs(actual-c['expected'])<=c['tolerance']
     except (KeyError,IndexError,ValueError):actual=None;ok=False
     checks.append(dict(c,actual=actual,passed=ok))
    if not all(c['passed'] for c in checks):r['returncode']=1
  outcomes.append({'name':t['name'],'passed':r['returncode']==0,'checks':checks,'log':r})
 return outcomes
def build_test(jid):
 folder=jobdir(jid);package=json.loads((folder/'package.json').read_text());app=folder/'app'
 env=dict(os.environ,MOOSE_DIR=str(MOOSE),METHOD='opt',MOOSE_JOBS='2',OMP_NUM_THREADS='1')
 env['PATH']=os.pathsep.join(CONFIG.get('toolchain_bin',[])+[env.get('PATH','')])
 result={'passed':False,'phase':'build'}
 try:
  build=run(['make','-j2'],cwd=app,timeout=900,env=env);result['build']=build
  if build['returncode']!=0:return result
  exe=app/'vibora_physics-opt'
  result['phase']='input_check';result['validation']=run(['mpiexec','-n','1',exe,'-i',folder/'model.i','--check-input'],cwd=folder,timeout=120,env=env)
  if result['validation']['returncode']!=0:return result
  tests=list(package['tests'])
  for manifest in (ROOT/'capabilities').glob('*/manifest.json'):
   for t in json.loads(manifest.read_text()).get('tests',[]):tests.append(dict(t,name=manifest.parent.name[:8]+'_'+t['name']))
  result['phase']='tests';result['tests']=run_tests(exe,folder/'tests',tests,env=env)
  result['passed']=all(t['passed'] for t in result['tests'])
  result['executable']=str(exe);return result
 except Exception as e:result['error']=str(e);return result
 finally:save(folder/'build_result.json',result)
def submit(jid):
 folder=jobdir(jid)
 if not (folder/'approval.json').exists():raise ValueError('No custom-code approval')
 cfg=CONFIG['scheduler']
 script=folder/'build.sbatch'
 script.write_text('#!/bin/bash\nset -euo pipefail\ncd '+str(ROOT)+'\npython3 scripts/moose_workspace.py --build '+jid+'\n')
 args=['sbatch','--parsable','--account',cfg['account'],'--partition',cfg['partition'],'--qos',cfg['qos'],
       '--gres','gpu:'+str(cfg.get('gpus',1)),'--time',cfg['time'],'--cpus-per-task',str(cfg['cpus']),'--mem',cfg['memory'],'--output',str(folder/'scheduler.log'),str(script)]
 r=run(args,timeout=30)
 if r['returncode']!=0:raise RuntimeError(r['stderr'] or r['stdout'])
 scheduler_id=r['stdout'].strip().split(';')[0]
 if not scheduler_id.isdigit():raise RuntimeError('Invalid scheduler response')
 save(folder/'scheduler.json',{'id':scheduler_id});return {'scheduler_id':scheduler_id,'status':'queued'}
def build_status(jid):
 folder=jobdir(jid)
 if (folder/'build_result.json').exists():return {'status':'complete','result':json.loads((folder/'build_result.json').read_text())}
 if not (folder/'scheduler.json').exists():return {'status':'not_submitted'}
 sid=json.loads((folder/'scheduler.json').read_text())['id']
 r=run(['squeue','-h','-j',sid,'-o','%T|%R'],timeout=20)
 state=r['stdout'].strip()
 if state:return {'status':'running' if state.startswith('RUNNING') else 'queued','scheduler':state,'scheduler_id':sid}
 log=(folder/'scheduler.log').read_text()[-8000:] if (folder/'scheduler.log').exists() else ''
 return {'status':'failed','error':'Scheduler job ended without a build result.','log':log,'scheduler_id':sid}
RUN_FILES={'model.i','run.sbatch','run.sh','scheduler.json','exit_code','node','slurm.log','heartbeat','cancel','launcher.log','render.log'}
LOGIN_MAX_RANKS=4
LOGIN_MAX_SECONDS=3600
def run_results(folder):
 result={'folder':str(folder),'outputs':[],'postprocessors':{}}
 if (folder/'node').exists():result['node']=(folder/'node').read_text().strip()
 if (folder/'moose.log').exists():result['log_tail']=(folder/'moose.log').read_text(errors='replace')[-6000:]
 for f in sorted(folder.iterdir()):
  if f.is_file() and f.name not in RUN_FILES:result['outputs'].append({'name':f.name,'size':f.stat().st_size})
 # Final-row postprocessor values from the main CSV output.
 csvs=sorted(folder.glob('*.csv'),key=lambda f:(not f.name.endswith('_out.csv'),f.name))
 if csvs:
  with csvs[0].open() as f:rows=list(csv.DictReader(f))
  if rows:result['postprocessors']=rows[-1];result['csv']=csvs[0].name;result['csv_rows']=len(rows)
 manifest=folder/'images'/'manifest.json'
 if manifest.exists():
  m=json.loads(manifest.read_text());result['images']=m.get('images',[])
  if m.get('error'):result['images_error']=m['error']
  if m.get('deformed'):result['images_deformed']=True
 return result
CONDA_BASES=('miniforge3','mambaforge','miniconda3','anaconda3')
def conda_env_prefix(name):
 # Folder of the named conda environment: explicit setting, the usual install folders, then conda's own list.
 if CONFIG.get('render_conda_prefix'):return Path(CONFIG['render_conda_prefix']).expanduser()
 bases=[Path.home()/b for b in CONDA_BASES]+[Path.home()/'.conda']+[p/b for p in list(MOOSE.parents)[:3] for b in CONDA_BASES]
 for base in bases:
  if (base/'envs'/name/'bin'/'python').exists():return base/'envs'/name
 conda=os.environ.get('CONDA_EXE') or shutil.which('conda') or shutil.which('mamba')
 if conda:
  try:envs=json.loads(subprocess.run([conda,'env','list','--json'],text=True,capture_output=True,timeout=20).stdout).get('envs',[])
  except (OSError,ValueError,subprocess.TimeoutExpired):envs=[]
  for e in envs:
   if Path(e).name==name and (Path(e)/'bin'/'python').exists():return Path(e)
 return None
def render_command():
 # Result images run in the conda environment that has numpy, matplotlib and netCDF4 (default: moose).
 script=shlex.quote(str(ROOT/'scripts'/'render_results.py'))+' . > render.log 2>&1'
 if CONFIG.get('render_python'):return shlex.quote(CONFIG['render_python'])+' '+script
 name=CONFIG.get('render_conda_env','moose');prefix=conda_env_prefix(name)
 if prefix is None:
  error={'error':'Conda environment "'+name+'" was not found for result images (looked in ~/'+', ~/'.join(CONDA_BASES)+', ~/.conda, next to '+str(MOOSE.parent)+
   ' and in "conda env list"). Set render_conda_prefix in config.local.json to the environment folder, for example ~/miniforge3/envs/'+name+'.'}
  return 'mkdir -p images && printf "%s\\n" '+shlex.quote(json.dumps(error))+' > images/manifest.json'
 # Equivalent of "conda activate" for this command: the environment's tools first on PATH.
 bin=prefix/'bin'
 return ('env PATH='+shlex.quote(str(bin))+':"$PATH" CONDA_PREFIX='+shlex.quote(str(prefix))+' CONDA_DEFAULT_ENV='+shlex.quote(name)+' '
         +shlex.quote(str(bin/'python'))+' '+script)
def seconds(wall):
 h,m,s=(int(x) for x in wall.split(':'));return h*3600+m*60+s
def run_submit(jid,text,ranks,wall,where='slurm'):
 state=json.loads((jobdir(jid)/'state.json').read_text())
 # Only the exact input of a validated job may be run.
 if state.get('status')!='ready' or state.get('input')!=text:raise ValueError('Only the validated input of a ready job can be run')
 if where not in ('slurm','login'):raise ValueError('Unknown run location')
 folder=jobdir(jid)/'run'
 if (folder/'scheduler.json').exists() and run_status(jid)['status'] in ('queued','running'):raise ValueError('A simulation for this job is already queued or running')
 if folder.exists():shutil.rmtree(folder)
 folder.mkdir()
 cfg=CONFIG['scheduler']
 if where=='login':
  ranks=int(ranks) or 1;wall=wall or '00:10:00'
  if not 1<=ranks<=LOGIN_MAX_RANKS:raise ValueError('Login-node runs are limited to '+str(LOGIN_MAX_RANKS)+' MPI ranks')
  if seconds(wall)>LOGIN_MAX_SECONDS:raise ValueError('Login-node runs are limited to 01:00:00 wall time')
 else:ranks=int(ranks) or int(cfg.get('run_ranks',cfg['cpus']));wall=wall or cfg.get('run_time',cfg['time'])
 (folder/'model.i').write_text(text)
 toolchain=os.pathsep.join(CONFIG.get('toolchain_bin',[]))
 head=('#!/bin/bash\nset -uo pipefail\ncd '+shlex.quote(str(folder))+'\n'
  +('export PATH='+shlex.quote(toolchain)+':"$PATH"\n' if toolchain else '')
  +'export OMP_NUM_THREADS=1\nhostname > node\n')
 moose='mpiexec -n '+str(ranks)+' '+shlex.quote(str(executable()))+' -i model.i Outputs/csv=true Outputs/exodus=true > moose.log 2>&1'
 # Result images come from the Exodus output; a rendering problem never changes the run's exit code.
 render=render_command()
 if where=='login':
  # Status checks may reach a different login node, so all state lives in files on the shared filesystem:
  # a heartbeat while running, a cancel flag the loop obeys, and the exit code at the end.
  script=folder/'run.sh'
  script.write_text(head+'timeout --signal=TERM '+str(seconds(wall))+' '+moose+' &\nchild=$!\n'
   +'watch(){ while kill -0 "$1" 2>/dev/null; do touch heartbeat; [ -f cancel ] && kill -TERM "$1"; sleep 5; done; }\n'
   +'watch "$child"; wait "$child"; code=$?\n'
   +'if [ ! -f cancel ]; then '+render+' & child=$!; watch "$child"; wait "$child"; fi\n'
   +'echo $code > exit_code\n')
  with (folder/'launcher.log').open('w') as log:
   subprocess.Popen(['bash',str(script)],cwd=folder,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
  node=os.uname().nodename
  save(folder/'scheduler.json',{'mode':'login','node':node,'ranks':ranks,'time':wall,'submitted_at':time.time()})
  return {'mode':'login','scheduler_id':None,'node':node,'ranks':ranks,'time':wall,'folder':str(folder)}
 script=folder/'run.sbatch'
 script.write_text(head+moose+'\ncode=$?\n'+render+' || true\necho $code > exit_code\n')
 args=['sbatch','--parsable','--job-name','vibora-run-'+jid[:8],'--account',cfg['account'],'--partition',cfg['partition'],'--qos',cfg['qos'],
       '--gres','gpu:'+str(cfg.get('gpus',1)),'--time',wall,'--ntasks',str(ranks),'--cpus-per-task','1','--mem',cfg['memory'],
       '--output',str(folder/'slurm.log'),str(script)]
 r=run(args,timeout=30)
 if r['returncode']!=0:raise RuntimeError(r['stderr'] or r['stdout'])
 sid=r['stdout'].strip().split(';')[0]
 if not sid.isdigit():raise RuntimeError('Invalid scheduler response')
 save(folder/'scheduler.json',{'mode':'slurm','id':sid,'ranks':ranks,'time':wall,'submitted_at':time.time()})
 return {'mode':'slurm','scheduler_id':sid,'ranks':ranks,'time':wall,'partition':cfg['partition'],'folder':str(folder)}
def run_status(jid):
 folder=jobdir(jid)/'run'
 if not (folder/'scheduler.json').exists():return {'status':'not_submitted'}
 meta=json.loads((folder/'scheduler.json').read_text());sid=meta.get('id');mode=meta.get('mode','slurm')
 cancelled=meta.get('cancelled') or (folder/'cancel').exists()
 if (folder/'exit_code').exists():
  code=int((folder/'exit_code').read_text().strip() or 1)
  result=dict(run_results(folder),returncode=code,scheduler_id=sid,mode=mode)
  if code and cancelled:return dict(result,status='cancelled')
  if code==124 and mode=='login':return dict(result,status='failed',error='Login-node wall time limit ('+meta['time']+') reached.')
  return dict(result,status='complete' if code==0 else 'failed')
 if mode=='login':
  beat=folder/'heartbeat';last=beat.stat().st_mtime if beat.exists() else meta['submitted_at']
  if time.time()-last<90:return {'status':'running','node':meta['node'],'mode':'login','scheduler_id':None}
  log=(folder/'launcher.log').read_text(errors='replace')[-4000:] if (folder/'launcher.log').exists() else ''
  return dict(run_results(folder),status='cancelled' if cancelled else 'failed',mode='login',scheduler_id=None,
              error='The login-node process stopped without finishing (killed, or the node rebooted).',scheduler_log=log)
 r=run(['squeue','-h','-j',sid,'-o','%T|%R|%N'],timeout=20)
 line=r['stdout'].strip()
 if line:
  st,reason,node=(line.split('|')+['',''])[:3]
  return {'status':'running' if st=='RUNNING' else 'queued','scheduler':st,'reason':reason,'node':node,'scheduler_id':sid,'mode':'slurm'}
 result=dict(run_results(folder),scheduler_id=sid,mode='slurm')
 if cancelled:return dict(result,status='cancelled')
 log=(folder/'slurm.log').read_text(errors='replace')[-4000:] if (folder/'slurm.log').exists() else ''
 return dict(result,status='failed',error='Slurm job ended before MOOSE finished (time limit, memory or node failure).',scheduler_log=log)
def run_cancel(jid):
 folder=jobdir(jid)/'run';meta=json.loads((folder/'scheduler.json').read_text())
 if meta.get('mode')=='login':(folder/'cancel').write_text('cancel\n');return {'cancelling':True}
 r=run(['scancel',meta['id']],timeout=20)
 if r['returncode']!=0:raise RuntimeError(r['stderr'] or 'scancel failed')
 meta['cancelled']=True;save(folder/'scheduler.json',meta);return {'cancelling':True}
def promote(jid):
 folder=jobdir(jid);result=json.loads((folder/'build_result.json').read_text())
 if not result.get('passed'):raise ValueError('Cannot retain an unverified implementation')
 with (STATE/'promotion.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  baseline=json.loads((folder/'baseline.json').read_text())
  if baseline['digest']!=app_digest():raise ValueError('App changed during build. Rebuild against the latest source before promotion.')
  package=json.loads((folder/'package.json').read_text())
  for f in package['files']:
   dest=ROOT/'moose_app'/f['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(folder/'app'/f['path'],dest)
  cap=ROOT/'capabilities'/jid;cap.mkdir(parents=True,exist_ok=True)
  manifest={'id':jid,'summary':package['summary'],'objects':package['objects'],'tests':package['tests'],
            'files':[f['path'] for f in package['files']],'verification':result,'approved':json.loads((folder/'approval.json').read_text())}
  save(cap/'manifest.json',manifest);(cap/'model.i').write_text(package['input'])
  save(STATE/'active_app.json',{'executable':result['executable'],'capability':jid})
  # Commit only files produced by this approved implementation.
  paths=['moose_app/'+f['path'] for f in package['files']]+[str(cap.relative_to(ROOT))]
  run(['git','add','--']+paths,cwd=ROOT)
  commit=run(['git','-c','user.name=VIBORA','-c','user.email=vibora@localhost','commit','--only','-m','Add verified custom MOOSE capability '+jid[:8],'--']+paths,cwd=ROOT)
  push=run(['git','push','origin','HEAD'],cwd=ROOT,timeout=30,env=dict(os.environ,GIT_TERMINAL_PROMPT='0')) if commit['returncode']==0 else {'returncode':1,'stderr':'Commit failed'}
  return {'retained':True,'capability':jid,'manifest':str(cap/'manifest.json'),'commit':commit,'push':push,'sync_pending':push['returncode']!=0}
def dispatch(r):
 op=r['op'];jid=r.get('id')
 if op=='context':return context(r)
 if op=='details':return details(r.get('paths',[]))
 if op=='check':return check_input(jid,r['input'])
 if op=='save_job':save(jobdir(jid)/'state.json',r['state']);return {'saved':True}
 if op=='load_job':return json.loads((jobdir(jid)/'state.json').read_text())
 if op=='authorize':return authorize(jid,r['plan_hash'])
 if op=='find_ready':return find_ready(r['semantic_hash'],r.get('exclude'))
 if op=='stage':return stage(jid,r['package'])
 if op=='submit':return submit(jid)
 if op=='build_status':return build_status(jid)
 if op=='promote':return promote(jid)
 if op=='run_submit':return run_submit(jid,r['input'],r.get('ranks',0),r.get('time',''),r.get('where','slurm'))
 if op=='run_status':return run_status(jid)
 if op=='run_cancel':return run_cancel(jid)
 raise ValueError('Unknown operation')
if __name__=='__main__':
 if len(sys.argv)==3 and sys.argv[1]=='--build':
  result=build_test(sys.argv[2]);print(json.dumps(result));sys.exit(0 if result['passed'] else 1)
 try:print(json.dumps({'ok':True,'result':dispatch(json.load(sys.stdin))}))
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)}));sys.exit(1)
