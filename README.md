# VIBORA
**Visual Interface for Block-oriented Operator Representation and Assembly**

A block editor for assembling steady or transient MOOSE diffusion models, with an HTML/CSS/JavaScript frontend and C++17 backend.

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
- Save graph/Open export and import portable JSON. The new interface saves a browser-local draft; export a JSON file for portable backups.
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
The existing moose/ checkout is preserved and excluded from this repository. Installed executables are available at /depot/aamp/data/gonz1075/moose/moose/test/moose_test-opt and /depot/aamp/data/gonz1075/moose/ml/ml-opt (the user-provided MARLINS build). The GUI does not launch these executables. The description-generated transient input passed MOOSE --check-input; a full solve remains unverified. Input structure follows moose/test/tests/kernels/simple_diffusion/simple_diffusion.i at MOOSE commit 2c9d7a5e570501e440acc6faefb2a2866e897df6.

## Architecture
- web/: buildless editor, typed ports, import/export, input preview.
- backend/main.cpp: catalog, dependency validation, MOOSE input generation.
- GET /api/catalog; POST /api/validate; POST /api/generate.
- tests/test_backend.py: 19 integration tests for generation, invalid connections, boundary conflicts, malformed parameters, injection rejection, static serving, and CLI/API equivalence.

Block physics, numerical method, and implementation requirements are now passed to a real Codex coding agent. It proposes typed parameter changes with reasons. The C++ backend allowlists and validates those changes, then generates MOOSE input. Agent text is never executed as code. The separate dependency checker remains deterministic.
The agent uses the laptop's existing Codex login through a loopback service and SSH reverse tunnel. Model requests consume that account's Codex usage. No API key is placed on Gilbreth. An unavailable agent is an explicit error when descriptions need interpretation.

Descriptions are executable intent within the supported catalog. Supported roles: mesh, variable, diffusion, Dirichlet boundary, steady solver, output. The prototype requires one mesh, field, diffusion operator, solver, output, and at least one boundary. Generated meshes support 1D/2D. Edges are assembly dependencies, not physical transport or arbitrary coupled equations. Multiphysics, cyclic physical coupling, variable coefficients, units checking, custom kernels, and multi-fidelity execution are future work.

The backend has a bounded four-worker pool, 1 MB request limit, and limits of 500 blocks/2000 edges. Dependency traversal is linear in graph size. This is a small-model prototype, not a benchmarked large-model engine.

## GUI typography and solid mechanics
The interface uses Tahoma, with Arial and generic sans-serif fallbacks when Tahoma is unavailable. All VIBORA HTML, CSS, JavaScript, C++ source, build configuration, and tests are tracked in this repository. Third-party headers are downloaded with pinned checksums by CMake.

The executable block catalog supports steady and transient diffusion. Solid-mechanics blocks and their MOOSE/MARLINS mappings must be added before a mechanics assembly can generate a runnable input.

## Description-driven coding agent
On your laptop, sign in with the Codex CLI (codex login), then start both the bridge
and the remote backend using the source stored on Gilbreth:
```sh
ssh gonz1075@gilbreth.rcac.purdue.edu 'cat /depot/aamp/data/gonz1075/vibora/scripts/agent_bridge.py' | python3 -u - --ssh-host gonz1075@gilbreth.rcac.purdue.edu
```
Stop an older VIBORA server/tunnel first, or choose --gui-port 18090 --port 18093.
Keep this command running while using the GUI. It authenticates the agent bridge
with an ephemeral token carried over SSH stdin. Codex runs in a temporary read-only
workspace with shell, apps, browser, and computer tools disabled. Stop with Ctrl-C.
The earlier manual startup remains useful for explicit parameters without descriptions.

Example solver description:
> Transient diffusion with backward Euler, dt = 0.1, end time = 1. Initial u = 0 everywhere.

Click **Implement & generate**. The agent resolves descriptions across the graph;
the compiler adds TimeDerivative for transient diffusion and emits the executioner,
time settings and initial condition. The preview shows every parameter change and
its reason. Apply settings to blocks updates the editor; Save resolved graph exports
the implemented configuration. Input download contains the implementation, not merely
the old template. Changing descriptions invalidates old output. New-version edits
are also saved as a browser-local draft; still use Save graph for portable backups.

Explicit descriptions override old parameters and generic default labels. Conflicting
descriptions or unsupported physics produce unresolved questions instead of an input.
Missing transient dt, end_time/num_steps, or initial_condition blocks generation.
An empty-description graph can still compile directly from structured parameters.
Time schemes: implicit-euler, bdf2, crank-nicolson. Transient mode adds accumulation
for scalar diffusion; this is not a generic rule for arbitrary future physics.

Validation: 19 automated backend integration tests, a live Codex description-to-input
test, and the installed MOOSE executable accepted the generated transient case with
--check-input (Syntax OK). This verifies input syntax/setup, not solution accuracy.
