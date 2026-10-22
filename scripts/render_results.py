#!/usr/bin/env python3
"""Write PNG snapshots of nodal variables from a MOOSE Exodus result at a few times.

Usage: render_results.py RUN_FOLDER. Writes RUN_FOLDER/images/*.png and images/manifest.json.
Shows the solver's visualize list (visualize.json) when given, otherwise a default selection.
Supports 1D and 2D meshes, nodal and element fields. Missing libraries or unsupported meshes are recorded in the manifest
instead of failing the run.
"""
import json, re, sys
from pathlib import Path
MAX_VARIABLES = 6
MAX_REQUESTED = 12
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

def uniform_frame(plt, Triangulation, np, out, name, value, geometry, times, steps):
    first, last = steps[0], steps[-1]
    span = 't = %g' % times[first] if first == last else 't = %g to %g' % (times[first], times[last])
    fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=100)
    if geometry['dim'] == 2:
        x, y = geometry['position'](last)
        ax.tripcolor(Triangulation(x, y, geometry['triangles']), np.zeros(len(x)), cmap='Greys', vmin=-1, vmax=4)
        ax.set_aspect('equal')
    else:
        ax.axhline(value, color='#16775c'); ax.set_ylabel(name); ax.ticklabel_format(axis='y', useOffset=False)
    ax.text(0.5, 0.5, '%s = %g\neverywhere' % (name, value), transform=ax.transAxes, ha='center', va='center', fontsize=15,
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='#16775c'))
    ax.set_title('%s is uniform and unchanged (%s)' % (name, span))
    fig.tight_layout()
    file = '%s_uniform.png' % re.sub(r'[^A-Za-z0-9_.-]', '_', name)
    fig.savefig(out / file); plt.close(fig)
    return {'variable': name, 'time': float(times[first]), 'time_end': float(times[last]), 'step': first, 'file': file, 'uniform': value}

def requested_names(folder):
    # The solver block's visualize list, written next to the run by moose_workspace.py.
    try: return [str(n) for n in json.loads((folder / 'visualize.json').read_text()).get('names', []) if str(n).strip()]
    except (OSError, ValueError): return []

def choose(fields, requested):
    """Requested names in order (exact, case-insensitive, or as a prefix such as cauchy_stress for cauchy_stress_xx)."""
    if not requested:
        order = sorted(fields, key=lambda n: (n.startswith('disp_'), fields[n]['location'] != 'node', fields[n]['order']))
        return order[:MAX_VARIABLES], []
    shown, missing = [], []
    for q in requested:
        matches = [n for n in sorted(fields, key=lambda n: fields[n]['order']) if n == q or n.lower() == q.lower() or n.startswith(q + '_')]
        if matches: shown += [m for m in matches if m not in shown]
        else: missing.append(q)
    return shown[:MAX_REQUESTED], missing

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
    # Nodal fields are drawn smoothly; element fields (stress components, material properties) one value per element.
    fields = {}
    for i, name in enumerate(ex.names('name_nod_var')):
        data = ex.get('vals_nod_var%d' % (i + 1)) if ex.has('vals_nod_var%d' % (i + 1)) else ex.get('vals_nod_var')[:, i, :]
        fields[name] = {'location': 'node', 'values': np.asarray(data, float), 'order': len(fields)}
    triangles, tri_element, centers, block_sizes = [], [], [], []
    block = 1
    while ex.has('connect%d' % block):
        connect = np.asarray(ex.get('connect%d' % block), int) - 1;offset = sum(block_sizes)
        block_sizes.append(len(connect));centers.extend(coords[0][connect].mean(axis=1).tolist())
        if dim == 2:
            local = np.arange(len(connect)) + offset
            if connect.shape[1] in (3, 6, 7): triangles.extend(connect[:, :3].tolist()); tri_element.extend(local.tolist())
            elif connect.shape[1] in (4, 8, 9):
                triangles.extend(np.vstack([connect[:, [0, 1, 2]], connect[:, [0, 2, 3]]]).tolist()); tri_element.extend(np.concatenate([local, local]).tolist())
        block += 1
    if dim == 2 and not triangles: return {'error': 'The Exodus output has no 2D elements to plot.'}
    for v, name in enumerate(ex.names('name_elem_var')):
        parts = []
        for b, size in enumerate(block_sizes):
            key = 'vals_elem_var%deb%d' % (v + 1, b + 1)
            parts.append(np.asarray(ex.get(key), float) if ex.has(key) else np.full((len(times), size), np.nan))
        if parts and name not in fields: fields[name] = {'location': 'element', 'values': np.hstack(parts), 'order': len(fields)}
    if not fields: return {'error': 'The Exodus output has no nodal or element fields to show.'}
    displaced = dim == 2 and 'disp_x' in fields and 'disp_y' in fields and fields['disp_x']['location'] == 'node'
    def position(step):
        if displaced: return coords[0] + fields['disp_x']['values'][step], coords[1] + fields['disp_y']['values'][step]
        return (coords[0], coords[1]) if dim == 2 else (coords[0], None)
    geometry = {'dim': dim, 'triangles': triangles, 'position': position}
    requested = requested_names(folder)
    shown, missing = choose(fields, requested)
    steps = pick_times(len(times))
    out = folder / 'images'; out.mkdir(exist_ok=True)
    for old in out.glob('*.png'): old.unlink()
    images = []
    tri_element = np.asarray(tri_element, int); centers = np.asarray(centers)
    for name in shown:
        field = fields[name]; data = field['values'][steps]
        low, high = float(np.nanmin(data)), float(np.nanmax(data))
        if high - low <= 1e-12 * max(1.0, abs(low), abs(high)):
            # A field that never changes gets one labelled frame instead of a meaningless colour scale.
            images.append(dict(uniform_frame(plt, Triangulation, np, out, name, low, geometry, times, steps), location=field['location']))
            continue
        for step in steps:
            fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=100)
            if dim == 2:
                x, y = position(step); mesh = Triangulation(x, y, triangles)
                if field['location'] == 'node':
                    art = ax.tripcolor(mesh, field['values'][step], shading='gouraud', cmap='viridis', vmin=low, vmax=high)
                else:
                    art = ax.tripcolor(mesh, facecolors=field['values'][step][tri_element], cmap='viridis', vmin=low, vmax=high)
                ax.set_aspect('equal'); bar = fig.colorbar(art, ax=ax, shrink=0.85)
                bar.formatter.set_useOffset(False); bar.update_ticks()
            else:
                if field['location'] == 'node':
                    order = np.argsort(coords[0]); ax.plot(coords[0][order], field['values'][step][order], color='#16775c')
                else:
                    order = np.argsort(centers); ax.plot(centers[order], field['values'][step][order], 'o-', color='#16775c', markersize=3)
                ax.set_ylim(low, high); ax.set_ylabel(name); ax.grid(alpha=0.3); ax.ticklabel_format(axis='y', useOffset=False)
            ax.set_title('%s   t = %g%s%s' % (name, times[step], '   (per element)' if field['location'] == 'element' else '', '   (deformed)' if displaced else ''))
            fig.tight_layout()
            file = '%s_%03d.png' % (re.sub(r'[^A-Za-z0-9_.-]', '_', name), step)
            fig.savefig(out / file); plt.close(fig)
            images.append({'variable': name, 'time': float(times[step]), 'step': step, 'file': file, 'location': field['location']})
    manifest = {'source': candidates[0].name, 'deformed': displaced, 'images': images, 'available': sorted(fields)}
    if requested: manifest.update(requested=requested, missing=missing)
    return manifest

def main():
    folder = Path(sys.argv[1]).resolve()
    try:
        manifest = render(folder)
    except ImportError as e:
        manifest = {'error': 'Result images need numpy and matplotlib, plus netCDF4 or h5py, in the Python that runs them (%s): %s. '
                    'Install them into the conda environment named by render_conda_env (default moose), or point render_conda_prefix '
                    'in config.local.json at an environment that has them.' % (sys.executable, e)}
    except Exception as e:
        manifest = {'error': 'Could not create result images: %s: %s' % (type(e).__name__, e)}
    (folder / 'images').mkdir(exist_ok=True)
    (folder / 'images' / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    print(json.dumps({'images': len(manifest.get('images', [])), 'error': manifest.get('error')}))

if __name__ == '__main__':
    main()
