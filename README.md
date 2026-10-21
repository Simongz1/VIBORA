# VIBORA
**Visual Interface for Block-oriented Operator Representation and Assembly**

A block editor for assembling a MOOSE steady diffusion model, with an HTML/CSS/JavaScript frontend and C++17 backend.

## Start on Gilbreth
From your laptop:
```sh
ssh -L 18080:127.0.0.1:18080 gonz1075@gilbreth.rcac.purdue.edu
```
In that SSH session:
```sh
cd /depot/aamp/data/gonz1075/vibora
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/vibora 18080 web
```
Keep the session open and visit http://127.0.0.1:18080 on your laptop. The server binds only to loopback. First configure downloads checksum-pinned cpp-httplib 0.18.3 and nlohmann/json 3.11.3 headers; subsequent builds reuse them. MIT licenses are included in third_party/. Requires CMake 3.16+, C++17, pthreads, and Python 3 for tests. Run MOOSE simulations in an appropriate scheduler allocation, not on a login node.

## Use
The example contains a 20×20 unit-square mesh, first-order Lagrange field u, unit-coefficient Diffusion kernel, u=0 on the left and u=1 on the right, a Steady PJFNK solver, and Exodus output. Other sides use natural zero flux. Expected solution: u=x.

- Drag block headers to arrange the graph.
- Click an output then a compatible input to connect.
- Click wires or inspector connection entries to remove connections.
- Add blocks from the library; select a block to edit its parameters and physics/method/implementation notes.
- Create custom block makes a named instance of a supported MOOSE role.
- Save graph/Open export and import portable JSON. Edits are not automatically persisted.
- Dependency checks run after edits. Generate MOOSE input validates first, then offers a downloadable diffusion.i.

Headless generation:
```sh
./build/vibora --generate < model.json > diffusion.i
```
With a compiled MOOSE application registering the built-in objects:
```sh
/path/to/moose-app-opt -i diffusion.i --check-input
/path/to/moose-app-opt -i diffusion.i
```
The existing moose/ checkout is preserved and excluded from this repository. No executable was found at moose/test/moose_test-opt during setup: an actual MOOSE parse/solve remains unverified. Input structure follows moose/test/tests/kernels/simple_diffusion/simple_diffusion.i at MOOSE commit 2c9d7a5e570501e440acc6faefb2a2866e897df6.

## Architecture
- web/: buildless editor, typed ports, import/export, input preview.
- backend/main.cpp: catalog, dependency validation, MOOSE input generation.
- GET /api/catalog; POST /api/validate; POST /api/generate.
- tests/test_backend.py: 11 integration tests for generation, invalid connections, boundary conflicts, malformed parameters, injection rejection, static serving, and CLI/API equivalence.

Dependency checking and coding roles currently use deterministic validation and input generation, not LLM agents. No API credentials, autonomous code execution, or simulation submission is configured. Future agents can wrap these components while keeping validation as a gate.

Custom metadata is descriptive, not executable. Supported roles: mesh, variable, diffusion, Dirichlet boundary, steady solver, output. The prototype requires one mesh, field, diffusion operator, solver, output, and at least one boundary. Generated meshes support 1D/2D. Edges are assembly dependencies, not physical transport or arbitrary coupled equations. Multiphysics, cyclic physical coupling, transients, variable coefficients, units checking, custom kernels, and multi-fidelity execution are future work.

The backend has a bounded four-worker pool, 1 MB request limit, and limits of 500 blocks/2000 edges. Dependency traversal is linear in graph size. This is a small-model prototype, not a benchmarked large-model engine.
