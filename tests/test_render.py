import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HAVE=all(importlib.util.find_spec(m) for m in ('numpy','matplotlib','netCDF4'))
def exodus(path,dim=2,uniform=False):
 # A small MOOSE-style Exodus file: 2x2 QUAD4 mesh, disp_x/disp_y/temp over 5 times.
 import numpy as np,netCDF4
 xs,ys=np.meshgrid(np.linspace(0,1,3),np.linspace(0,1,3));x,y=xs.ravel(),ys.ravel()
 with netCDF4.Dataset(str(path),'w',format='NETCDF4') as f:
  f.createDimension('num_nodes',9);f.createDimension('time_step',None);f.createDimension('num_nod_var',3)
  f.createDimension('len_name',33);f.createDimension('num_el_in_blk1',4);f.createDimension('num_nod_per_el1',4)
  f.createVariable('coordx','f8',('num_nodes',))[:]=x
  if dim>1:f.createVariable('coordy','f8',('num_nodes',))[:]=y
  if dim>2:f.createVariable('coordz','f8',('num_nodes',))[:]=x+y
  f.createVariable('connect1','i4',('num_el_in_blk1','num_nod_per_el1'))[:]=[[1,2,5,4],[2,3,6,5],[4,5,8,7],[5,6,9,8]]
  times=f.createVariable('time_whole','f8',('time_step',))
  names=f.createVariable('name_nod_var','S1',('num_nod_var','len_name'))
  for i,n in enumerate(['disp_x','disp_y','temp']):names[i]=netCDF4.stringtoarr(n,33)
  # One element field, as MOOSE writes stress components from generate_output.
  f.createDimension('num_elem_var',1)
  enames=f.createVariable('name_elem_var','S1',('num_elem_var','len_name'));enames[0]=netCDF4.stringtoarr('cauchy_stress_xx',33)
  stress=f.createVariable('vals_elem_var1eb1','f8',('time_step','num_el_in_blk1'))
  for t in range(5):
   times[t]=0.1*t;stress[t]=[1e6*t*k for k in (1,2,3,4)]
   for i,v in enumerate([0.01*t*x,0*y,300+0*x if uniform else 300+10*t*x]):
    if t==0:f.createVariable('vals_nod_var%d'%(i+1),'f8',('time_step','num_nodes'))
    f.variables['vals_nod_var%d'%(i+1)][t]=v
@unittest.skipUnless(HAVE,'numpy, matplotlib and netCDF4 are needed to test result images')
class RenderTests(unittest.TestCase):
 def run_render(self,dim=2,uniform=False,visualize=None):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);folder=Path(tmp.name)
  exodus(folder/'model_out.e',dim,uniform)
  if visualize is not None:(folder/'visualize.json').write_text(json.dumps({'names':visualize}))
  subprocess.run([sys.executable,str(ROOT/'scripts/render_results.py'),str(folder)],check=True,capture_output=True)
  return folder,json.loads((folder/'images/manifest.json').read_text())
 def test_snapshots_at_selected_times_on_deformed_mesh(self):
  folder,m=self.run_render()
  self.assertTrue(m['deformed']);self.assertNotIn('error',m)
  self.assertEqual(sorted({i['variable'] for i in m['images']}),['cauchy_stress_xx','disp_x','disp_y','temp'])
  temp=[i for i in m['images'] if i['variable']=='temp']
  self.assertEqual([i['step'] for i in temp],[0,1,3,4]);self.assertEqual(temp[0]['variable'],m['images'][0]['variable'])
  for i in m['images']:self.assertEqual((folder/'images'/i['file']).read_bytes()[:4],b'\x89PNG')
 def test_uniform_field_gets_one_labelled_frame(self):
  folder,m=self.run_render(uniform=True)
  temp=[i for i in m['images'] if i['variable']=='temp']
  self.assertEqual(len(temp),1);self.assertEqual((temp[0]['uniform'],temp[0]['time'],temp[0]['time_end']),(300.0,0.0,0.4))
  self.assertEqual(len([i for i in m['images'] if i['variable']=='disp_x']),4)
 def test_visualize_list_selects_fields_including_element_stress(self):
  folder,m=self.run_render(visualize=['cauchy_stress','temp','vonmises_stress'])
  self.assertEqual([i['variable'] for i in m['images'][::4]],['cauchy_stress_xx','temp'])
  self.assertEqual({i['location'] for i in m['images'] if i['variable']=='cauchy_stress_xx'},{'element'})
  self.assertEqual(m['missing'],['vonmises_stress']);self.assertIn('disp_x',m['available'])
  for i in m['images']:self.assertEqual((folder/'images'/i['file']).read_bytes()[:4],b'\x89PNG')
 def test_three_dimensional_mesh_reports_clear_error(self):
  folder,m=self.run_render(3)
  self.assertIn('3D',m['error']);self.assertEqual(list((folder/'images').glob('*.png')),[])
 def test_missing_output_reports_clear_error(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  subprocess.run([sys.executable,str(ROOT/'scripts/render_results.py'),tmp.name],check=True,capture_output=True)
  self.assertIn('No Exodus output',json.loads((Path(tmp.name)/'images/manifest.json').read_text())['error'])

if __name__=='__main__':unittest.main()
