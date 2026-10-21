# VIBORA
**Visual Interface for Block-oriented Operator Representation and Assembly**

HTML/CSS/JavaScript block editor with a C++17 HTTP backend and a Python model/workspace bridge. Tahoma typography. Source lives at `/depot/aamp/data/gonz1075/vibora` on Gilbreth.

## Build and start
On Gilbreth:
```sh
cd /depot/aamp/data/gonz1075/vibora
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
```
CMake downloads checksum-pinned cpp-httplib and nlohmann/json headers; licenses are in third_party/.

From your laptop, with Python 3, SSH access and an authenticated Codex CLI:
```sh
ssh gonz1075@gilbreth.rcac.purdue.edu 'cat /depot/aamp/data/gonz1075/vibora/scripts/agent_bridge.py' | python3 -u - --ssh-host gonz1075@gilbreth.rcac.purdue.edu
```
Keep this command running and open http://127.0.0.1:18080. Stop an older server/tunnel first, or select `--gui-port 19081 --port 19084`. The bridge creates authenticated loopback forward/reverse SSH tunnels; no API key is stored on Gilbreth.

## Build a model
- Use category shortcuts for Materials, ICs, BCs, Postprocessors, Kernels, AuxVariables and AuxKernels.
- **Add MOOSE object** accepts any category, an optional registered object type, and physics/method descriptions. Other categories include Functions, UserObjects, Constraints, MultiApps and Transfers. Category suggestions are editable, not an allowlist.
- Newly added blocks are selected and scrolled into view; the canvas expands with the graph.
- The inspector edits category, object type, JSON parameters, descriptions and named typed ports. Connect compatible ports to represent dependencies. Adding a block creates a specification; implementation occurs during generation.
- Describe the complete problem in Model requirements. Save graph/Open round-trip the graph and metadata; browser-local drafts also persist edits.
- **LLM model** selects the provider/model for each new job. Existing jobs retain their selection. Codex uses the laptop login and usage allowance. **Claude Code** (opus, sonnet, haiku) uses a Claude Pro/Max/Team/Enterprise subscription through the Claude Code CLI: run `claude auth login` once on the laptop, and pass `--claude PATH` to the bridge if `claude` is not on its PATH. It runs with all tools, MCP servers and session saving disabled. The Claude API (default `claude-opus-5-5`; also Sonnet 5.5, Haiku 5.5 and Fable 5.1 when the key has access) needs `pip3 install --user anthropic` and `ANTHROPIC_API_KEY` exported in the laptop shell that starts the bridge; it is billed to that API key and the key never leaves the laptop. Ollama and OpenAI-compatible local endpoints are discovered at `VIBORA_OLLAMA_URL` (default localhost:11434) and `VIBORA_LOCAL_URL` (default localhost:8000/v1). A model server must already be running; the picker does not install models. Local servers must support structured JSON responses.

## General MOOSE workflow
**Implement & generate** snapshots the graph and starts an asynchronous job. The agent sees the installed MARLINS/MOOSE object catalog, relevant parameter documentation and retained custom source. It can generate input across registered physics modules, rather than a fixed diffusion template. Built-in proposals are checked with the installed executable's `--check-input`; failures allow bounded repairs. Missing information is returned as questions. Successful input checks verify setup, not numerical accuracy.

When a request requires custom code, the job presents the reason and asks for explicit approval. Only approval of that exact graph/proposal starts coding. Generated C++ files are staged in an isolated application, built through Slurm, and tested against numerical CSV assertions, including retained regression cases. Only passing implementations are copied into `moose_app/` and recorded under `capabilities/`, becoming context for future jobs. New files are committed; push failures are reported as synchronization pending. Review generated numerical assertions: passing them is not proof that an arbitrary physical model is correct.

`config.example.json` defines installed paths and scheduler/toolchain defaults; override locally in ignored `config.local.json`. The custom application extends the installed MARLINS application and registers `ViboraPhysicsApp` objects. Jobs/logs/caches live in ignored `.vibora/`. Compute builds and solves run in scheduler allocations. Runtime custom sources currently support kernels, materials, BCs, AuxKernels, functions, user objects, postprocessors and ICs; the GUI can describe other installed object categories as well.

## Architecture and verification
- `web/`: buildless GUI, editor, model picker and asynchronous job/approval views.
- `backend/`: C++ HTTP server, catalog and workflow proxy. Bounded worker pool and request limits.
- `scripts/workflow_engine.py`: provider adapters, object discovery, planning, approval, repairs and job orchestration.
- `scripts/moose_workspace.py`: catalog lookup, MOOSE validation, isolated builds/tests and capability retention.
- `moose_app/`: cumulative custom C++ application scaffold.
- `tests/`: 19 legacy backend checks and 17 workflow/approval tests; `submit_build_fixture.py` submits an isolated analytic Poisson fixture without retaining it.

The deterministic graph checker checks graph structure; it is not a general proof of physical consistency or dimensional correctness. Cyclic physical coupling is allowed. The legacy `/api/generate`, `/api/validate` and `--generate` remain diffusion-specific; the GUI uses `/api/jobs/*` and `/api/graph/check` for general models. The existing `moose/` checkout and installed MOOSE/MARLINS builds are not vendored.
