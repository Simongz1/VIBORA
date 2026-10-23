<p align="center"><img src="web/vibora.svg" width="120" height="120" alt="VIBORA viper logo"></p>

# VIBORA
**Visual Interface for Block-oriented Operator Representation and Assembly**

VIBORA is a block editor for [MOOSE](https://mooseframework.inl.gov) multiphysics models. You draw the model as connected blocks (mesh, variables, materials, kernels, boundary conditions, solver, outputs) and describe the physics in words. An LLM agent turns the graph into a MOOSE input using the objects your MOOSE build actually registers, checks it with `--check-input`, and can run it and show result images. When existing objects are not enough, it proposes custom C++, which is only written after you approve it, and is compiled and numerically tested before it is kept.

It is a buildless HTML/CSS/JavaScript GUI with a small C++17 HTTP server and a Python bridge to the LLM and to MOOSE.

## Quick start (one machine)
You need MOOSE built with conda, CMake, a C++17 compiler, Python 3 and one LLM provider. **[docs/SETUP.md](docs/SETUP.md)** walks through all of it, including installing MOOSE.

```sh
git clone git@github.com:Simongz1/VIBORA.git ~/projects/vibora
cd ~/projects/vibora
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j4
cp config.example.json config.local.json   # then edit the MOOSE paths if they differ
python3 scripts/agent_bridge.py
```

Open http://127.0.0.1:18080, pick a model under **LLM model**, build a graph (or **Open** one, such as a graph you saved earlier) and press **Implement & generate**.

To keep MOOSE on a cluster and the GUI on your laptop, see [Remote MOOSE host](docs/SETUP.md#5-run-vibora).

## Build a model
- The library holds general blocks (MOOSE component, Mesh, Solver, Results) and category shortcuts for Variables, Materials, ICs, BCs, Kernels, AuxVariables, AuxKernels and Postprocessors. The canvas starts empty.
- **Add MOOSE object** accepts any category, an optional registered object type, and physics/method descriptions. Other categories include Functions, UserObjects, Constraints, MultiApps and Transfers. Category suggestions are editable, not an allowlist.
- Newly added blocks are selected and scrolled into view; the canvas expands with the graph.
- Zoom with **− / 100% / +** above the canvas, Ctrl/⌘ + scroll or a trackpad pinch (around the pointer), from 10% to 200%. **Fit** shows every block; opening a saved graph that does not fit zooms out automatically. Zoom only changes the display, not block coordinates.
- The inspector edits category, object type, JSON parameters, descriptions and named typed ports. Connect compatible ports to represent dependencies. Adding a block creates a specification; implementation occurs during generation.
- Describe the complete problem in Model requirements. Save graph/Open round-trip the graph and metadata; browser-local drafts also persist edits.
- **LLM model** selects the provider and model for each new job; existing jobs keep theirs. See [LLM providers](docs/SETUP.md#6-choose-an-llm-provider).

## General MOOSE workflow
**Implement & generate** snapshots the graph and starts an asynchronous job. The agent sees your MOOSE build's object catalog, relevant parameter documentation and retained custom capabilities, so it can use any registered physics module rather than a fixed template. Built-in proposals are checked with the executable's `--check-input`; failures allow bounded repairs. Missing information comes back as questions. A passing input check verifies the setup, not numerical accuracy.

When a request needs custom code, the job explains why and asks for explicit approval; only approval of that exact graph and proposal starts coding. Generated C++ is staged in an isolated copy of `moose_app/`, built (through Slurm when enabled, otherwise on the MOOSE host) and tested against numerical CSV assertions, including retained regression cases. Only passing implementations are copied into `moose_app/` and recorded under `capabilities/`, becoming context for future jobs. New files are committed and, if the checkout has a remote, rebased onto the latest `origin/<branch>` and pushed; the job log reports the outcome, and conflicts or uncommitted changes leave the commit local with the reason. Review generated numerical assertions: passing them is not proof that an arbitrary physical model is correct.

Runtime custom sources currently support kernels, materials, BCs, AuxKernels, functions, user objects, postprocessors and ICs; the GUI can describe other installed object categories as well.

## Agent activity and simulation runs
The job dialog's **Agent activity** log shows each step as it happens: catalog loading, every model call (purpose, prompt size, duration, tokens and a summary of the answer), MOOSE input checks with the first error line, builds, test results and repairs. A note appears when a step has been running for a while.

When a job is ready, the dialog shows **What will run** (mesh size, resolution and constitutive model, read from the generated input); raw validation output is folded into **Technical details**, which opens by itself when something fails.

**Run simulation** runs only that validated input:
- **This machine** starts it at once on the MOOSE host (a workstation, or a cluster login node), within `local_runs` limits (default 4 MPI ranks, 1 hour). State lives in files in the run folder, so status checks work from any login node; a run whose heartbeat stops for 90 s is reported as failed.
- **Compute node (Slurm)** submits it with `sbatch` when `scheduler.enabled` is true, using the configured account, partition, QoS, memory and GPUs.

MOOSE writes CSV and Exodus output in `.vibora/jobs/<id>/run/`. Runs can be cancelled, and monitoring resumes if the bridge restarts. A finished run only means MOOSE exited cleanly; check convergence and results yourself.

After a run, `scripts/render_results.py` saves PNG snapshots of up to 4 times into `run/images/`, on the deformed mesh when `disp_x`/`disp_y` exist and with one colour scale per variable, and the dialog shows them as a gallery. Set **Visualize** on the solver block (space-separated names such as `cauchy_stress_xx temperature vonmises_cauchy_stress`) to choose what is shown: it is a VIBORA setting, never written into the input, and the agent makes each quantity appear in the Exodus output. A name also matches its components (`cauchy_stress` shows `cauchy_stress_xx`, `_yy`, …); up to 12 fields are shown, and names missing from the output are listed with what is available. Element fields such as stress components are drawn one value per element; fields that never change get one labelled frame. Without a list, up to 6 fields are chosen automatically. Images support 1D and 2D meshes and run in the `moose` conda environment (see [Result images](docs/SETUP.md#7-result-images)).

## Model token use
- **Usage per call.** Each model call in the activity log shows the tokens the provider reported, and the job dialog shows the job's running total. Running simulations never calls a model.
- **Smaller prompts.** Object selection gets the 150 best keyword matches instead of every registered object name, and may still name any registered object exactly. Planning gets parameter documentation without C++ source or boilerplate parameters. Question reviews and repairs send only the graph evidence, the plan's objects, the previous plan and trimmed MOOSE output.
- **Output-only edits.** If only the Results blocks or the solver's **Visualize** list changed since an earlier ready job, that input is edited instead of regenerated: unchanged with no model calls when the quantities are already written, otherwise with one small prompt. Either way it passes `--check-input`.
- **Reuse.** If the requirements, blocks and connections match an earlier ready job (canvas positions do not count), its input is reused after a fresh `--check-input`, with no model calls. **Regenerate anyway** forces a new generation.

## Architecture and verification
- `web/`: buildless GUI, editor, model picker and asynchronous job, approval and run views.
- `backend/`: C++ HTTP server, catalog, workflow proxy and result-image route. Bounded worker pool and request limits.
- `scripts/agent_bridge.py`: starts the GUI server (locally or on a remote host over SSH) and serves model calls.
- `scripts/workflow_engine.py`: provider adapters, object discovery, planning, approval, repairs and job orchestration.
- `scripts/moose_workspace.py`: catalog lookup, MOOSE validation, isolated builds/tests, runs and capability retention.
- `scripts/render_results.py`: result images from Exodus output.
- `moose_app/`: cumulative custom C++ application (`ViboraPhysicsApp`): framework, all modules and an optional base application.
- `tests/`: backend, workflow, image and git-sync tests (`ctest --test-dir build`); `submit_build_fixture.py` builds an isolated analytic Poisson fixture without retaining it.

The deterministic graph checker checks graph structure; it is not a general proof of physical consistency or dimensional correctness. Cyclic physical coupling is allowed. The legacy `/api/generate`, `/api/validate` and `--generate` remain diffusion-specific; the GUI uses `/api/jobs/*` and `/api/graph/check` for general models. MOOSE itself is not vendored. CMake downloads checksum-pinned cpp-httplib and nlohmann/json headers; their licenses are in `third_party/`.

## License
VIBORA is released under the [MIT License](LICENSE), copyright (c) 2026 Simon Gonzalez. Exceptions:
- `moose_app/include/base/ViboraPhysicsApp.h` and `moose_app/Makefile` are adapted from MOOSE's application template and remain under MOOSE's [LGPL-2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html) license.
- The downloaded headers in `third_party/` (cpp-httplib, nlohmann/json) are MIT-licensed by their authors; see `third_party/*.LICENSE`.

VIBORA links against MOOSE, which is licensed separately under LGPL-2.1 and is not included in this repository.
