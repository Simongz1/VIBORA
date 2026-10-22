#!/usr/bin/env python3
"""Write PNG snapshots of nodal variables from a MOOSE Exodus result at a few times.

Usage: render_results.py RUN_FOLDER. Writes RUN_FOLDER/images/*.png and images/manifest.json.
Supports 1D and 2D meshes. Missing libraries or unsupported meshes are recorded in the manifest
instead of failing the run.
"""
import json, re, sys
from pathlib import Path
MAX_VARIABLES = 6
MAX_TIMES = 4

class Exodus:
    """Reads the netCDF variables of an Exodus file with netCDF4, h5py or scipy."""
    def __init__(self, path):
        with open(path, 'rb') as f: head = f.read(4)
        if head.startswith(b'\x89HDF'):
            try:
                import netCDF4
                self.file = netCDF4.Dataset(str(path)); self.file.set_auto_mask(False)
                self.get = lambda name: self.file.variables[name][:]
                self.has = lambda name: name in self.file.variables
            except ImportError:
                import h5py
                self.file = h5py.File(str(path), 'r')
                self.get = lambda name: self.file[name][()]
                self.has = lambda name: name in self.file
        else:
            from scipy.io import netcdf_file
            self.file = netcdf_file(str(path), 'r', mmap=False)
            self.get = lambda name: self.file.variables[name][:].copy()
            self.has = lambda name: name in self.file.variables
    def names(self, variable):
        if not self.has(variable): return []
        rows = self.get(variable)
        return [b''.join(x if isinstance(x, bytes) else bytes(x) for x in row).decode(errors='replace').strip('\x00 ') for row in rows]

def pick_times(count):
    if count <= MAX_TIMES: return list(range(count))
    return sorted({round(i * (count - 1) / (MAX_TIMES - 1)) for i in range(MAX_TIMES)})

def render(folder):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation
    candidates = sorted(folder.glob('*.e'), key=lambda f: (f.name != 'model_out.e', f.name))
    if not candidates: return {'error': 'No Exodus output (*.e) was written, so there is nothing to show.'}
    ex = Exodus(candidates[0])
    coords = [np.asarray(ex.get(c), float) for c in ('coordx', 'coordy', 'coordz') if ex.has(c)]
    if not coords and ex.has('coord'): coords = [np.asarray(row, float) for row in ex.get('coord')]
    while len(coords) > 1 and not np.any(coords[-1]): coords.pop()
    dim = len(coords)
    if dim not in (1, 2): return {'error': 'Result images support 1D and 2D meshes; this mesh is %dD.' % dim}
    times = np.asarray(ex.get('time_whole'), float) if ex.has('time_whole') else np.zeros(1)
    names = ex.names('name_nod_var')
    def nodal(i):
        if ex.has('vals_nod_var%d' % (i + 1)): return np.asarray(ex.get('vals_nod_var%d' % (i + 1)), float)
        return np.asarray(ex.get('vals_nod_var'), float)[:, i, :]
    values = {name: nodal(i) for i, name in enumerate(names)}
    if not values: return {'error': 'The Exodus output has no nodal variables to show.'}
    displaced = dim == 2 and 'disp_x' in values and 'disp_y' in values
    shown = sorted(values, key=lambda n: (n.startswith('disp_'), names.index(n)))[:MAX_VARIABLES]
    steps = pick_times(len(times))
    triangles = []
    block = 1
    while ex.has('connect%d' % block):
        connect = np.asarray(ex.get('connect%d' % block), int) - 1
        if dim == 2:
            if connect.shape[1] in (3, 6, 7): triangles.extend(connect[:, :3].tolist())
            elif connect.shape[1] in (4, 8, 9): triangles.extend(np.vstack([connect[:, [0, 1, 2]], connect[:, [0, 2, 3]]]).tolist())
        block += 1
    if dim == 2 and not triangles: return {'error': 'The Exodus output has no 2D elements to plot.'}
    out = folder / 'images'; out.mkdir(exist_ok=True)
    for old in out.glob('*.png'): old.unlink()
    images = []
    for name in shown:
        data = values[name][steps]
        low, high = float(np.nanmin(data)), float(np.nanmax(data))
        if high <= low: high = low + (abs(low) or 1) * 1e-9
        for step in steps:
            fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=100)
            if dim == 2:
                x, y = coords[0], coords[1]
                if displaced: x, y = x + values['disp_x'][step], y + values['disp_y'][step]
                mesh = Triangulation(x, y, triangles)
                art = ax.tripcolor(mesh, values[name][step], shading='gouraud', cmap='viridis', vmin=low, vmax=high)
                ax.set_aspect('equal'); fig.colorbar(art, ax=ax, shrink=0.85)
            else:
                order = np.argsort(coords[0])
                ax.plot(coords[0][order], values[name][step][order], color='#16775c')
                ax.set_ylim(low, high); ax.set_ylabel(name); ax.grid(alpha=0.3)
            ax.set_title('%s   t = %g%s' % (name, times[step], '   (deformed)' if displaced else ''))
            fig.tight_layout()
            file = '%s_%03d.png' % (re.sub(r'[^A-Za-z0-9_.-]', '_', name), step)
            fig.savefig(out / file); plt.close(fig)
            images.append({'variable': name, 'time': float(times[step]), 'step': step, 'file': file})
    return {'source': candidates[0].name, 'deformed': displaced, 'images': images}

def main():
    folder = Path(sys.argv[1]).resolve()
    try:
        manifest = render(folder)
    except ImportError as e:
        manifest = {'error': 'Result images need numpy and matplotlib, plus netCDF4 or h5py, in the Python that runs them (%s): %s. '
                    'Install with "python3 -m pip install --user numpy matplotlib netCDF4", or set render_python in config.local.json.' % (sys.executable, e)}
    except Exception as e:
        manifest = {'error': 'Could not create result images: %s: %s' % (type(e).__name__, e)}
    (folder / 'images').mkdir(exist_ok=True)
    (folder / 'images' / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(json.dumps({'images': len(manifest.get('images', [])), 'error': manifest.get('error')}))

if __name__ == '__main__':
    main()
