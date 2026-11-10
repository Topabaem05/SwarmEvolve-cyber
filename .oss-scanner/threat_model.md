# Threat model

## What this project does and where untrusted input enters

A research benchmark for LLM-guided evolutionary program search. It ships 21 benchmark problems with a
shared scoring harness (`benchmarks/`) and vendored, unmodified copies of three baseline frameworks
(`baselines/openevolve`, `baselines/ShinkaEvolve`, `baselines/CodeEvolve`) with glue scripts.

Untrusted input, lowest trust first:

1. **LLM output.** Generated programs, diffs, summaries, patch names. The frameworks execute generated
   programs by design, on the operator's host, with a timeout as the main control.
2. **Network clients and web pages.** The ShinkaEvolve viewer (`shinka/webui/visualization.py`, binds all
   interfaces) and the OpenEvolve visualizer (`scripts/visualizer.py`, loopback by default) have no
   authentication.
3. **On-disk state.** Results directories, checkpoints, pickles, sqlite databases and hydra configs that
   a framework reloads, including state that a generated program could have written.
4. **Benchmark problem directories and configs** (trusted when they come from this repository).

## Components that matter most / least

Most:
- `benchmarks/evaluation.py`, `benchmarks/run_evaluator.py` and the problem evaluators: the integrity of
  the scores they record is what the paper's comparison rests on.
- The two web UIs.
- Resume-time loading of pickles and configs in the three frameworks.

Less, but in scope: shell command construction (`shinka/launch/slurm.py`, `baselines/run_baseline.sh`),
the ShinkaEvolve agent skills under `baselines/ShinkaEvolve/skills/`.

Out of scope: `baselines/*/examples/`, `baselines/*/tests/`, `baselines/*/docs/`, `assets/`. The vendored
`.github/workflows` files are not active in this repository (it has no root workflows of their own).

## How to exercise it

- `python benchmarks/evaluation.py <problem> <program.py>` scores one program.
- `python baselines/ShinkaEvolve/shinka/webui/visualization.py` and
  `python baselines/openevolve/scripts/visualizer.py --path <dir>` start the web UIs.
- `/opt/venv/bin/python` in the image has the pinned environment; the three frameworks are importable.
- Each framework has a `tests/` directory. No GPU, model weights or LLM endpoint exists in the image, so
  full evolution runs are not possible; drive the components directly with dummy data.

## How we rate severity

- "A generated program can run arbitrary code as the operator" is the documented design of this class
  of software. Do not report it by itself.
- **High**: a generated program gains code execution in a framework parent process that outlives the
  evaluation timeout or persists across runs; a network client or cross-site page reads operator files
  or causes code execution on the operator host.
- **Medium**: a generated program can forge or alter recorded benchmark scores; script execution in the
  operator's browser from LLM-derived content; an issue that needs a non-default option.
- **Low**: needs another local user on a single-user research host, or only discloses non-secret data.
- Vulnerable dependency pins are reportable only with a reachable code path that handles untrusted data.

## Anything to leave alone

- Do not report missing sandboxing of generated code by itself (see above).
- Do not report issues that exist only under `examples/` or `tests/`.
