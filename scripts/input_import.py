"""Turn a MOOSE input file (HIT syntax) into a VIBORA block graph, without a model call.

Each object block becomes a block in its category; [Mesh], [Executioner] and [Outputs] become the
Mesh, Solver and Results blocks. A parameter that names another object (variable, function,
material property, postprocessor, user object, mesh generator) becomes a connection on a port
named after that parameter. Comments above a block become its physics description.
"""
import re, uuid

# Column order of the layout: roughly how a model flows from geometry to outputs.
COLUMNS = [('Mesh',), ('Variables', 'AuxVariables', 'GlobalParams'), ('Functions', 'ICs'), ('Materials',),
           ('Physics', 'Modules', 'Kernels', 'AuxKernels', 'BCs', 'Constraints', 'InterfaceKernels', 'DGKernels',
            'ScalarKernels', 'AuxScalarKernels', 'NodalKernels', 'Dampers'),
           ('Postprocessors', 'VectorPostprocessors', 'UserObjects', 'Reporters', 'Controls'),
           ('Executioner', 'Preconditioning', 'Problem', 'Adaptivity', 'MultiApps', 'Transfers'), ('Outputs',)]
PROVIDES = ('Variables', 'AuxVariables', 'Functions', 'Postprocessors', 'VectorPostprocessors', 'UserObjects', 'Reporters', 'Mesh')

def strip_comment(line):
    # A '#' starts a comment unless it is inside quotes.
    quote = None
    for i, ch in enumerate(line):
        if ch in '\'"' and quote in (None, ch): quote = None if quote else ch
        elif ch == '#' and not quote: return line[:i].rstrip()
    return line

def parse(text):
    """Nested blocks: {'name', 'params' (ordered), 'children', 'comment'}; top-level variables are substituted."""
    root = {'name': '', 'params': {}, 'children': [], 'comment': ''}
    stack, comments, header, variables = [root], [], [], {}
    lines = text.splitlines(); i = 0
    while i < len(lines):
        raw = lines[i]; i += 1
        stripped = raw.strip()
        if stripped.startswith('#'):
            comments.append(stripped.lstrip('#').strip())
            if len(stack) == 1 and not root['children'] and not root['params']: header.append(comments[-1])
            continue
        line = strip_comment(stripped)
        if not line: comments = []; continue
        m = re.fullmatch(r'\[\s*(?:\./)?([^\]\s]*)\s*\]', line)
        if m:
            name = m.group(1).rstrip('/')
            if name in ('', '..'):
                if len(stack) > 1: stack.pop()
            else:
                block = stack[-1]
                for part in [p for p in name.split('/') if p][:-1]:
                    child = next((c for c in block['children'] if c['name'] == part), None)
                    if child is None:
                        child = {'name': part, 'params': {}, 'children': [], 'comment': ''}; block['children'].append(child)
                    block = child
                node = {'name': name.split('/')[-1], 'params': {}, 'children': [], 'comment': ' '.join(c for c in comments if c)}
                block['children'].append(node); stack.append(node)
            comments = []; continue
        m = re.match(r'([A-Za-z_][\w:/.-]*)\s*=\s*(.*)', line)
        if not m: comments = []; continue
        key, value = m.group(1), m.group(2).strip()
        # A quoted value may continue over several lines.
        while value[:1] in "'\"" and value.count(value[0]) % 2 and i < len(lines):
            value += ' ' + lines[i].strip(); i += 1
        value = value.strip().strip('\'"').strip()
        if len(stack) == 1: variables[key] = value
        else: stack[-1]['params'][key] = value
        comments = []
    def substitute(block):
        for k, v in block['params'].items():
            block['params'][k] = re.sub(r'\$\{([A-Za-z_]\w*)\}', lambda m: variables.get(m.group(1), m.group(0)), v)
        for c in block['children']: substitute(c)
    substitute(root)
    return root, header, variables

def leaves(block, path=()):
    """Object blocks as (path, block). A block with parameters, without sub-blocks, or a variable, is an object;
    a block holding only sub-blocks (like [Kernels]) is just a container. Sub-blocks are always visited."""
    for child in block['children']:
        here = path + (child['name'],)
        # Every block directly under [Variables]/[AuxVariables] is a variable, even with default settings.
        variable = len(here) == 2 and here[0] in ('Variables', 'AuxVariables')
        if child['params'] or not child['children'] or variable: yield here, child
        if child['children']: yield from leaves(child, here)

def column(category):
    top = category.split('/')[0]
    return next((i for i, names in enumerate(COLUMNS) if top in names), 6)

def number(value):
    try: return int(value) if re.fullmatch(r'[-+]?\d+', value) else float(value) if re.fullmatch(r'[-+0-9.eE]+', value) else value
    except ValueError: return value

def to_graph(text, name='model.i'):
    root, header, variables = parse(text)
    nodes, objects = [], []
    for path, block in leaves(root):
        category = '/'.join(path[:-1]) or path[0]
        params = {k: number(v) for k, v in block['params'].items()}
        top = path[0]
        if top == 'Mesh' and len(path) == 1: kind = 'mesh'
        elif top == 'Executioner' and len(path) == 1: kind = 'solver'
        elif top == 'Outputs' and len(path) == 1: kind = 'output'
        else: kind = 'component'
        node = {'id': 'b_' + uuid.uuid4().hex, 'kind': kind, 'label': path[-1] if len(path) > 1 else top, 'params': params,
                'physics': block['comment'], 'method': '', 'implementation': '', 'inputs': [], 'outputs': []}
        if kind == 'component':
            node['category'] = category
            node['object_type'] = str(params.pop('type', ''))
        nodes.append(node); objects.append((path, block, node))
    # Names other blocks can refer to, and the block that provides each.
    provided = {}
    for path, block, node in objects:
        top = path[0]
        if top in PROVIDES and len(path) > 1: provided.setdefault(path[-1], node)
        for key in ('prop_names', 'property_name', 'f_name', 'base_name'):
            for token in str(block['params'].get(key, '')).split(): provided.setdefault(token, node)
    edges = []
    def connect(source, target, out, port):
        if source is target: return
        if not any(p['name'] == out for p in source['outputs']): source['outputs'].append({'name': out, 'type': 'object'})
        if not any(p['name'] == port for p in target['inputs']): target['inputs'].append({'name': port, 'type': 'object'})
        edge = {'from': source['id'], 'out': out, 'to': target['id'], 'in': port}
        if edge not in edges: edges.append(edge)
    for path, block, node in objects:
        for key, value in block['params'].items():
            if key in ('type', 'prop_names', 'prop_values', 'property_name', 'f_name', 'base_name'): continue
            for token in re.split(r"[\s,;]+", str(value)):
                if token in provided: connect(provided[token], node, 'object', key)
    # Structural links that make the diagram read like a model: mesh -> variables, solver -> outputs.
    mesh = next((n for n in nodes if n['kind'] == 'mesh'), None); solver = next((n for n in nodes if n['kind'] == 'solver'), None)
    for path, block, node in objects:
        if mesh and path[0] in ('Variables', 'AuxVariables') and len(path) > 1: connect(mesh, node, 'mesh', 'mesh')
        if solver and path[0] == 'Outputs': connect(solver, node, 'solution', 'solution')
    # Layout in columns by role; columns this model does not use take no space.
    used = sorted({column(node.get('category') or path[0]) for path, block, node in objects})
    rows = {}
    for path, block, node in objects:
        c = column(node.get('category') or path[0]); r = rows.get(c, 0); rows[c] = r + 1
        node['x'], node['y'] = 50 + used.index(c) * 250, 60 + r * 150
    request = ' '.join(h for h in header if h)
    if variables: request += (' ' if request else '') + 'Input parameters: ' + ', '.join(k + ' = ' + v for k, v in variables.items()) + '.'
    title = re.sub(r'\.i$', '', name.rsplit('/', 1)[-1]) or 'Imported model'
    return {'version': 2, 'title': title, 'request': request.strip(), 'nodes': nodes, 'edges': edges,
            'imported_from': name.rsplit('/', 1)[-1]}
