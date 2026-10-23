# Setting up VIBORA

This guide takes you from nothing to a running VIBORA: install MOOSE, build VIBORA, point it at your MOOSE build, start it, and connect an LLM.

## 1. What runs where
VIBORA has three parts:

| Part | What it does | Where it runs |
|---|---|---|
| **GUI** | The block editor in your browser | Your browser, at http://127.0.0.1:18080 |
| **Bridge** (`scripts/agent_bridge.py`) | Calls the LLM and runs the job workflow | The machine where your LLM sign-ins and API keys live |
| **MOOSE host** | MOOSE, the GUI server (`build/vibora`), job files, builds and runs (`scripts/moose_workspace.py`) | The machine with MOOSE: the same computer, or a cluster reached over SSH |

There are two ways to run it:
- **One machine.** MOOSE, VIBORA and the bridge are all on your workstation. This is the simplest.
- **Remote MOOSE host.** MOOSE and VIBORA live on a cluster; you start the bridge on your laptop. It tunnels the GUI to your browser over SSH, and your LLM keys never leave the laptop.

## 2. Install MOOSE
These steps follow MOOSE's [conda installation guide](https://mooseframework.inl.gov/getting_started/installation/conda.html); check it for the current details.

**Install Miniforge** (pick the installer for your system: `Linux-x86_64`, `MacOSX-arm64` or `MacOSX-x86_64`):
```sh
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge
export PATH=$HOME/miniforge/bin:$PATH
conda init --all
```
Close and reopen the terminal.

**Create the MOOSE environment.** Add INL's channel, then create an environment named `moose`. Use the `moose-dev` version shown in MOOSE's guide:
```sh
conda config --add channels https://conda.software.inl.gov/public
conda create -n moose moose-dev=<version from the MOOSE guide>
conda activate moose
```

**Clone and build MOOSE.** MOOSE recommends `~/projects`:
```sh
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/idaholab/moose.git
cd moose && git checkout master
cd test && make -j 6 && ./run_tests -j 6
```

**Build an application with all physics modules.** VIBORA needs an executable that registers the objects you want to use. The combined application includes every module:
```sh
cd ~/projects/moose/modules/combined
make -j 6
ls combined-opt
```

On a cluster you can also use a MOOSE build or application that already exists there; just point `moose_dir` and `moose_executable` at it (section 4).

## 3. Get and build VIBORA
Requirements: CMake 3.16 or newer, a C++17 compiler, Python 3.9 or newer, `git` and `ssh`. The `moose` environment provides suitable compilers.

```sh
cd ~/projects
git clone git@github.com:Simongz1/VIBORA.git vibora
cd vibora
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4
ctest --test-dir build --output-on-failure
```
CMake downloads two checksum-pinned header libraries (cpp-httplib, nlohmann/json) the first time.

The recommended layout:
```
~/projects/
  moose/                                MOOSE checkout                 -> moose_dir
    modules/combined/combined-opt       MOOSE executable               -> moose_executable
  vibora/                               this repository (on the MOOSE host)
    config.local.json                   your settings (not committed)
    build/vibora                        GUI server
    moose_app/                          ViboraPhysicsApp, where approved custom objects go
    capabilities/                       verified custom capabilities (created on first use)
    .vibora/                            jobs, logs, catalog cache and run results (not committed)
```

## 4. Configure
Copy the example and edit it. `config.local.json` is ignored by git, and its top-level keys override `config.example.json`:
```sh
cp config.example.json config.local.json
```

| Key | Meaning |
|---|---|
| `moose_dir` | MOOSE checkout, used to build `ViboraPhysicsApp`. `~` is allowed. |
| `moose_executable` | MOOSE application whose object catalog the agent uses and that runs your models, e.g. `~/projects/moose/modules/combined/combined-opt`. After a custom capability is approved and verified, VIBORA switches to its own `vibora_physics-opt`. |
| `application_description` | One line telling the agent what that executable contains. |
| `base_app` | Optional existing MOOSE application to extend, e.g. your group's app: `class` (e.g. `MyApp`, with header `MyApp.h`), `dir` (its source tree, with `include/base` and `lib/`) and `library` (stem of `lib/lib<stem>-opt.la`). Leave `class` empty to extend the framework and modules only. |
| `toolchain_bin` | Extra folders put first on `PATH` for builds and runs, e.g. a cluster's MPI `bin`. Usually empty inside the `moose` environment. |
| `scheduler.enabled` | `true` to build custom code and run "Compute node" simulations through Slurm; `false` (default) to build on the MOOSE host and offer only "This machine" runs. |
| `scheduler.account`, `partition`, `qos`, `memory`, `gpus` | Slurm settings; empty values and `gpus: 0` are left out of `sbatch`. |
| `scheduler.extra_args` | Any other `sbatch` options, e.g. `["--constraint=intel"]`. |
| `scheduler.time`, `cpus` | Wall time and CPUs for custom-code build and test jobs. |
| `scheduler.run_ranks`, `run_time` | Defaults for "Compute node" simulation runs. |
| `local_runs.max_ranks`, `max_time`, `default_time` | Limits and default for "This machine" runs (default 4 ranks, 01:00:00, 00:10:00). Keep them small on shared login nodes. |
| `render_conda_env`, `render_conda_prefix`, `render_python` | Python used for result images (section 7). |

Example for a Slurm cluster:
```json
{
  "moose_dir": "/path/to/moose",
  "moose_executable": "/path/to/moose/modules/combined/combined-opt",
  "scheduler": {"enabled": true, "account": "myproject", "partition": "cpu", "qos": "", "memory": "8G", "gpus": 0,
                "extra_args": [], "time": "00:30:00", "cpus": 4, "run_ranks": 8, "run_time": "01:00:00"}
}
```

## 5. Run VIBORA
### One machine
From the VIBORA folder, in a terminal where your LLM tools are signed in:
```sh
python3 scripts/agent_bridge.py
```
Leave it running and open http://127.0.0.1:18080. Ctrl-C stops the bridge and the GUI server.

### Remote MOOSE host
1. On the cluster, clone and build VIBORA (section 3) and create `config.local.json` there (section 4).
2. Make sure your laptop can log in without typing a password (SSH keys, or your site's equivalent): `ssh user@cluster.example.edu true` must work non-interactively.
3. On your laptop, with your LLM tools signed in, run:
   ```sh
   ssh user@cluster.example.edu 'cat ~/projects/vibora/scripts/agent_bridge.py' | python3 -u - --ssh-host user@cluster.example.edu --remote-dir ~/projects/vibora
   ```
   Use the full path of the cluster checkout for `--remote-dir` if `~` differs there.
4. Open http://127.0.0.1:18080 on your laptop.

The bridge starts the GUI server on the cluster, forwards port 18080 to your laptop and port 18083 back to the bridge, and passes a fresh random token so only this bridge is accepted. The GUI server stops when the bridge does; leftover servers for the same port are stopped on start.

If a port is taken, choose others: `--gui-port 19081 --port 19084`.

### Slurm
With `scheduler.enabled: true`, custom-code builds and "Compute node" runs go through `sbatch`, and their state is polled with `squeue`. "This machine" runs always start directly on the MOOSE host. On a cluster, that's the login node you landed on, so keep them small.

## 6. Choose an LLM provider
Providers are used from the machine that runs the bridge. Set one up, then open **LLM model** in the GUI, press **Refresh models** and pick a model; the dialog also shows each provider's status.

| Provider | Setup | Notes |
|---|---|---|
| **Codex CLI** | Install the [Codex CLI](https://github.com/openai/codex) and sign in (`codex login`). | Uses your ChatGPT plan's allowance. Pass `--codex PATH` if it is not on `PATH`. |
| **Claude Code CLI** | Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and sign in once: `claude auth login` (add `--sso` for single sign-on). | Uses your Claude subscription (Pro, Max, Team or Enterprise). Runs with all tools, MCP servers and session saving disabled. Pass `--claude PATH` if `claude` is not on `PATH`. Models appear only once `claude auth status` reports you are signed in. |
| **Claude API** | `python3 -m pip install --user anthropic` (for the Python that runs the bridge), then `export ANTHROPIC_API_KEY=...` in that terminal. | Billed to the API key. Lists the current Claude models the key can use. |
| **Ollama** | Install [Ollama](https://ollama.com), `ollama pull <model>`, and start the server with a large context: `OLLAMA_CONTEXT_LENGTH=32768 ollama serve`. | Found at `VIBORA_OLLAMA_URL` (default `http://127.0.0.1:11434`). VIBORA's prompts are long; with the default context Ollama silently cuts them off. |
| **OpenAI-compatible server** | Start a local server (e.g. vLLM or llama.cpp) with an OpenAI-style `/v1` API. | Found at `VIBORA_LOCAL_URL` (default `http://127.0.0.1:8000/v1`). It must support `response_format` with a JSON schema. |

Each job records the model it used and logs the tokens every call reported.

## 7. Result images
After each run, `scripts/render_results.py` turns the Exodus output into PNG snapshots. It needs `numpy`, `matplotlib` and `netCDF4` (or `h5py`), and by default runs inside the conda environment named `moose`, found under `~/miniforge`, `~/miniforge3`, `~/mambaforge`, `~/miniconda3`, `~/anaconda3`, `~/.conda` or next to the MOOSE folder, or through `conda env list`. Check and install:
```sh
conda activate moose
python -c "import numpy, matplotlib, netCDF4"  || conda install -n moose numpy matplotlib netcdf4
```
If the environment is elsewhere, set `render_conda_prefix` to its folder; to use a specific interpreter instead, set `render_python`. If images cannot be made, the gallery says why and the run itself is unaffected.

## 8. Custom C++ and your repository
Approved, verified custom objects are copied into `moose_app/`, recorded in `capabilities/<job>/`, and committed to the VIBORA checkout on the MOOSE host. If that checkout has an `origin` remote, VIBORA rebases the commit onto `origin/<branch>` and pushes it, so pushing needs credentials on the MOOSE host (for GitHub, an SSH deploy key with write access works well). Without a remote, or when a push fails, the commit stays local and the job says why. These capabilities are yours: they accumulate in your own clone.

## 9. Troubleshooting
| Symptom | What to do |
|---|---|
| `Address already in use` when starting the bridge | Another bridge or GUI server is running; stop it, or use `--gui-port` and `--port`. |
| "SSH tunnel stopped" | Check non-interactive SSH login, and that `build/vibora` exists on the host. |
| "MOOSE executable not found" | Fix `moose_executable` in `config.local.json` on the MOOSE host. |
| "Slurm is not enabled" | Set `scheduler.enabled: true`, or run on "This machine". |
| A provider is missing in **LLM model** | Read its status line in the dialog: usually not signed in, or no key. |
| Generation seems stuck | The activity log and the counter show the slow step. Model calls can take minutes for large models. |

## 10. Security notes
- The GUI server and bridge listen only on `127.0.0.1`. On a shared cluster login node, other users on the same node can reach local ports, and the GUI itself has no login; the bridge only accepts requests that carry the session's random token.
- Model text is treated as data: the agent is not given tools, and custom C++ is only written after you approve a specific proposal, then compiled and tested in an isolated folder.
- API keys and CLI sign-ins stay on the machine running the bridge.
