# Architecture summary — SwarmEvolve-cyber @ a944b3d

Profile `quick`, scope `benchmarks/` + `baselines/`. No prior ledger or findings exist for this repo. Source-only run: no target code was executed.

## 1. Product, principals, authority, protected resources

Research benchmark repository for LLM-guided evolutionary program search. The SwarmEvolve code itself is not released (`README.md:57`); the repo ships 21 benchmark problems, a shared scoring harness, and vendored copies of three baseline frameworks (OpenEvolve, ShinkaEvolve, CodeEvolve) plus glue scripts.

- **Operator** (researcher): runs `baselines/run_baseline.sh` on a GPU host under their own uid; owns the host filesystem, environment variables (possibly real provider API keys), results directories, and the score log `EVAL_LOG`.
- **LLM output** (lowest trust inside the run): generated programs, diffs, meta text, patch names. Executing it is the product's core action.
- **Remote/adjacent network client and cross-site web page**: can reach the web UIs if the bind address or the operator's browser allows it.
- **Authors of on-disk state**: problem dirs, YAML/hydra configs, checkpoints, pickles, sqlite DBs, `.env`.
- **PR authors / issue commenters** on the upstream baseline repositories (vendored workflows are *not* active from this repo's root — there is no root `.github/`).
- **Coding agents** that consume `baselines/ShinkaEvolve/skills/*`.

Protected resources: operator files and environment secrets, integrity of benchmark scores (`EVAL_LOG` is the source of truth for every framework), the framework parent process, the operator's browser origin for the web UIs, CI secrets upstream.

## 2. Comparable baseline

AlphaEvolve-style frameworks. All three baselines run generated code locally by default with a timeout only. CodeEvolve documents its evaluation as "sandboxed" (`baselines/CodeEvolve/README.md:127`), but source shows a psutil monitor, and the glue disables the memory limit (`baselines/run_codeevolve.py:44`). No doc states "generated code runs unsandboxed". Unsandboxed generated-code execution by itself is therefore an accepted design trade-off of the class; it calibrates severity but does not dismiss a boundary failure built on top of it.

## 3. Stack, deployment, offline limits

Python + bash. CLI-only benchmarks; setuptools packages for the three baselines; Flask visualizer (OpenEvolve), stdlib `http.server` visualizer (ShinkaEvolve); optional Docker/Slurm backends in ShinkaEvolve; vLLM serving a local Qwen3 model. No lock files; two fully pinned requirement files in `baselines/`. Host for this audit: no Docker daemon, no bwrap/firejail; `unshare --user --net` works; scipy/flask/pytest/psutil absent, so target tests cannot run offline without installing dependencies. Target-controlled execution was not performed.

## 4. Entry surfaces and important paths

1. **Evolved program → scoring harness.** `benchmarks/evaluation.py:43-58` runs `run_evaluator.py` as a subprocess (temp cwd, new session, 60 s, `killpg` on timeout) with the full parent environment (`:46`). `run_evaluator.py:9-16` loads the problem evaluator; 15 of 21 evaluators `__import__` the program in-process. Scores are parsed from the last `@@METRICS@@` stdout line and appended to `EVAL_LOG`, which the child can also write.
2. **`circle_packing_26` evaluator.** Interpolates `program_path` into generated Python source (`evaluator.py:95-140`) and `pickle.load`s a results file written by the program's child (`:166-168`).
3. **ShinkaEvolve web UI.** `shinka/webui/visualization.py` binds all interfaces (`:1740`), no auth, CORS `*` (`:1681`); `db_path` query value joined to `search_root` with no containment (`:449` and nine sibling sites; `_get_actual_db_path` `:428-430` is a no-op); `/plot_file/` uses a `startswith` prefix check (`:995-997`); meta text reaches `wkhtmltopdf`/`pandoc` (`:1510`, `:1562`). Front-end `viz_tree.html` renders LLM-derived text through `marked.parse` → `innerHTML` (`:2868`, `:3042`, `:5692`), CDN scripts without SRI.
4. **OpenEvolve visualizer.** Flask, default `127.0.0.1` (`scripts/visualizer.py:207`), optional `--debug`. Manual-mode blueprint accepts unauthenticated form/JSON POST (`scripts/manual.py:159-177`) whose answer becomes the LLM reply (`openevolve/llm/openai.py:262-305`) and then executed code. JS sinks: `static/js/sidebar.js:421`, `list.js:96-138`, `manual.js:46-62`. Static export embeds `jsonify(data)` in `<script>` (`visualizer.py:158-159`).
5. **Resume-time deserialization.** ShinkaEvolve `results_dir/bandit_state.pkl` → `pickle.load` (`shinka/llm/prioritization.py:218-220`, via `core/async_runner.py:631-633`); CodeEvolve checkpoint `pickle.load` (`src/codeevolve/utils/ckpt.py:115`); OpenEvolve evaluator pickle at a predictable temp path (`openevolve/api.py:331-347`); hydra `_target_` instantiation from `.hydra/config.yaml` found in results dirs (`shinka/utils/utils_hydra.py:16-32,73-75`).
6. **Command construction.** `shinka/launch/slurm.py:20-27,271,352,441-493` joins config values into shell strings; `shinka/llm/providers/headless.py:212-219` uses `shell=True` with `shlex.join`; `baselines/run_baseline.sh:34,50-54` starts `vllm serve` without `--host`/`--api-key` and writes positional args into JSON unquoted.
7. **Vendored CI.** `openevolve/.github/workflows/claude.yml:15-37` (`@claude` trigger, no `author_association` gate, mutable action tag, OAuth secret); `python-test.yml:107,113` (`HF_TOKEN` on `pull_request`); CodeEvolve `ci.yml:13-40` (`contents: write`, auto-commit).
8. **Agent skills / model context.** `shinka-inspect` dumps LLM-generated program text into a context file for a coding agent (`skills/shinka-inspect/scripts/inspect_best_programs.py:110-213`); program stdout is fed back into later prompts (`baselines/openevolve_evaluator.py:13`, `shinka_evaluate.py:23`, `codeevolve_evaluate.py:19`).

## 5. Trust boundaries and strongest source-visible control

| Boundary | Strongest visible control |
|---|---|
| Evolved program ↔ scorer / score log | Subprocess + 60 s `killpg`; no fs/net/uid/env isolation |
| Evolved program ↔ framework parent on resume | None on pickle loads; `np.load(allow_pickle=False)` on scientific outputs |
| Network client ↔ operator files (Shinka UI) | `startswith` check on `/plot_file/` only |
| Cross-site page ↔ OpenEvolve manual answers | Default loopback bind; task file must exist; no CSRF token |
| LLM-derived text ↔ operator browser | Partial `escapeHtml` use; Jinja autoescape |
| Config values ↔ shell | `shlex.join` in `headless.py`; none in `slurm.py` |
| PR/issue author ↔ CI secrets | ShinkaEvolve association gate + SHA pins; none in OpenEvolve `claude.yml` |

YAML loads are `safe_load` everywhere; SQL uses bound parameters; no archive extraction or `torch.load`.

## 6. Starting paths

`benchmarks/evaluation.py`, `benchmarks/run_evaluator.py`, `benchmarks/problems/circle_packing_26/evaluator.py`, `baselines/ShinkaEvolve/shinka/webui/`, `baselines/openevolve/scripts/`, `baselines/ShinkaEvolve/shinka/llm/prioritization.py`, `baselines/CodeEvolve/src/codeevolve/utils/ckpt.py`, `baselines/ShinkaEvolve/shinka/launch/slurm.py`, `baselines/run_baseline.sh`, `baselines/*/.github/workflows/`, `baselines/ShinkaEvolve/skills/`.

## 7. Prior coverage

None. Deterministic tool input for this run: osv-scanner (pillow 11.3.0 in `baselines/requirements_openevolve_shinkaevolve.txt` matches 58 advisory groups; example-only hits elsewhere), SkillSpector static scan of the four ShinkaEvolve skills (LOW, 5 medium notes: LP3 ×3, EA2 ×2), open-code-review delegation rules for the key files.

## 8. Companion selection

- `AI-AND-LLM.md` — model output is executed and re-ingested; skill context bundles feed a coding agent.
- `CLIENT-SIDE.md` — both web UIs render LLM-derived data into the DOM.
- `WEB-PROTOCOL-AND-AUTH.md` — state-changing unauthenticated POST on the OpenEvolve manual-mode blueprint.
- `SUPPLY-CHAIN-AND-RELEASE.md` — vendored CI workflows with secrets, unpinned actions and dependencies.

Not selected: memory-safety (no native code in scope beyond example C++ headers), cloud, RPC/messaging, data-isolation (single-tenant), desktop/mobile, resource-exhaustion (single-operator host; no shared quota boundary visible in source).
