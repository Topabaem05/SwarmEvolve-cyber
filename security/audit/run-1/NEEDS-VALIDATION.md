# Needs validation — run-1

Source-grounded leads that still need a bounded local observation. None has a severity, and none is a confirmed vulnerability.
Each lead lists its repository trace, what blocks confirmation, and the exact local check to run in the sandbox once the owner approves it (see `security/DESIGN.md`).

## `baselines-glue/vllm-localhost-endpoint-impersonation`

**run_baseline.sh accepts any listener on localhost:<port> as the model server, so another local user can supply the programs the operator executes**

Lower-trust principal: a second unprivileged local user (or other workload sharing the host network namespace) on the GPU host where the operator runs baselines/run_baseline.sh. Accepted input: HTTP responses from whichever process is listening on `localhost:<port>`. Control that should stop it: the launcher should only hand the frameworks an endpoint that is provably the vLLM child it started (and the frameworks should authenticate that endpoint); the only visible checks are a `curl -s localhost:$port/v1/models` probe and a `kill -0 $server` liveness test that is evaluated after the probe has already returned success. Boundary crossed: local user A to code execution as operator B. Affected resource: the operator's account (files, environment variables including any provider keys, EVAL_LOG score integrity), because every completion returned by the endpoint is turned into a program and executed by benchmarks/evaluation.py with the operator's environment.

Source-visible mechanics: (1) free_port binds ('', 0), prints the number and releases the socket; the number is reused later for `vllm serve ... --port $port`, where it is visible in the process arguments. For shinkaevolve the main port is chosen before the embedding server is started and only used after that server is up. (2) `serve` backgrounds vLLM and loops: `curl -s localhost:$port/v1/models > /dev/null && return 0; kill -0 $server || break`. Any HTTP responder satisfies the probe (no -f, no identity check), and success is returned without consulting the child's state, so a vLLM child that failed to bind because the port was taken goes unnoticed. (3) All three drivers configure the framework with `http://localhost:<port>/v1` and the placeholder key 'EMPTY'; vLLM is started without --host and without --api-key, so neither side authenticates the other and the hostname is resolved by each client. (4) The completion text becomes child_code and is executed by the shared evaluation as a subprocess that inherits the operator environment.

Two ways a foreign listener can end up answering, both needing local validation: (a) binding 127.0.0.1:<port> between the `vllm serve` exec (port visible in process arguments) and vLLM's own listen; (b) binding [::1]:<port> at any time if vLLM's default bind covers IPv4 only, with clients that resolve `localhost` to ::1 first. This is not the documented 'generated code runs unsandboxed' trade-off: the party choosing the code is a different local principal than the operator and the operator's own model. Reviewer note: Parent review confirmed free_port binds and releases a port (run_baseline.sh:29), and that serve() accepts the endpoint as soon as `curl -s localhost:$port/v1/models` succeeds, a test made before the liveness check of the vLLM child in the same loop iteration (:36); no key or identity check ties the answering process to the server the script started.

**Claimed root cause.** baselines/run_baseline.sh treats 'something answers HTTP on localhost:<port>' as proof that its own vLLM child is serving: the port is picked by bind-and-release, the readiness probe is evaluated before (and independently of) the child liveness test, and the server/clients share no secret and use the ambiguous hostname `localhost`, so the identity of the endpoint whose output is executed is never established.

**Trace**

1. `entrypoint` `baselines/run_baseline.sh:36` (serve) — Readiness loop: `curl -s localhost:$port/v1/models > /dev/null && return 0` succeeds for any HTTP responder on that port and returns before `kill -0 $server` is consulted; a foreign listener's response is accepted here as 'vLLM is up'.
2. `propagation` `baselines/run_baseline.sh:58` (main script, case $framework) — The same port is handed to the framework driver (`--port $port`); lines 59 and 60 do the same for shinkaevolve (plus --embed-port) and codeevolve.
3. `propagation` `baselines/run_openevolve.py:37` (module level, config['llm']) — OpenEvolve is configured with api_base `http://localhost:{port}/v1` and api_key 'EMPTY'; no credential or identity ties the client to the vLLM child.
4. `propagation` `baselines/openevolve/openevolve/llm/openai.py:86` (OpenAILLM.__init__) — AsyncOpenAI client is created with base_url=self.api_base; all completions are requested from whichever process holds that address.
5. `propagation` `baselines/openevolve/openevolve/process_parallel.py:209` (_run_iteration_worker) — llm_response is obtained from the endpoint via _worker_llm_ensemble.generate_with_context.
6. `propagation` `baselines/openevolve/openevolve/process_parallel.py:283` (_run_iteration_worker) — Diff blocks extracted from the response are applied to the parent program to form child_code (full-rewrite mode takes the response's code block instead).
7. `propagation` `baselines/openevolve/openevolve/process_parallel.py:364` (_run_iteration_worker) — child_code is passed to _worker_evaluator.evaluate_program.
8. `propagation` `baselines/openevolve/openevolve/evaluator.py:455` (Evaluator._direct_evaluate) — The code is written to a temp file (line 260) and the configured evaluate function is called with its path.
9. `propagation` `baselines/openevolve_evaluator.py:11` (evaluate) — The glue evaluator forwards the program path to the shared benchmarks evaluation.
10. `propagation` `benchmarks/evaluation.py:43` (evaluate) — subprocess.Popen runs run_evaluator.py on the program with env={**os.environ, ...} (line 46): the operator's uid and full environment, no isolation beyond a temp cwd and a 60 s limit.
11. `sink` `benchmarks/run_evaluator.py:12` (module level) — module.evaluate(program_path) runs the problem evaluator, which imports/executes the program text supplied by the endpoint.

**Evidence**

- `baselines/run_baseline.sh:29` — free_port: `s.bind(('', 0)); print(s.getsockname()[1])` - the socket is released when the helper exits, so the returned port is unreserved until vLLM binds it.
- `baselines/run_baseline.sh:34` — `vllm serve "$@" --port $port >> $log 2>&1 &` - started in the background with the port in its arguments, without --host and without --api-key; a bind failure is only written to the log.
- `baselines/run_baseline.sh:36` — Strongest visible control: probe then liveness. The probe has no -f and no responder identity check, and `return 0` short-circuits before `kill -0 $server`.
- `baselines/run_baseline.sh:42` — `port=$(free_port)` is taken before the optional embedding server is started and awaited (lines 46-47) and is only bound at line 50.
- `baselines/run_baseline.sh:22` — `OPENAI_API_KEY=EMPTY` is exported: the clients present a placeholder, so no shared secret exists between launcher, server and frameworks.
- `baselines/run_shinkaevolve.py:33` — ShinkaEvolve path of the same root cause: every LLM role uses `local/{model}@http://localhost:{port}/v1` (embedding endpoint at line 45).
- `baselines/run_codeevolve.py:60` — CodeEvolve path of the same root cause: API_BASE=`http://localhost:{port}/v1`, API_KEY='EMPTY'.
- `benchmarks/evaluation.py:46` — The evaluated program inherits the operator's whole environment (`env={**os.environ, **SINGLE_THREAD}`).

**Blockers**

- No target code may be executed in this run (sandbox controls incomplete), so the readiness-gate behaviour of `serve` with a foreign listener and a failed/absent vLLM child has not been observed.
- Deployment fact: whether the benchmark host has a second local principal (other user accounts, or unprivileged workloads sharing the host network namespace) that can read process arguments (/proc not mounted with hidepid) or probe loopback ports during a run.
- Dependency fact (vLLM is not vendored and its version is not pinned in the repository): how long `vllm serve` takes from exec to listen() on --port, and which address family/interface it binds when --host is omitted (IPv4 wildcard only versus dual-stack); this decides whether 127.0.0.1:<port> can be taken first or [::1]:<port> stays free for the whole run.
- Host fact: the order in which `localhost` resolves (::1 versus 127.0.0.1) for curl and for the OpenAI/httpx clients used by the three frameworks.

**Local check (sandbox, dummy data).** In the no-network sandbox with isolated loopback and dummy data only. Step 1 (readiness gate): create scratch/bin/vllm as a stub script that sleeps 3 seconds and exits 1 (stand-in for a vLLM child that could not bind) and put scratch/bin first on PATH. Start a dummy HTTP listener (python3 http.server subclass) on 127.0.0.1:P, P a free port, that answers every GET with the body {"sentinel":"foreign-listener"}. Copy lines 29-38 of baselines/run_baseline.sh (free_port and serve) verbatim into scratch/harness.sh and append: `serve P scratch/vllm.log dummy-model; echo "serve_rc=$?" > scratch/poc_marker`. Run it under `bash` with `set -u`, 30 s wall-clock limit. Observable that proves the boundary result: scratch/poc_marker contains `serve_rc=0` and stdout does not contain 'vLLM did not start', although the stub child exited 1 and never listened. Step 2 (address-family split): bind a dummy listener on 0.0.0.0:P2 answering {"sentinel":"own-server"} (stand-in for an IPv4-wildcard bind), then try to bind a second listener on [::1]:P2 answering {"sentinel":"foreign-listener"}; write to scratch/poc_family whether the second bind succeeded and which sentinel is returned by `curl -s localhost:P2/v1/models` and by Python `urllib.request.urlopen('http://localhost:P2/v1/models')`. Stop all listeners afterwards. Nothing beyond these marker files is produced.

**Owner-observed check.** Owner-observed on the benchmark host during one run: record the listening address of the vLLM process for the run's port (`ss -ltnp`), the output of `getent ahosts localhost`, whether other user accounts or shared-network containers exist on the host, whether /proc is mounted with hidepid, and whether a host firewall filters the port from other machines.

## `benchmarks-evaluation/eval-log-writable-by-evaluated-program`

**Evaluated program receives the path of the shared score log and can write records to it directly**

EVAL_LOG is documented as the file from which every framework's scores are read. evaluation.py starts the evaluator child with the complete parent environment, so the log path exported by run_baseline.sh reaches run_evaluator.py, and the per-case children of the scientific problems and the circle_packing_26 wrapper inherit it again because they are started without an env argument. The log is an ordinary file owned by the uid that runs the program and is opened in append mode by the parent; nothing authenticates a record or restricts who appends, truncates or rewrites it. A program in any of the 21 problems, including those whose header says the child is given only the case inputs, can therefore append records with a chosen score, time and sha, or alter earlier records and the saved sources under programs/. Run directories of the other frameworks for the same problem are siblings of the log's parent directory, so the same access reaches their logs when they are on the same host. This is independent of the marker channel: moving the program out of the evaluator process would not remove it. The lower-trust principal is the LLM output; the affected resource is the integrity of the score record that the cross-framework comparison relies on. Reviewer note: Parent review confirmed the child environment is {**os.environ, **SINGLE_THREAD} (evaluation.py:46), that run_baseline.sh:55 exports EVAL_LOG, and that records are appended with no integrity field (evaluation.py:72-75). This is a separate control from the metrics marker: fixing the marker does not protect the log file.

**Claimed root cause.** The score record of truth is a plain file in the trust domain of the evaluated program, and evaluation.py passes its location to that program through the inherited environment; there is no integrity control on the log.

**Trace**

1. `entrypoint` `benchmarks/evaluation.py:33` (evaluate) — An LLM-generated program is submitted for scoring while EVAL_LOG is set in the adapter's environment.
2. `propagation` `benchmarks/evaluation.py:46` (evaluate) — The child environment is the full parent environment plus thread settings, so EVAL_LOG is inherited.
3. `propagation` `benchmarks/scientific_cases.py:42` (run_case) — The per-case child that runs the program is started without an env argument and inherits EVAL_LOG as well.
4. `sink` `benchmarks/evaluation.py:74` (evaluate) — The log is a plain append-mode file with no authentication of records; the program runs under the same uid and knows its path.

**Evidence**

- `benchmarks/evaluation.py:6` — Comment: all frameworks' scores are read from these logs.
- `benchmarks/evaluation.py:71` — Program sources are saved beside the log by hash with a plain write; they share the same exposure.
- `baselines/run_baseline.sh:55` — EVAL_LOG is exported for the whole framework run as <run directory>/eval_log.jsonl.
- `baselines/run_baseline.sh:18` — Run directories of all frameworks for a problem are siblings under results/<problem>/.
- `benchmarks/problems/circle_packing_26/evaluator.py:148` — The wrapper child is started without an env argument and inherits EVAL_LOG too.
- `benchmarks/scientific_cases.py:2` — Header describes the child as receiving only the case inputs, yet the environment and file access are unrestricted.

**Blockers**

- No bounded local observation was allowed in this run, so a record written by an evaluated program has not been observed in the log.
- The reader of EVAL_LOG used for the published results is not in the repository; how it treats additional, duplicate or back-dated records is not source-visible.

**Local check (sandbox, dummy data).** In the no-network sandbox with python3 and numpy, create the directory <scratch>/b and the file <scratch>/b/poc_b.py containing: import json, os / def solve(nu, T, x): / (indented) open(os.environ['EVAL_LOG'], 'a').write(json.dumps({'time': 1.0, 'score': 777.0, 'sha': 'forged', 'error': '', 'metrics': {}}) + chr(10)) / (indented) return x * 0. From the repository root run: EVAL_LOG=<scratch>/b/eval_log.jsonl python3 benchmarks/evaluation.py burgers_1d <scratch>/b/poc_b.py. Single observable: <scratch>/b/eval_log.jsonl contains lines with sha 'forged' and score 777.0 written by the per-case child, next to the one genuine record whose score is near 0.

**Owner-observed check.** Owner check: confirm whether the analysis that produces the result tables reads eval_log.jsonl without any cross-check against re-evaluation of programs/<sha>.py, and whether several frameworks' runs share one host account.

## `benchmarks-evaluation/inband-metrics-marker-forgery`

**Evaluated program can set its own recorded score through the in-band metrics marker**

The shared harness reads the score from the last line of the child's combined stdout and stderr that starts with the fixed marker '@@METRICS@@'. For 15 of the 21 problems the evaluator imports the LLM-generated program into the same interpreter that later prints that marker. Program code can therefore print its own marker line and end the interpreter (os._exit, or sys.exit, which the evaluators' 'except Exception' does not catch) before the genuine line is printed, or replace the evaluator's functions in memory. evaluation.py never checks the child's exit status, uses no per-run secret, and accepts any numeric non-NaN score, including values far above what the evaluator can produce. The forged value is returned to the framework as the fitness and is appended to EVAL_LOG by the trusted parent, which the file header describes as the place all frameworks' scores are read from. The lower-trust principal is the LLM output; the affected resource is the integrity of the benchmark scores and of the selection signal inside each run. The strongest control visible in source is the child process boundary with a 60 s limit, which does not separate the program from the marker's author. For the six evaluators that run the program in a further child process, the same marker channel might be reachable by a same-uid descendant that reopens the parent's stdout pipe through /proc and then stops the parent; that variant depends on operating-system behaviour and is not established from source. Reviewer note: Parent review read benchmarks/evaluation.py and benchmarks/run_evaluator.py in full: the scorer takes found[-1] among stdout lines starting with the marker (evaluation.py:50-52) and never checks the child exit status; run_evaluator.py prints the genuine marker only after module.evaluate() returns (:12-16), and in-process evaluators such as kissing_number_11 import the program into that same interpreter (evaluator.py:65-66). A harness draft exists at security/pipeline/poc/benchmarks-evaluation_inband-metrics-marker-forgery/.

**Claimed root cause.** The metrics channel is unauthenticated and shared with the untrusted program: run_evaluator.py executes the program inside the process that emits the marker, and evaluation.py trusts the last marker line without checking the exit status, a per-run secret or a plausible score range.

**Trace**

1. `entrypoint` `benchmarks/evaluation.py:33` (evaluate) — The framework adapters pass the path of an LLM-generated program to the shared evaluate().
2. `propagation` `benchmarks/evaluation.py:43` (evaluate) — run_evaluator.py is started on that program with stdout piped and stderr merged into it.
3. `propagation` `benchmarks/run_evaluator.py:12` (module) — The problem evaluator's evaluate() runs in this interpreter, which prints the genuine marker only afterwards (line 16).
4. `propagation` `benchmarks/problems/kissing_number_11/evaluator.py:66` (evaluate) — __import__ executes the program's top-level code in the evaluator process; the surrounding handler catches Exception only (line 95).
5. `sink` `benchmarks/evaluation.py:52` (evaluate) — The JSON after the last marker line becomes the metrics, with no exit-status or origin check; the score is then returned and logged.

**Evidence**

- `benchmarks/evaluation.py:50` — Marker lines are selected from all output lines by prefix only; found[-1] is used.
- `benchmarks/evaluation.py:62` — The only score validation is a type and NaN test; there is no upper bound and process.returncode is never read.
- `benchmarks/evaluation.py:72` — The accepted score is written into the EVAL_LOG record by the parent process.
- `benchmarks/evaluation.py:2` — Header states combined_score is the score and is 0 for an invalid program.
- `benchmarks/run_evaluator.py:16` — The genuine marker is printed with the same fixed public prefix after the program has run in-process.
- `benchmarks/problems/kissing_number_11/evaluator.py:95` — Only Exception is caught, so SystemExit or os._exit from program code ends the evaluator before it reports.
- `benchmarks/problems/first_autocorrelation/evaluator.py:67` — Same in-process import pattern; one of 15 evaluators that share it.
- `baselines/shinka_evaluate.py:27` — The adapter forwards combined_score to the framework without further validation.

**Blockers**

- No bounded local observation was allowed in this run (no target code execution), so the forged score has not been observed in the returned metrics or in EVAL_LOG.
- Whether a same-uid descendant can inject a marker for the six process-isolated evaluators by reopening the parent's stdout pipe through /proc is an operating-system fact that was not observed.
- The script that reads EVAL_LOG for the published tables is not in the repository, so any filtering it applies to implausible scores is not source-visible.

**Local check (sandbox, dummy data).** In the no-network sandbox with python3 and numpy, create <scratch>/a/poc_a.py with three lines: import os, json / print('@@METRICS@@' + json.dumps({'combined_score': 123.0}), flush=True) / os._exit(0). The file defines no kissing_number11 function, so it is an invalid program. From the repository root run: EVAL_LOG=<scratch>/a/eval_log.jsonl python3 benchmarks/evaluation.py kissing_number_11 <scratch>/a/poc_a.py. Single observable: the printed metrics have combined_score 123.0 and the one line appended to <scratch>/a/eval_log.jsonl has score 123.0; if the control held, the score would be 0 with an error.

## `benchmarks-evaluation/time-limit-process-escape`

**Processes started by an evaluated program outlive the evaluation and its time limit**

evaluation.py starts the evaluator in a new session and states that this lets a timeout kill everything the child started. The group kill is sent only when communicate() times out, and only to the original process group. A descendant that the program moved to another session or group is not signalled, and when the evaluation finishes normally nothing is signalled at all, so a background process that does not hold the stdout pipe keeps running with the operator's uid and environment after the score has been recorded. The per-case runner of the scientific problems has the same structure, and the circle_packing_26 evaluator kills only its direct child. Because the evaluator child is in its own session, the group SIGTERM that run_baseline.sh relies on at the end of the budget does not reach in-flight evaluations, whose only supervisor is the adapter process being terminated. The task statements promise a hard 60 s limit on one core. A surviving process is not bound by it: it can continue computing and leave results for later programs of the same lineage, act on the score log after the parent has written the genuine record, and keep running after the framework run ends. The lower-trust principal is the LLM output; the affected resources are the compute-budget rule the comparison depends on and the operator's host after the run. A related robustness effect is that the communicate() call after the kill has no timeout, so a surviving descendant that still holds the pipe keeps evaluate() from returning. Reviewer note: Parent review confirmed os.killpg is called only in the TimeoutExpired branch (evaluation.py:55-56) although the comment at :41 says the process group lets a timeout kill everything the evaluator started; a descendant that calls setsid leaves the group. The concrete cross-boundary effect to test is work that continues past the 60 s limit and is consumed by a later evaluation (the per-evaluation compute budget the benchmark states).

**Claimed root cause.** Process lifetime is bound to the evaluation only through a process-group SIGKILL issued in the timeout handler; there is no kill on normal completion and no containment (subreaper, cgroup or PID namespace) for descendants that leave the group.

**Trace**

1. `entrypoint` `benchmarks/evaluation.py:33` (evaluate) — An LLM-generated program is submitted for scoring.
2. `propagation` `benchmarks/evaluation.py:43` (evaluate) — The evaluator child is started as leader of a new session and process group.
3. `propagation` `benchmarks/run_evaluator.py:12` (module) — Program code runs and may start a process in a different session with its standard streams detached.
4. `sink` `benchmarks/evaluation.py:56` (evaluate) — The only termination step: SIGKILL to the original group, reached only on TimeoutExpired.

**Evidence**

- `benchmarks/evaluation.py:41` — Comment claims the separate process group lets a timeout kill everything the child started.
- `benchmarks/evaluation.py:48` — Normal completion path: no signal is sent to the group after communicate() returns.
- `benchmarks/evaluation.py:57` — communicate() without a timeout after the kill; it waits for every holder of the pipe.
- `benchmarks/scientific_cases.py:48` — Same pattern for the per-case child: group kill only in the timeout handler.
- `benchmarks/problems/circle_packing_26/evaluator.py:180` — process.kill() reaches only the direct wrapper child.
- `baselines/run_baseline.sh:54` — End of budget relies on SIGTERM to the framework's process group, which excludes evaluator sessions.
- `benchmarks/problems/kissing_number_11/task.md:23` — Task statement promises a single CPU core and a hard time limit of 60 seconds.

**Blockers**

- No bounded local observation was allowed in this run, so a surviving descendant has not been observed after a timeout or after normal completion.
- Whether the deployment adds outer containment (container, systemd scope, cgroup kill) around framework runs is not source-visible.

**Local check (sandbox, dummy data).** In the no-network sandbox with python3 and numpy, create <scratch>/c/child.py: import os, time / time.sleep(8) / open(os.environ['POC_MARKER'], 'w').write('alive'). Create <scratch>/c/poc_c.py: import os, subprocess, sys, time / subprocess.Popen([sys.executable, os.environ['POC_CHILD']], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True) / time.sleep(30). From the repository root run, with the limit shortened to keep the check bounded: POC_CHILD=<scratch>/c/child.py POC_MARKER=<scratch>/c/marker python3 -c "import sys; sys.path.insert(0, 'benchmarks'); import evaluation; evaluation.TIME_LIMIT = 3; print(evaluation.evaluate('<scratch>/c/poc_c.py', 'kissing_number_11'))". Single observable: evaluate() returns the error 'time limit of 3 s exceeded' after about 3 s, and about 5 s later <scratch>/c/marker is created by the descendant that survived the group kill. The helper exits by itself after 8 s.

**Owner-observed check.** Owner check: after a baseline run ends, list processes of the run account (ps -u <account> -o pid,ppid,sid,etime,cmd) and confirm whether any interpreter started from an evaluation is still alive.

## `benchmarks-scientific-cases/reference-answers-readable-by-program`

**Scientific-problem programs can read the reference answers they are scored against**

scientific_cases.py states that the program's entry function runs in a child process that receives only the case inputs and never the reference answer. That is true of the arguments, but the child runs under the same uid with no file-system restriction. For convection_diffusion_2d and helmholtz_2d the answers are stored in reference.npz beside the evaluator, world-readable and keyed by case name; for burgers_1d, nonnormal_eigenvalues and sparse_linear_systems the evaluator source regenerates the references from a fixed seed, so importing that file yields them. The absolute problem directory appears in the command line of the child's parent process, and BENCHMARK_PROBLEM is in the inherited environment. A program that returns the stored reference for the case it is given has relative error 0 and receives full marks on every case without solving the problem. The lower-trust principal is the LLM output; the affected resource is the validity of the scores of the five scientific-computing problems. The control named in source is the separate child process with input-only arguments. Reviewer note: Parent review confirmed the explicit claim at benchmarks/scientific_cases.py:2-5 that the child "receives only the case's inputs (never the reference answer)"; the child (CHILD, :19-29) runs under the same uid with no file-system restriction, and the score is digits of accuracy against the reference.

**Claimed root cause.** Reference answers are kept in files readable by the process that runs the untrusted program, and the isolation claimed for that process covers only its arguments, not its file access or environment.

**Trace**

1. `entrypoint` `benchmarks/evaluation.py:43` (evaluate) — The evaluator child is started with the absolute problem directory and program path in its argv and the full environment.
2. `propagation` `benchmarks/problems/convection_diffusion_2d/evaluator.py:24` (cases) — References are loaded from reference.npz in the problem directory, keyed by case name.
3. `propagation` `benchmarks/scientific_cases.py:42` (run_case) — The per-case child is started under the same uid with inherited environment and no file-system restriction.
4. `propagation` `benchmarks/scientific_cases.py:26` (CHILD) — The program's entry function executes in that child and can open any file the operator can read.
5. `sink` `benchmarks/scientific_cases.py:75` (evaluate_cases) — The returned array is compared with the same reference; an identical array gives relative error 0 and full digits.

**Evidence**

- `benchmarks/scientific_cases.py:2` — Header: the child receives only the case inputs, never the reference answer.
- `benchmarks/scientific_cases.py:62` — digits() maps a relative error of 0 to the cap, so an exact copy scores full marks.
- `benchmarks/problems/helmholtz_2d/evaluator.py:24` — Second problem whose answers are in reference.npz beside the evaluator.
- `benchmarks/problems/sparse_linear_systems/evaluator.py:76` — Planted solutions come from a fixed seed in the evaluator source and can be regenerated by importing it.
- `benchmarks/problems/burgers_1d/evaluator.py:28` — Reference values are computed by a function in the evaluator source from fixed inputs.
- `benchmarks/evaluation.py:44` — The absolute problem directory is placed in the evaluator child's argv, visible to its children.

**Blockers**

- No bounded local observation was allowed in this run, so a full score obtained by returning the stored reference has not been observed.
- Reading the parent's command line needs a /proc file system consistent with the PID namespace; that is an operating-system fact of the evaluation host.

**Local check (sandbox, dummy data).** In the no-network sandbox with python3 and numpy and a /proc that matches the sandbox PID namespace, create <scratch>/r/poc_r.py: import os / import numpy as np / def solve(eps, b, x, y): / (indented) problem_dir = open('/proc/%d/cmdline' % os.getppid(), 'rb').read().split(bytes(1))[2].decode() / (indented) return np.load(os.path.join(problem_dir, 'reference.npz'))['eps_%g' % eps]. From the repository root run: python3 benchmarks/evaluation.py convection_diffusion_2d <scratch>/r/poc_r.py. Single observable: combined_score is 1.0 and output_tail reports 6.00 of 6 digits for all five cases although the file contains no solver; if the control held, the reference would be unreachable and the score would be 0.

## `circle-packing-26-evaluator/results-pickle-load`

**circle_packing_26 evaluator unpickles a results file controlled by the evaluated program**

The circle_packing_26 evaluator is the one evaluator that runs the program in a child process of its own. The child returns its result by pickling the objects that run_packing() returned into a file next to the wrapper script, and the evaluator loads that file with pickle.load after checking only that the child exited with code 0. The objects are chosen by the program, and the program can also write the file itself because its path is the wrapper script path plus '.results'. Unpickling therefore executes program-chosen callables inside the run_evaluator.py process, which is the process that prints the metrics marker. That removes the only separation this evaluator has between the program and the scorer: code running there can emit its own metrics and end the process, and a SystemExit raised during the load is not caught by the evaluator's 'except Exception', while the child's stdout, whose lines after the first are reprinted without a prefix, has already been written. The lower-trust principal is the LLM output; the crossed boundary is child process to evaluator process; the affected resource is the integrity of this problem's scores. Both processes run under the same uid, so no additional operating-system privilege is claimed. Reviewer note: Parent review confirmed run_with_timeout loads <wrapper>.results with pickle.load (circle_packing_26/evaluator.py:166-168) after checking only the child exit code. Scope of the gain: the loading process is the run_evaluator.py child that prints the metrics marker, so this is a second route to score forgery for the one evaluator that separates the program from the scorer by a process; it does not reach the framework process.

**Claimed root cause.** run_with_timeout uses pickle as the result format for data produced by the untrusted child and loads it in the evaluator process with no restriction on the types that may be constructed.

**Trace**

1. `entrypoint` `benchmarks/problems/circle_packing_26/evaluator.py:208` (evaluate) — The LLM-generated program path is handed to run_with_timeout.
2. `propagation` `benchmarks/problems/circle_packing_26/evaluator.py:119` (run_with_timeout) — In the child, the wrapper calls the program's run_packing(); the returned objects are program-controlled.
3. `propagation` `benchmarks/problems/circle_packing_26/evaluator.py:129` (run_with_timeout) — The wrapper pickles those objects into '<wrapper path>.results', a path the program can also write directly.
4. `propagation` `benchmarks/problems/circle_packing_26/evaluator.py:162` (run_with_timeout) — The only gate before loading is the child's exit code.
5. `sink` `benchmarks/problems/circle_packing_26/evaluator.py:168` (run_with_timeout) — pickle.load of the child-written file runs in the evaluator process.

**Evidence**

- `benchmarks/problems/circle_packing_26/evaluator.py:144` — results_path is derived from the wrapper script name, which the child knows as its own script path.
- `benchmarks/problems/circle_packing_26/evaluator.py:157` — Child stdout is reprinted with a prefix on its first line only, before the load.
- `benchmarks/problems/circle_packing_26/evaluator.py:271` — evaluate() catches Exception only; SystemExit from the load ends the evaluator before it reports.
- `benchmarks/run_evaluator.py:16` — The process that performs the load is the one that prints the genuine metrics marker.
- `benchmarks/scientific_cases.py:57` — Sibling control for comparison: the scientific problems return child data with np.load(allow_pickle=False).

**Blockers**

- No bounded local observation was allowed in this run, so execution in the evaluator process during the load has not been observed.

**Local check (sandbox, dummy data).** In the no-network sandbox with python3 and numpy, create the directories <scratch>/d and <scratch>/d/tmp and the file <scratch>/d/poc_d.py: import os / class Marker: / (indented) def __reduce__(self): return (exec, ("import os; open(os.environ['POC_MARKER'], 'w').write(str(os.getpid()))",)) / def run_packing(): / (indented) open(os.environ['POC_CHILD_PID'], 'w').write(str(os.getpid())) / (indented) return (Marker(), Marker(), 0.0). From the repository root run: TMPDIR=<scratch>/d/tmp POC_MARKER=<scratch>/d/marker POC_CHILD_PID=<scratch>/d/child_pid python3 benchmarks/evaluation.py circle_packing_26 <scratch>/d/poc_d.py. Single observable: <scratch>/d/marker exists and holds a PID different from the one in <scratch>/d/child_pid, showing the callable ran in the evaluator process during pickle.load rather than in the program's child.

## `circle-packing-26-evaluator/shared-tempdir-on-module-search-path`

**Evaluation runs Python with the shared temp directory first on the module search path**

The circle_packing_26 evaluator writes its wrapper script directly into the system temp directory and runs it as a script. Python then puts the script's directory, normally the world-writable /tmp, at the front of the module search path, ahead of the standard library and site-packages, and the wrapper imports numpy, pickle and traceback. A file such as numpy.py or pickle.py present in that directory is imported and executed with the operator's uid on every circle_packing_26 evaluation, under any framework. The harness sets PYTHONNOUSERSITE but not safe-path mode. The results file is a predictable sibling name in the same directory, is opened by the child without exclusive creation, and is unpickled by the evaluator whenever it exists and the child exited with 0, so on hosts without the protected-file sysctls a file placed there by another account can be loaded. The same pattern reaches the 15 in-process evaluators when OpenEvolve is the framework: OpenEvolve writes each program directly into the temp directory and the evaluators insert the program's directory at sys.path[0] before importing it, so the program's own imports of modules not yet loaded, for example jax in the shipped initial programs, resolve from the shared directory first. Two lower-trust principals are affected differently. Another local account on a shared host could plant such a file and gain code execution as the operator; whether such accounts and a shared /tmp exist is a deployment fact. An evaluated program can plant one and thereby persist into every later evaluation and run on the host. The affected resources are the operator's account and the integrity of later evaluations. Reviewer note: Parent review confirmed tempfile.NamedTemporaryFile(suffix=".py", delete=False) with no dir (evaluator.py:95) and that the file is run as [sys.executable, temp_file_path] (:148), which puts the temp directory first on sys.path before the wrapper's `import numpy`. evaluation.py changes the child's cwd, not TMPDIR.

**Claimed root cause.** Scripts and result files are created directly in the shared temp directory instead of a private directory, and the interpreters are started without isolated or safe-path mode, so the shared directory becomes an import location.

**Trace**

1. `entrypoint` `benchmarks/problems/circle_packing_26/evaluator.py:95` (run_with_timeout) — The wrapper script is created with NamedTemporaryFile in the default temp directory, which other principals can write to.
2. `propagation` `benchmarks/problems/circle_packing_26/evaluator.py:99` (run_with_timeout) — The generated script imports numpy, os, pickle and traceback by name.
3. `sink` `benchmarks/problems/circle_packing_26/evaluator.py:148` (run_with_timeout) — The script is run as [sys.executable, path], so its directory is sys.path[0] and those imports search the shared temp directory first.

**Evidence**

- `benchmarks/evaluation.py:28` — The child environment adds PYTHONNOUSERSITE and thread settings only; no PYTHONSAFEPATH or isolated mode.
- `benchmarks/problems/circle_packing_26/evaluator.py:144` — The results file is the predictable sibling '<wrapper path>.results' in the same shared directory.
- `benchmarks/problems/circle_packing_26/evaluator.py:166` — An existing results file is unpickled after an exit code of 0, whoever created it.
- `benchmarks/problems/kissing_number_11/evaluator.py:65` — In-process evaluators insert the program's directory at sys.path[0] before importing the program.
- `baselines/openevolve/openevolve/evaluator.py:259` — OpenEvolve creates each program file directly in the default temp directory, making it that program directory.
- `benchmarks/scientific_cases.py:36` — Sibling control for comparison: the scientific runner uses a private TemporaryDirectory for its script and outputs.

**Blockers**

- No bounded local observation was allowed in this run, so import of a file from the temp directory by the wrapper has not been observed.
- Whether evaluation hosts have other local accounts sharing a world-writable temp directory, and the values of fs.protected_regular and fs.protected_symlinks there, are deployment facts not visible in source.

**Local check (sandbox, dummy data).** In the no-network sandbox with python3 and numpy, create the directory <scratch>/t/tmp and the file <scratch>/t/tmp/pickle.py containing: import os / open(os.environ['POC_MARKER'], 'w').write(str(os.getpid())). From the repository root run the repository's own unmodified program: TMPDIR=<scratch>/t/tmp POC_MARKER=<scratch>/t/marker python3 benchmarks/evaluation.py circle_packing_26 benchmarks/problems/circle_packing_26/initial_program.py. Single observable: <scratch>/t/marker is created, showing that a file in the temp directory was imported in place of the standard-library module during a normal evaluation. The evaluation then reports score 0 because the stand-in module is empty.

**Owner-observed check.** Owner check on an evaluation host: run 'ls -ld "${TMPDIR:-/tmp}"' and 'getent passwd' to see whether the temp directory is world-writable and shared with other accounts, and 'sysctl fs.protected_regular fs.protected_symlinks'.

## `codeevolve-ckpt/pickle-load-on-resume`

**CodeEvolve unpickles the highest-numbered ckpt_N.pkl found in an output directory that evaluated programs can write**

CodeEvolve checkpoints are pickles under <out_dir>/island_<i>/ckpt/. On a resume (--load_ckpt -1 or a positive epoch) each island process calls pickle.load on ckpt_<epoch>.pkl. The epoch is taken from a directory listing: for -1, and also when a requested epoch is missing, the highest-numbered file name common to all island directories is used. An evaluated program (a plain subprocess with the full parent environment, which in this repo includes EVAL_LOG pointing into the run directory) can write a file such as ckpt_99999999.pkl into every island's ckpt directory; the framework never overwrites it, and the next resume executes its content inside the CodeEvolve island processes, after the evaluation that wrote it has timed out or been killed. Scope limits established from source: the load occurs only on an explicit resume; the repo glue always starts with --load_ckpt 0 (while writing a checkpoint every epoch), so the path is reached only when an operator later resumes a codeevolve_output directory by hand or uses CodeEvolve directly. CodeEvolve's README describes evaluation as sandboxed, but the evaluator applies only a timeout and a psutil monitor, so the program has the operator's uid and full filesystem access; the pickle adds a boundary crossing where the output directory is resumed on another host or account, or where the operator relies on the documented sandbox. Reviewer note: Parent review confirmed pkl.load in load_ckpt (utils/ckpt.py:114-115) and that loading is enabled only when --load_ckpt is not 0 (cli.py:125). This repository's glue passes --load_ckpt 0, so the default flow here does not reach the sink. A generated program already runs as the operator, so the boundary that matters is a checkpoint directory received from someone else and then resumed.

**Claimed root cause.** load_ckpt deserializes checkpoints with pickle from a directory shared with untrusted evaluated programs, with no integrity check, and checkpoint selection trusts file names found in that directory.

**Trace**

1. `entrypoint` `baselines/CodeEvolve/src/codeevolve/evaluator.py:298` (Evaluator.execute) — The evaluated program runs as a plain subprocess that inherits the environment and has no filesystem isolation, so it can write <out_dir>/island_<i>/ckpt/ckpt_<n>.pkl.
2. `propagation` `baselines/CodeEvolve/src/codeevolve/utils/cli_setup.py:162` (find_common_checkpoints) — On start-up the checkpoint candidates are whatever file names matching ckpt_(\d+)\.pkl exist in every island ckpt directory.
3. `propagation` `baselines/CodeEvolve/src/codeevolve/utils/cli_setup.py:189` (determine_checkpoint_to_load) — For --load_ckpt -1, or a requested epoch that is absent, the maximum epoch number found is selected.
4. `propagation` `baselines/CodeEvolve/src/codeevolve/evolution.py:1196` (_initialize_from_checkpoint) — Each island process calls load_ckpt(args['load_ckpt'], args['ckpt_dir']) when load_ckpt is non-zero.
5. `sink` `baselines/CodeEvolve/src/codeevolve/utils/ckpt.py:115` (load_ckpt) — pickle.load on the selected checkpoint file in the island process.

**Evidence**

- `baselines/CodeEvolve/src/codeevolve/utils/ckpt.py:115` — Bare pickle.load; no signature, MAC, ownership check or restricted unpickler.
- `baselines/CodeEvolve/src/codeevolve/utils/cli_setup.py:287` — Checkpoint directory is the fixed path <out_dir>/island_<id>/ckpt.
- `baselines/CodeEvolve/src/codeevolve/cli.py:125` — Checkpoint loading is active only when --load_ckpt is non-zero.
- `baselines/run_codeevolve.py:69` — The repo glue always passes --load_ckpt 0, so the glue itself never loads a checkpoint.
- `baselines/run_codeevolve.py:52` — The glue sets ckpt: 1, so pickled checkpoints are written every epoch into the run directory for later use.
- `baselines/run_baseline.sh:55` — EVAL_LOG=<run dir>/eval_log.jsonl is exported and inherited by evaluated programs, disclosing the run directory that contains codeevolve_output.
- `baselines/CodeEvolve/README.md:200` — Documentation claims sandboxed program execution; source shows only time and memory limits.

**Blockers**

- No target code was executed in this run; the marker-file observation for the pickle sink and the epoch-selection result have not been observed.
- Deployment fact not in source: whether any CodeEvolve output directory produced by this repo is ever resumed with a non-zero --load_ckpt (the glue never does).
- Deployment fact not in source: whether the resume happens under a different host, account or isolation level than the evaluation that could write the file. On one host and one uid the evaluated program already has equivalent write access to the framework's code.

**Local check (sandbox, dummy data).** In the no-network sandbox with baselines/CodeEvolve/src on PYTHONPATH and its dependencies present: (1) call codeevolve.utils.cli_setup.determine_checkpoint_to_load({'ckpt_3.pkl', 'ckpt_99999999.pkl'}, -1) and record the return value (expected 99999999). (2) Create scratch/ckpt/ckpt_99999999.pkl by pickling {'x': Obj()} where Obj.__reduce__ returns (open, ('scratch/poc_marker_codeevolve', 'w')), then call codeevolve.utils.ckpt.load_ckpt(99999999, 'scratch/ckpt'). Single observable: scratch/poc_marker_codeevolve exists after the call.

**Owner-observed check.** Owner check: confirm whether codeevolve_output directories are ever resumed (--load_ckpt -1 or N), on which host and account, and whether evaluated programs could write to island_*/ckpt during the original run.

## `codeevolve/config-template-verify-ssl-false`

**CodeEvolve's shipped model templates disable TLS certificate verification for the client that carries the API key and returns code to execute**

Both real-model configuration templates vendored under baselines/CodeEvolve/configs/templates/ set verify_ssl: False on every language-model role (exploration ensemble, exploitation ensemble, sampler auxiliary model). CodeEvolve passes each entry straight into OpenAILM, which builds httpx.AsyncClient(verify=self.verify_ssl) and gives it to AsyncOpenAI together with the operator's API_KEY and API_BASE. With verify=False the client accepts any certificate for any host. An operator who follows CodeEvolve's own instructions (export API_KEY and API_BASE for a hosted provider or gateway, run scripts/run.sh or pass --cfg_path with a template) therefore sends the bearer key over a connection that an on-path network attacker can terminate with a self-signed certificate. That attacker can read the API key and can also return forged completions; CodeEvolve applies completions as code edits and executes the result on the operator's host, so reply integrity is a code-execution boundary, not just a confidentiality one. The class default is verify_ssl: None, so the unsafe behavior comes from the templates, which are the only non-mock starting configurations the project ships. Scope condition: the benchmark path of this repository is not affected. baselines/run_codeevolve.py loads the qwen template but replaces all three model entries with dictionaries that have no verify_ssl key and sets API_BASE to http://localhost, so the flag never reaches a client there. The issue applies when the vendored CodeEvolve is run with its own templates or scripts/run.sh against an https endpoint. Reviewer note: Parent review confirmed verify_ssl: False on every model entry of configs/templates/config_qwen.yaml and config_gemini.yaml (:40-45) and that the value is passed to httpx.AsyncClient(verify=...) (lm/openai.py:97). This repository's CodeEvolve run talks to a local http endpoint, so it is not affected; the templates are.

**Claimed root cause.** The configuration templates opt every model client out of certificate verification (verify_ssl: False), and the loader forwards that value to httpx without a warning, an allow-list of hosts, or a requirement that the endpoint be loopback.

**Trace**

1. `entrypoint` `baselines/CodeEvolve/configs/templates/config_gemini.yaml:40` (EXPLORATION_ENSEMBLE) — Template model entry carries verify_ssl: False (same on lines 42, 43, 45, and in config_qwen.yaml lines 40, 42, 44); the network peer of this client is the lower-trust party whose certificate is accepted unchecked.
2. `propagation` `baselines/CodeEvolve/src/codeevolve/cli.py:121` (main) — API_BASE and API_KEY are read from the operator's environment (validate_environment, utils/cli_setup.py lines 43-44) and stored in args.
3. `propagation` `baselines/CodeEvolve/src/codeevolve/evolution.py:1003` (_create_ensembles) — The EXPLORATION_ENSEMBLE list from the YAML is passed as models_cfg to OpenAIEnsemble with the operator's api_key and api_base (exploitation ensemble and SAMPLER_AUX_LM take the same route, line 1042 and prompt/sampler.py line 122).
4. `propagation` `baselines/CodeEvolve/src/codeevolve/lm/openai.py:324` (_create_lm_from_config) — OpenAILM(**model_cfg, api_key=api_key, api_base=api_base): the verify_ssl key from the template becomes a constructor argument without validation.
5. `propagation` `baselines/CodeEvolve/src/codeevolve/lm/openai.py:97` (OpenAILM.__post_init__) — httpx.AsyncClient(verify=self.verify_ssl) is created with verify=False and installed as the AsyncOpenAI http_client together with the API key and base URL (lines 99-101).
6. `sink` `baselines/CodeEvolve/src/codeevolve/lm/openai.py:132` (OpenAILM.generate) — chat.completions.create sends the bearer API key over the unverified TLS connection and returns the peer's reply, which the evolution loop turns into program edits that are then executed.

**Evidence**

- `baselines/CodeEvolve/configs/templates/config_qwen.yaml:40` — The second real-model template also sets verify_ssl: False (lines 40, 42, 44).
- `baselines/CodeEvolve/scripts/run.sh:17` — CodeEvolve's own run script points CFG_PATH at configs/templates/config_qwen.yaml unchanged.
- `baselines/CodeEvolve/README.md:275` — Documentation says API_BASE may be a hosted provider or gateway, i.e. a remote https endpoint is an expected deployment.
- `baselines/CodeEvolve/src/codeevolve/lm/openai.py:71` — Class default is verify_ssl: Optional[bool] = None, so verification is disabled by the template value, not by the code default.
- `baselines/CodeEvolve/src/codeevolve/lm/openai.py:502` — The embedding client has the same verify=self.verify_ssl construction and would be affected by an EMBEDDING entry with the same flag.
- `baselines/run_codeevolve.py:38` — Strongest in-repo mitigation: this repository's glue replaces the template's three model entries with a dictionary that has no verify_ssl key (lines 38-47) and uses http://localhost as API_BASE (line 60), so its benchmark runs never use the flag.

**Blockers**

- No bounded local observation was made: this run forbids executing target code, and httpx/openai are not installed on the audit host. Whether the pinned openai==3.37.0 client uses the supplied http_client unchanged, and whether httpx==0.28.1 treats verify=False as CERT_NONE with hostname checking off, must be observed.
- Deployment fact: the flag only matters when an operator runs the vendored CodeEvolve with its own templates or scripts/run.sh against an https API_BASE on a network path an attacker can intercept. The path this repository documents (baselines/run_baseline.sh -> baselines/run_codeevolve.py) overrides the affected entries and talks to a loopback HTTP server.

**Local check (sandbox, dummy data).** Inside the no-network sandbox, with the baselines/venv_codeevolve packages mounted read-only and loopback only: (1) generate a throwaway self-signed certificate in scratch and start an HTTPS server on 127.0.0.1:<port> that records the Authorization header of POST /v1/chat/completions and returns a minimal fixed chat-completion JSON; (2) yaml.safe_load baselines/CodeEvolve/configs/templates/config_gemini.yaml and call codeevolve.lm.openai._create_lm_from_config(cfg['EXPLORATION_ENSEMBLE'][0], api_key='DUMMY-KEY-MARKER', api_base='https://127.0.0.1:<port>/v1'), then await .generate([{'role': 'user', 'content': 'x'}]) once. Single observable: the server log contains 'Bearer DUMMY-KEY-MARKER' and generate() returns the fixed content with no certificate error. Control: repeat with the same entry after deleting its verify_ssl key; the call must fail with a certificate verification error and the server must not log the marker. Limits: one request per case, 30 s wall clock, no external hosts.

**Owner-observed check.** Owner-observed: list the CodeEvolve configuration files actually used for runs outside baselines/run_codeevolve.py (for example copies of config_qwen.yaml or config_gemini.yaml) and check whether any model entry still carries verify_ssl: False while API_BASE is an https URL that is not loopback.

## `openevolve-api/shared-tempdir-module-path`

**OpenEvolve library API writes the evaluator module into the shared temp dir and adds that dir to sys.path of controller and workers**

run_evolution() uses a private mkdtemp directory only when output_dir is None and cleanup is True. When the caller passes output_dir or cleanup=False and supplies the evaluator as a callable or a code string, the evaluator pickle, the generated wrapper module and the initial program are written straight into tempfile.gettempdir(). The controller's Evaluator and every worker's Evaluator then insert the evaluator file's directory, which is now the world-writable temp dir, at sys.path[0] (never removed) and import the module from there, with its bytecode cache under <tempdir>/__pycache__. Consequences for another local user of the host: (1) any later import of a not-yet-loaded top-level module in the controller or a worker, including modules resolved while unpickling a cloudpickled evaluator and modules imported by evolved programs that the evaluator loads in-process, is resolved from the temp dir first; (2) if that user owns a pre-created <tempdir>/__pycache__, they can swap the cached .pyc of the evaluator module (source mtime and size are readable) before worker processes import it. Either way their code runs as the operator. The files themselves are created with default umask (world-readable) but cannot be replaced by another user in a sticky temp dir, and their names (uuid4 hex) cannot be pre-created; the evaluated program, which has the operator's uid, can overwrite the pickle, but in this flow it already runs in the worker, so that is not a separate escalation. The repo glue does not use this API (it drives the CLI with a file evaluator), so this affects direct users of the vendored library. Reviewer note: Parent review confirmed api.py falls back to tempfile.gettempdir() for the evaluator module (:359-362) and that Evaluator._load_evaluation_function inserts that directory at sys.path[0] (evaluator.py:86-89). The file names carry 8 random hex characters, so the claim rests on the import path, not on predicting a file name. This library API is not used by this repository's glue scripts.

**Claimed root cause.** api._prepare_evaluator/_prepare_program fall back to the shared system temp directory for executable module files when no private temp_dir was created, and Evaluator._load_evaluation_function unconditionally prepends the evaluator file's directory to sys.path.

**Trace**

1. `entrypoint` `baselines/openevolve/openevolve/api.py:157` (_run_evolution_async) — A private mkdtemp directory is created only when output_dir is None and cleanup is true; otherwise temp_dir stays None.
2. `propagation` `baselines/openevolve/openevolve/api.py:360` (_prepare_evaluator) — With temp_dir None the wrapper/evaluator module is written as <gettempdir()>/evaluator_<8 hex>.py (the pickle likewise at lines 329-333).
3. `propagation` `baselines/openevolve/openevolve/controller.py:138` (OpenEvolve.__init__) — The controller builds an Evaluator for that file; workers do the same lazily (process_parallel.py:131).
4. `sink` `baselines/openevolve/openevolve/evaluator.py:89` (Evaluator._load_evaluation_function) — sys.path.insert(0, eval_dir) with eval_dir equal to the shared temp dir, followed by exec_module at line 98 which reads/writes the bytecode cache under <tempdir>/__pycache__.

**Evidence**

- `baselines/openevolve/openevolve/api.py:329` — temp_dir falls back to tempfile.gettempdir() for the evaluator pickle.
- `baselines/openevolve/openevolve/api.py:332` — Pickle is created with open(path, 'wb') and default permissions in that directory.
- `baselines/openevolve/openevolve/api.py:255` — Same fallback for the initial program file.
- `baselines/openevolve/openevolve/api.py:347` — The wrapper unpickles the evaluator once per process, after the temp dir is already first on sys.path.
- `baselines/openevolve/openevolve/evaluator.py:88` — The directory is added whenever it is not yet on sys.path and is never removed.
- `baselines/openevolve/openevolve/process_parallel.py:131` — Each worker process constructs its own Evaluator from the same file path, re-importing the module (and its cached bytecode) later than the controller.
- `baselines/run_openevolve.py:49` — The repo glue runs the CLI entry point with a file evaluator and does not call openevolve.api.

**Blockers**

- No target code was executed in this run; neither the sys.path state nor a shadowed import has been observed.
- Deployment fact not in source: whether the vendored openevolve.api is used at all with a callable or code-string evaluator together with output_dir or cleanup=False, on a host where another account can write to the temp directory.
- Runtime fact: which modules are imported after the insertion in the controller and workers, and whether bytecode caching is enabled (PYTHONDONTWRITEBYTECODE / PYTHONPYCACHEPREFIX), are not source-visible.

**Local check (sandbox, dummy data).** In the no-network sandbox with baselines/openevolve on PYTHONPATH and its dependencies present, set TMPDIR=scratch/sharedtmp and create scratch/sharedtmp/colorsys.py containing only: open('<abs scratch>/poc_marker_api_path', 'w').close(). In one Python process: p = openevolve.api._prepare_evaluator("def evaluate(program_path):\n    return {'score': 1.0}\n", None, []); from openevolve.config import EvaluatorConfig; from openevolve.evaluator import Evaluator; Evaluator(EvaluatorConfig(), p); then 'import colorsys'. Observables: os.path.dirname(p) == tempfile.gettempdir(), sys.path[0] == tempfile.gettempdir(), and the single decisive one: scratch/poc_marker_api_path exists. Also record whether scratch/sharedtmp/__pycache__/evaluator_*.pyc was created.

**Owner-observed check.** Owner check: confirm whether any workflow calls openevolve.api.run_evolution / evolve_function / evolve_algorithm / evolve_code with output_dir set or cleanup=False on a multi-user host.

## `openevolve-evaluator/shared-tmp-program-import-path`

**OpenEvolve places candidate programs in the shared temp dir, which the benchmark evaluators then put first on sys.path**

In the repo's OpenEvolve flow every candidate program is written to the system temp directory itself (tempfile.NamedTemporaryFile with no dir, e.g. /tmp/tmpXXXXXXXX.py). The glue evaluator hands that path to the shared scoring harness, and the in-process problem evaluators insert the program's directory at sys.path[0], import the program and call its entry function while that entry is still present. The directory is therefore the world-writable temp dir: any top-level module the program imports that is not already loaded in the scorer process (the evaluator pre-imports numpy and scipy; other stdlib or third-party names are not) is resolved from the temp dir before the standard library and site-packages. Another local user of the host can pre-place files such as /tmp/<module>.py and have them executed as the operator inside the scorer process, which carries the operator's full environment. This needs no cooperation from the LLM beyond importing a common module. CodeEvolve and ShinkaEvolve do not share the problem because they place the program in a private temporary directory or under the results directory. Reviewer note: Parent review confirmed NamedTemporaryFile(suffix=..., delete=False) with no dir in Evaluator.evaluate_program (openevolve/evaluator.py:259) and that in-process benchmark evaluators insert the program's directory at sys.path[0] before importing it.

**Claimed root cause.** OpenEvolve's Evaluator.evaluate_program creates the importable program file directly in the shared system temp directory instead of a private directory, and the consumer adds the file's directory to the import path.

**Trace**

1. `entrypoint` `baselines/openevolve/openevolve/evaluator.py:259` (Evaluator.evaluate_program) — Candidate program is written with tempfile.NamedTemporaryFile(suffix=..., delete=False) and no dir argument, so it lands directly in tempfile.gettempdir().
2. `propagation` `baselines/openevolve/openevolve/evaluator.py:270` (Evaluator.evaluate_program) — The temp file path is passed to the configured evaluate function.
3. `propagation` `baselines/openevolve_evaluator.py:11` (evaluate) — The glue evaluator forwards the path to the shared harness.
4. `propagation` `benchmarks/evaluation.py:44` (evaluate) — The harness starts run_evaluator.py with the resolved program path and the full parent environment.
5. `propagation` `benchmarks/run_evaluator.py:12` (module) — The problem evaluator's evaluate(program_path) is called in the scorer process.
6. `sink` `benchmarks/problems/min_max_distance_14_3d/evaluator.py:34` (evaluate) — sys.path.insert(0, dirname(program_path)) followed by __import__ and the entry-function call; with an OpenEvolve program this puts the shared temp dir first on the import path while program imports are resolved.

**Evidence**

- `baselines/openevolve/openevolve/evaluator.py:259` — No dir= argument and no private directory: the program file is created in the shared temp dir.
- `benchmarks/problems/min_max_distance_14_3d/evaluator.py:35` — The program is imported and (line 37) executed while its directory is at sys.path[0]; removal happens only in the finally block at line 43-45.
- `benchmarks/evaluation.py:46` — The scorer process inherits the operator's whole environment (env={**os.environ, ...}), so code loaded from the temp dir runs with it.
- `baselines/CodeEvolve/src/codeevolve/evaluator.py:269` — Sibling control: CodeEvolve creates a private TemporaryDirectory and writes the program inside it (lines 276-278).
- `baselines/ShinkaEvolve/shinka/core/async_runner.py:2606` — Sibling control: ShinkaEvolve stores the program under <results_dir>/gen_N, not in a shared directory.

**Blockers**

- No target code was executed in this run; the import-resolution observation has not been made.
- Deployment fact not in source: whether the benchmark host has other local users (or other lower-trust processes) able to create files in the temp directory used by the run, and whether TMPDIR points at a shared directory.
- Runtime fact: which top-level modules are not yet in sys.modules of the scorer process when the program is imported depends on the installed numpy/scipy versions and on what the generated program imports.

**Local check (sandbox, dummy data).** In the no-network sandbox with numpy and scipy available, set TMPDIR=scratch/sharedtmp (stand-in for the shared temp dir). As the stand-in for the other user, create scratch/sharedtmp/colorsys.py containing only: open('<abs scratch>/poc_marker_tmp_import', 'w').close(). Create the program exactly as OpenEvolve does, with tempfile.NamedTemporaryFile(suffix='.py', delete=False), containing: 'import colorsys\nimport numpy as np\ndef min_max_dist_dim3_14():\n    return np.zeros((14, 3))'. Run: python benchmarks/run_evaluator.py benchmarks/problems/min_max_distance_14_3d <that temp path>. Single observable: scratch/poc_marker_tmp_import exists. Control: the same run without colorsys.py in the temp dir creates no marker.

**Owner-observed check.** Owner check: on the hosts used for baselines/run_baseline.sh openevolve runs, confirm whether other accounts can write to the directory returned by tempfile.gettempdir() for the run's user.

## `openevolve-visualizer/manual-answer-unauthenticated-reply-injection`

**OpenEvolve manual-mode endpoints let any client that can reach the visualizer port supply the LLM reply that is then executed**

When OpenEvolve runs in manual mode, each LLM call is written as a task file and the run waits for a matching answer file. The visualizer's manual blueprint lists pending task ids, returns each prompt, and accepts an answer by form POST, all without authentication and without any Origin or Host validation. The answer text is returned to the framework as the model reply, converted into a child program and passed to the evaluator, which runs it under the operator's account.

The lower-trust principal is anyone other than the operator who can read responses from the port. Source shows three: (1) another local user on a shared run host, since the default bind is loopback, which every local account can reach; (2) a network client, if the operator starts the visualizer with a non-loopback --host; (3) a web page in the operator's browser that uses DNS rebinding, since any Host header is accepted. Each can list task ids, read the prompts, and post an answer. The first answer written wins, so the operator's own answer for that task is ignored.

A blind cross-site form POST alone does not work: the task id is a random uuid4 and the listing is not readable cross-origin. That narrower claim was refuted from source and is not part of this candidate.

Preconditions: llm.manual_mode must be enabled (it is off by default and is not set by baselines/run_openevolve.py), and the visualizer must be running with --path pointing at the live run directory. Reviewer note: Parent review confirmed api_tasks lists task ids and api_task_answer writes the answer with no authentication, Origin or Host check (scripts/manual.py:136-142,159-177), and that manual mode is opt-in (config.py:138 default False; not set by baselines/run_openevolve.py). With manual mode off there is no consumer for the answer.

**Claimed root cause.** The manual blueprint treats reachability of the port as authorization. The only check on the answer route is that the task file exists, and the task id needed to pass it is published by the unauthenticated listing route on the same server. No token, Origin check or Host allowlist binds the answer to the operator.

**Trace**

1. `entrypoint` `baselines/openevolve/scripts/manual.py:136` (create_manual_blueprint.api_tasks) — GET /manual/api/tasks returns the id, creation time and model of every pending task to any caller.
2. `propagation` `baselines/openevolve/scripts/manual.py:159` (create_manual_blueprint.api_task_answer) — POST /manual/api/tasks/<task_id>/answer is registered with no authentication, token, Origin or Host check.
3. `propagation` `baselines/openevolve/scripts/manual.py:165` (create_manual_blueprint.api_task_answer) — The answer is read from request.form, so a urlencoded or multipart body is accepted.
4. `propagation` `baselines/openevolve/scripts/manual.py:173` (create_manual_blueprint.api_task_answer) — The only gate: the file <queue>/<task_id>.json must exist.
5. `propagation` `baselines/openevolve/scripts/manual.py:125` (_write_answer) — The answer is written atomically to <queue>/<task_id>.answer.json.
6. `propagation` `baselines/openevolve/openevolve/llm/openai.py:301` (OpenAILLM._manual_wait_for_answer) — The polling loop reads and parses the answer file as soon as it exists.
7. `propagation` `baselines/openevolve/openevolve/llm/openai.py:309` (OpenAILLM._manual_wait_for_answer) — The answer string is returned as the model reply.
8. `propagation` `baselines/openevolve/openevolve/process_parallel.py:208` (_run_iteration_worker) — The reply becomes llm_response in the iteration worker.
9. `propagation` `baselines/openevolve/openevolve/process_parallel.py:312` (_run_iteration_worker) — The reply is parsed into new program code (full rewrite; the diff path applies blocks at line 283).
10. `sink` `baselines/openevolve/openevolve/process_parallel.py:364` (_run_iteration_worker) — The resulting child code is passed to the evaluator, which executes it under the operator's account.

**Evidence**

- `baselines/openevolve/scripts/manual.py:141` — The listing response includes each pending task id, which is the only secret the answer route depends on.
- `baselines/openevolve/scripts/manual.py:152` — The task detail route returns the full display prompt to any caller.
- `baselines/openevolve/scripts/visualizer.py:17` — The Flask app is created with no secret key, trusted-host list or request hook; no access control exists elsewhere in scripts/.
- `baselines/openevolve/scripts/visualizer.py:194` — The manual blueprint is registered unconditionally on every visualizer run.
- `baselines/openevolve/scripts/visualizer.py:207` — Strongest visible control: the default bind host is 127.0.0.1. It can be overridden with --host.
- `baselines/openevolve/openevolve/llm/openai.py:269` — Second visible control: the task id is a uuid4, so it cannot be guessed, only read from the listing.
- `baselines/openevolve/openevolve/llm/openai.py:299` — The wait loop accepts the answer file on existence alone, so the first writer wins.
- `baselines/openevolve/openevolve/config.py:138` — Manual mode defaults to False.
- `baselines/openevolve/openevolve/controller.py:224` — The controller creates the queue directory only when llm.manual_mode is enabled.
- `baselines/run_openevolve.py:37` — The repository's OpenEvolve launcher writes an llm config with no manual_mode key, so this repository's default runs do not enable manual mode.

**Blockers**

- No target code was executed in this run, so acceptance of a request with a foreign Host and Origin and a form content type was not observed.
- Manual mode is opt-in and is not enabled by baselines/run_openevolve.py; whether any operator workflow enables llm.manual_mode alongside the visualizer is a deployment fact.
- Local-user path: whether the run host is shared with other accounts is a deployment fact.
- Network path: requires the operator to pass a non-loopback --host; the default is 127.0.0.1.
- DNS-rebinding path: depends on the operator's browser. Browsers that enforce local-network-access permission for requests from public pages to loopback addresses block or prompt for it; that behaviour is not visible in source.
- Flask and Werkzeug are not vendored; the absence of default Host validation must be observed on the pinned Flask==3.1.3 / Werkzeug==3.1.9.

**Local check (sandbox, dummy data).** In the no-network sandbox with Flask installed, create scratch/run/manual_tasks_queue/11111111-1111-4111-8111-111111111111.json containing {"id": "11111111-1111-4111-8111-111111111111", "created_at": "t", "model": "dummy", "display_prompt": "dummy prompt"}. Set EVOLVE_OUTPUT=scratch/run, add baselines/openevolve/scripts to sys.path, import the module visualizer (do not run it as __main__) and use visualizer.app.test_client(). Send every request with no cookies and with headers Host: rebind.example:8080 and Origin: http://rebind.example:8080. Step 1: GET /manual/api/tasks and expect status 200 with the dummy id in the JSON body. Step 2: POST /manual/api/tasks/11111111-1111-4111-8111-111111111111/answer with Content-Type application/x-www-form-urlencoded and body answer=SENTINEL_ANSWER_7f3a; expect status 200 and body {"ok": true}. Step 3: POST the same body to /manual/api/tasks/00000000-0000-4000-8000-000000000000/answer and expect 404. Single deciding observable: after step 2 the file scratch/run/manual_tasks_queue/11111111-1111-4111-8111-111111111111.answer.json exists and its "answer" field equals SENTINEL_ANSWER_7f3a. No evaluator is run and no generated code is executed.

**Owner-observed check.** Owner check: confirm whether any run enables llm.manual_mode, whether the visualizer is ever started with a non-loopback --host, and whether the run host has other interactive accounts. For the browser path, confirm which browsers operators use and whether they prompt for local network access.

## `openevolve-visualizer/sidebar-innerhtml-unescaped-llm-text`

**OpenEvolve visualizer writes LLM replies, prompts and artifacts into the page as HTML without escaping**

The visualizer sidebar escapes program code but not the Prompts tab. The selected prompt entry, which can be the system prompt, the user prompt, the raw model reply ('responses') or the artifacts JSON, is placed inside a <pre> element by string interpolation and assigned to innerHTML. Markup in that text is parsed by the browser, so an inline event handler such as an onerror attribute on an img tag runs script in the visualizer's origin.

The source is the lowest-trust data in the system. The raw model reply is logged verbatim with each program (prompt logging is on by default), the user prompt quotes earlier generated code and program output, and the artifacts entry is the tail of the evaluated program's stdout in this repository's glue. The victim is the operator's browser, which may be on a different machine from the run host (for example through a forwarded port), or anyone who opens a checkpoint directory produced by someone else.

Reaching the main sink needs ordinary inspection steps: select a node, open the Prompts tab and choose the 'user', 'responses' or 'artifacts' entry. The choice is remembered in localStorage, and once the Prompts tab is active in a page session, hovering over any node re-renders it with that node's text.

Variants of the same missing escape: metric names are interpolated raw into the sidebar metrics table and the list view, and the list view is rendered on every data load without a click; program and parent ids are interpolated raw into text and attribute positions. Metric names are program-influenced in this repository's glue; ids are framework-generated unless the checkpoint files come from another party.

Script running in the visualizer origin can call every same-origin route, including the manual-mode answer route described under openevolve-visualizer/manual-answer-unauthenticated-reply-injection. Reviewer note: Parent review confirmed `<pre class="sidebar-pre">${promptVal ?? ''}</pre>` at static/js/sidebar.js:421 with no escapeHtml call, while the code and diff tabs in the same file do escape (:353-369).

**Claimed root cause.** The front-end builds HTML by template-string interpolation and assigns it to innerHTML. Escaping is applied only to program code and diff lines; prompt values, artifacts, metric names and ids are interpolated raw. The server sends no Content-Security-Policy that would stop inline handlers.

**Trace**

1. `entrypoint` `baselines/openevolve/openevolve/process_parallel.py:208` (_run_iteration_worker) — The raw model reply is received as llm_response.
2. `propagation` `baselines/openevolve/openevolve/process_parallel.py:810` (ProcessParallelController.run_evolution) — The reply is passed verbatim to database.log_prompt as the responses list.
3. `propagation` `baselines/openevolve/openevolve/database.py:2818` (ProgramDatabase.log_prompt) — The responses list is stored on the prompt record for the program.
4. `propagation` `baselines/openevolve/openevolve/database.py:973` (ProgramDatabase._save_program) — The prompt record is written into the program's checkpoint JSON under 'prompts'.
5. `propagation` `baselines/openevolve/scripts/visualizer.py:68` (load_evolution_data) — The visualizer loads the program JSON; only metric values are sanitised.
6. `propagation` `baselines/openevolve/scripts/visualizer.py:124` (data) — GET /api/data returns the nodes, including prompts and artifacts, as JSON.
7. `propagation` `baselines/openevolve/scripts/static/js/main.js:122` (fetchAndRender) — The page fetches /api/data every two seconds and stores the nodes.
8. `propagation` `baselines/openevolve/scripts/static/js/sidebar.js:381` (showSidebarContent.renderSidebarTabContent) — Each prompt sub-entry (system, user, responses) is placed in promptMap unchanged.
9. `propagation` `baselines/openevolve/scripts/static/js/sidebar.js:421` (showSidebarContent.renderSidebarTabContent) — The selected value is interpolated into a <pre> element with no escaping.
10. `sink` `baselines/openevolve/scripts/static/js/sidebar.js:468` (showSidebarContent) — The assembled string is assigned to sidebarContent.innerHTML (also to tabContent.innerHTML at lines 491 and 508).

**Evidence**

- `baselines/openevolve/scripts/static/js/sidebar.js:369` — Sibling control: the Code tab passes d.code through escapeHtml, showing the escape exists and is omitted for prompts.
- `baselines/openevolve/scripts/static/js/sidebar.js:394` — The artifacts JSON string is added to the same unescaped promptMap.
- `baselines/openevolve/scripts/static/js/sidebar.js:414` — Artifacts are re-serialised with JSON.stringify, which does not escape '<'.
- `baselines/openevolve/scripts/static/js/sidebar.js:508` — Clicking a tab assigns the unescaped tab content to innerHTML.
- `baselines/openevolve/scripts/static/js/graph.js:265` — Hovering over a graph node calls showSidebarContent, so rendering happens without a click once the Prompts tab is the active tab.
- `baselines/openevolve/scripts/static/js/main.js:52` — formatMetrics interpolates metric names raw into a table row used in the sidebar.
- `baselines/openevolve/scripts/static/js/list.js:113` — The list view interpolates metric names raw.
- `baselines/openevolve/scripts/static/js/list.js:129` — The list view assigns that string to innerHTML; renderNodeList runs on every data load (main.js:83).
- `baselines/openevolve/scripts/static/js/sidebar.js:294` — The program id is concatenated raw into an href attribute.
- `baselines/openevolve/scripts/visualizer.py:93` — Strongest server-side control: only metric values are replaced when they are not finite numbers; keys and all text fields pass through.
- `baselines/openevolve/openevolve/config.py:326` — DatabaseConfig.log_prompts defaults to True, so prompts and replies are stored by default.
- `baselines/openevolve_evaluator.py:13` — This repository's evaluator returns the program's output tail and error text as artifacts.
- `benchmarks/evaluation.py:52` — Metric names are parsed from the last @@METRICS@@ line of the evaluator child's stdout, which the evolved program can print.

**Blockers**

- No target code or browser was run, so script execution from a prompt value was not observed.
- The page imports d3 from https://d3js.org at load time (templates/index.html:6); in a no-network sandbox the module graph fails unless a local d3 v7 copy is served by request interception.
- Operator interaction is required for the main path: opening the Prompts tab and selecting a non-system entry.
- Metric-name variant: whether OpenEvolve's evaluator (openevolve/evaluator.py, peer-owned) preserves arbitrary metric keys into the checkpoint was not traced.
- Impact depends on what else the operator's browser trusts at the visualizer origin and on whether the browser runs on a different machine from the run host; both are deployment facts.

**Local check (sandbox, dummy data).** In the no-network sandbox, create scratch/ckpt/checkpoint_1/metadata.json with {"islands": [["p1"]], "archive": []} and scratch/ckpt/checkpoint_1/programs/p1.json with {"id": "p1", "code": "x = 1", "generation": 0, "parent_id": null, "metrics": {"combined_score": 1.0}, "metadata": {}, "prompts": {"diff_user": {"system": "s", "user": "u", "responses": ["<img src=x onerror=\"document.title='XSS_MARKER_A'\">"]}}}. Start baselines/openevolve/scripts/visualizer.py on isolated loopback with --path scratch/ckpt. Open / in a headless browser with request interception that serves a local d3.v7.min.js for https://d3js.org/d3.v7.min.js and blocks every other external host. Click the List tab, click the single row, click the Prompts tab in the sidebar and choose 'diff_user - responses' in the select box. Single deciding observable: document.title equals XSS_MARKER_A (equivalently, document.querySelector('pre.sidebar-pre img') is not null).

**Owner-observed check.** Owner check: confirm how operators view the visualizer (same host, forwarded port, or checkpoints copied or shared between people) and whether manual mode is ever active on the same origin.

## `openevolve-visualizer/static-export-inline-script-json-breakout`

**OpenEvolve static export embeds run data in an inline script without HTML-safe encoding, so '</script>' in generated text injects markup**

The --static-output option writes a self-contained index.html. It serialises all programs, prompts, model replies and artifacts with jsonify and concatenates the result into an inline <script> element. JSON serialisation does not escape '<'. The HTML parser ends a script element at the first '</script' regardless of JavaScript string context, so any string value containing that sequence closes the data script, and whatever follows is parsed as HTML.

Program code, model replies and program output are all LLM-derived, so a generated program or reply that contains '</script><script>...' runs script when the exported page is opened. No click is needed. The export is meant to be served or shared (the tool prints a hint to serve it with a web server), so the affected principal is whoever opens the export, in whatever origin hosts it.

The same defect also corrupts the export for benign programs that merely contain the text '</script>'. Reviewer note: Parent review confirmed run_static_export builds `<script>window.STATIC_DATA = {data_json};</script>` from jsonify(data).get_data(as_text=True) (scripts/visualizer.py:158-160). Whether that serializer leaves `</script>` intact is behaviour of the installed Flask (pinned 3.1.3, not vendored) and must be observed.

**Claimed root cause.** run_static_export builds an inline script by string concatenation of jsonify output. That output is plain JSON, not the HTML-safe form produced by the tojson template filter, so '<', '>' and '&' are not escaped for the script-data context.

**Trace**

1. `entrypoint` `baselines/openevolve/openevolve/process_parallel.py:208` (_run_iteration_worker) — The raw model reply is received; it becomes program code and is also logged as a response.
2. `propagation` `baselines/openevolve/openevolve/database.py:973` (ProgramDatabase._save_program) — Program code, prompts and replies are written to the checkpoint program JSON.
3. `propagation` `baselines/openevolve/scripts/visualizer.py:68` (load_evolution_data) — The exporter loads each program JSON; text fields are not altered.
4. `propagation` `baselines/openevolve/scripts/visualizer.py:158` (run_static_export) — The dataset is serialised with jsonify(data).get_data(as_text=True).
5. `propagation` `baselines/openevolve/scripts/visualizer.py:159` (run_static_export) — The JSON text is concatenated into an inline <script> element.
6. `propagation` `baselines/openevolve/scripts/visualizer.py:172` (run_static_export) — The script element is spliced into the index.html template text.
7. `sink` `baselines/openevolve/scripts/visualizer.py:177` (run_static_export) — The resulting HTML is written to <static_output>/index.html, where a browser parses the injected markup.

**Evidence**

- `baselines/openevolve/scripts/visualizer.py:11` — Only render_template and jsonify are imported; no HTML-safe JSON helper is used anywhere in the file.
- `baselines/openevolve/scripts/visualizer.py:93` — Strongest visible control: sanitisation replaces non-finite metric values only; no text field is encoded.
- `baselines/openevolve/scripts/visualizer.py:189` — The export log message tells the operator to serve the directory with a web server, so the output is intended to be opened over HTTP.
- `baselines/openevolve/scripts/static/js/main.js:118` — The front-end consumes window.STATIC_DATA, confirming the inline script is the data channel for exported pages.
- `baselines/requirements_openevolve_shinkaevolve.txt:22` — Flask is pinned to 3.1.3 here; it is not vendored, so the serialiser was not read in source.

**Blockers**

- No target code was executed, so the exported file was not produced or inspected.
- Flask is not vendored in the repository and not installed on the audit host. The claim that jsonify output leaves '<' unescaped rests on Flask's documented JSON provider behaviour and must be observed on the pinned Flask==3.1.3.
- Impact depends on where exports are hosted and who opens them, which is a deployment fact.

**Local check (sandbox, dummy data).** In the no-network sandbox with Flask==3.1.3 installed, create scratch/ckpt/checkpoint_1/metadata.json with {"islands": [["p1"]], "archive": []} and scratch/ckpt/checkpoint_1/programs/p1.json with {"id": "p1", "code": "s = '</script><script>document.title=\"XSS_MARKER_B\"</script>'", "generation": 0, "parent_id": null, "metrics": {"combined_score": 1.0}, "metadata": {}}. Add baselines/openevolve/scripts to sys.path, import the module visualizer (do not run it as __main__) and call visualizer.run_static_export(argparse.Namespace(path='scratch/ckpt', static_output='scratch/export')). Parse scratch/export/index.html with Python's html.parser and collect the text of every script element. Single deciding observable: one script element's text is exactly document.title="XSS_MARKER_B" (that is, the marker appears as its own script element instead of inside the STATIC_DATA string). If the file instead contains \u003c/script in place of </script, the candidate is refuted for this Flask version.

**Owner-observed check.** Owner check: confirm whether static exports are produced and where they are published or shared.

## `shinka-bandit-state/pickle-load-on-resume`

**ShinkaEvolve runner unpickles results_dir/bandit_state.pkl on resume, a file the evaluated program can write**

When a ShinkaEvolve run is resumed (same results_dir, programs.sqlite with last_iteration > 0) and LLM bandit selection is enabled (framework default 'ucb'), the runner process loads <results_dir>/bandit_state.pkl with pickle.load. Evaluated programs are stored and executed under the same results_dir (<results_dir>/gen_N/main.py) as plain subprocesses, so LLM-generated code can write that file; whatever it pickles is executed inside the runner process at the next resume, after the evaluation job that wrote it has ended or been killed, and on whatever host or account performs the resume. Load failures are swallowed with a warning, so the run continues normally. Scope limits established from source: the load happens once at resume start-up, never periodically; the runner overwrites the file every 5 completed generations and at normal end, so a planted file survives only if it is the last write; the repo glue disables the bandit (llm_dynamic_selection: None) and uses a fresh timestamped directory, so this is reachable with the vendored framework's own defaults or examples, not through baselines/run_baseline.sh. With the local job backend the evaluated program already has the operator's uid and full filesystem access, so the pickle adds a boundary crossing only where the program's writes are otherwise confined to the results tree (the slurm_docker backend with the results directory mounted) or where a results directory is resumed on another host or account. Reviewer note: Parent review confirmed pickle.load in load_state (llm/prioritization.py:218-220) and the gate in _load_bandit_state: it returns early when llm_selection is None (core/async_runner.py:627-628). This repository's glue sets llm_dynamic_selection to None (baselines/run_shinkaevolve.py:46), so the default flow here does not reach the sink. A generated program already runs as the operator, so the boundary that matters is a results directory received from someone else and then resumed.

**Claimed root cause.** BanditBase.load_state deserializes run state with pickle from the results directory, which is also the working tree of untrusted evaluated programs, with no integrity check; the state itself is only arrays and scalars and does not need pickle.

**Trace**

1. `entrypoint` `baselines/ShinkaEvolve/shinka/launch/local.py:105` (submit) — Evaluation job for an LLM-generated program is started as a plain subprocess with a copy of the parent environment and no filesystem isolation; the program file is <results_dir>/gen_N/main.py, so it can locate and write <results_dir>/bandit_state.pkl.
2. `propagation` `baselines/ShinkaEvolve/shinka/core/async_runner.py:1223` (ShinkaEvolveRunner._setup_async) — A later start with the same results_dir is treated as a resume when programs.sqlite exists and last_iteration > 0.
3. `propagation` `baselines/ShinkaEvolve/shinka/core/async_runner.py:1240` (ShinkaEvolveRunner._setup_async) — The resume branch calls _load_bandit_state().
4. `propagation` `baselines/ShinkaEvolve/shinka/core/async_runner.py:633` (ShinkaEvolveRunner._load_bandit_state) — If llm_selection is not None and <results_dir>/bandit_state.pkl exists, load_state is called on that path.
5. `sink` `baselines/ShinkaEvolve/shinka/llm/prioritization.py:220` (BanditBase.load_state) — pickle.load on the file content in the runner process.

**Evidence**

- `baselines/ShinkaEvolve/shinka/llm/prioritization.py:220` — Bare pickle.load; no signature, type restriction or ownership check precedes it.
- `baselines/ShinkaEvolve/shinka/core/async_runner.py:631` — The path is the fixed name bandit_state.pkl directly under results_dir.
- `baselines/ShinkaEvolve/shinka/core/async_runner.py:643` — Any exception from the load is caught and only logged as a warning, so a payload that breaks set_state does not stop the run.
- `baselines/ShinkaEvolve/shinka/core/async_runner.py:2606` — Evaluated program path is <results_dir>/gen_<generation>/main.<ext>, i.e. inside the same tree as the state file.
- `baselines/ShinkaEvolve/shinka/core/async_runner.py:5190` — The runner rewrites the state file every 5 completed generations (and at line 1166 on normal end); a planted file must be written after the last save.
- `baselines/ShinkaEvolve/shinka/core/config.py:30` — Framework default llm_dynamic_selection is 'ucb', so the load path is active by default.
- `baselines/run_shinkaevolve.py:46` — The repo glue sets llm_dynamic_selection to None, which makes _load_bandit_state return early; the path is not reachable through the glue.
- `baselines/ShinkaEvolve/shinka/launch/slurm.py:152` — The slurm_docker backend runs the evaluation in a container with operator-supplied flags; the mount layout that would make the results tree the only shared writable path is not source-visible.

**Blockers**

- No target code was executed in this run; the marker-file observation for the pickle sink has not been made.
- Deployment fact not in source: whether ShinkaEvolve is run with bandit selection enabled and resumed from a results directory that evaluated programs could write (the repo glue disables the bandit and never reuses a run directory).
- Deployment fact not in source: whether the evaluated program is confined relative to the runner (slurm_docker with only the results tree mounted, or a results directory resumed on another host or account). With the local backend and one uid the program already has equivalent write access to the runner's code and home directory.
- Timing fact: the planted file must be the last write before the resume, since the runner re-saves the file every 5 completed generations and at normal completion.

**Local check (sandbox, dummy data).** In the no-network sandbox with baselines/ShinkaEvolve on PYTHONPATH and numpy available: create scratch/results/bandit_state.pkl by pickling {'x': Obj()} where Obj.__reduce__ returns (open, ('scratch/poc_marker_shinka', 'w')). Then call shinka.llm.prioritization.AsymmetricUCB(arm_names=['a']).load_state('scratch/results/bandit_state.pkl'), the same call ShinkaEvolveRunner._load_bandit_state makes. Single observable: the file scratch/poc_marker_shinka exists afterwards (a later exception from set_state is expected and irrelevant).

**Owner-observed check.** Owner check: confirm whether any ShinkaEvolve run uses llm_dynamic_selection other than null and is ever restarted on an existing results_dir, and whether evaluation jobs (local, slurm_docker, slurm_conda) can write to the top level of that results_dir.

## `shinka-inspect/context-bundle-fence-breakout`

**shinka-inspect context bundle lets generated program text and program stdout escape their code fences in the file a coding agent is told to load**

The shinka-inspect skill builds a Markdown 'context bundle' from a ShinkaEvolve results database and instructs the coding agent to load it as its planning context. Two fields in that bundle are authored by the lowest-trust principal in the system: `code` (the LLM-generated program) and `text_feedback` (in this repository's glue, the last 1500 characters the generated program printed). The renderer places each inside a fixed three-backtick fence and does nothing else: no escaping of backtick runs, no fence sized to the content, no marker that the content is untrusted. A program that contains or prints a line of three backticks ends the fence, and everything after it is emitted as ordinary top-level Markdown next to the framework-authored 'Run Metadata' and 'Ranking' sections, so it is indistinguishable from bundle structure or operator notes. The consumer is a different principal with different authority: the operator's coding agent (Claude Code/Codex per the docs), which the sibling shinka-run skill drives through shell commands and, on request, an autonomous multi-batch loop. The script also accepts any results directory or SQLite path, so a database produced in a contained backend, on another machine, or by another person reaches the same agent context. Attacker: whoever controls generated program text or its stdout (a mutation model endpoint, including the documented local/<model>@http(s)://host form, or the author of a shared results DB). Affected principal: the operator, through the agent session's tool authority. This is reported as needs_validation because only the delimiter failure is deterministic and source-visible; whether an agent acts on the escaped text is runtime behaviour, and when generation ran unsandboxed on the same host the generated program already executed as the operator, which limits the added authority to what only the agent session holds. Reviewer note: Not re-traced line by line by the parent. Kept because the locally testable part is deterministic: whether program text containing a backtick run closes the fence in the rendered bundle. What an agent then does with that text is not part of the claim to be reproduced.

**Claimed root cause.** inspect_best_programs.py:_render_markdown interpolates untrusted database text (text_feedback and code) between fixed ``` fences without neutralising embedded fence delimiters or labelling provenance, and SKILL.md directs the resulting file to be loaded into a tool-capable agent's context as trusted planning material.

**Trace**

1. `entrypoint` `benchmarks/evaluation.py:77` (evaluate) — The generated program's combined stdout/stderr tail (last 1500 characters) is stored verbatim in metrics['output_tail']; the program body itself is the second attacker-authored value.
2. `propagation` `baselines/shinka_evaluate.py:27` (module) — The output tail is embedded in `feedback` (lines 23-25) and written as metrics.json text_feedback (line 29) with no filtering.
3. `propagation` `baselines/ShinkaEvolve/shinka/utils/general.py:76` (load_results) — The runner loads metrics.json from the evaluation results directory.
4. `propagation` `baselines/ShinkaEvolve/shinka/core/async_runner.py:4130` (ShinkaEvolveRunner (completed-job persistence)) — text_feedback is taken from the loaded metrics and stored on the Program row (line 4171) regardless of evo_config.use_text_feedback.
5. `propagation` `baselines/ShinkaEvolve/shinka/core/async_runner.py:4165` (ShinkaEvolveRunner (completed-job persistence)) — The LLM-generated source file is read back and stored as Program.code in the programs table.
6. `propagation` `baselines/ShinkaEvolve/shinka/utils/load_df.py:108` (load_programs_to_df) — code (line 108) and text_feedback (line 123) are copied unchanged from the SQLite row into the DataFrame returned to the skill script.
7. `propagation` `baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py:275` (_render_markdown) — text_feedback is appended between a fixed ```text opener (274) and ``` closer (276) with only .strip() applied.
8. `propagation` `baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py:281` (_render_markdown) — The program code (length-truncated only, line 256) is appended between a fixed ```<language> opener (280) and ``` closer (282); an embedded fence line ends the block early.
9. `propagation` `baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py:315` (main) — The assembled Markdown is written to <results_dir>/shinka_inspect_context.md (or --out).
10. `sink` `baselines/ShinkaEvolve/skills/shinka-inspect/SKILL.md:48` (Workflow step 4) — The skill instructs the coding agent to load the output file into its context and use it as the artifact for next-step mutation planning (lines 48-50).

**Evidence**

- `baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py:280` — Strongest control present: a fixed three-backtick fence around the code (280-282) and around feedback (274-276). No escaping, no adaptive fence length, no untrusted-content label anywhere in _render_markdown (198-285).
- `baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py:153` — _truncate is the only transformation applied to code; it limits length and appends a marker but does not alter fence characters.
- `baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py:110` — _resolve_db_path accepts any directory or .sqlite/.db path, so a results database not produced by the current operator or host is rendered the same way.
- `baselines/ShinkaEvolve/skills/shinka-inspect/SKILL.md:3` — Skill description: 'Load top-performing Shinka programs into agent context'; the file contains no statement that the bundled program text is untrusted data, and no tool scope.
- `baselines/ShinkaEvolve/docs/agentic_usage.md:180` — Documentation states the bundle is 'designed to be loaded directly into coding-agent context'.
- `baselines/ShinkaEvolve/skills/shinka-run/SKILL.md:113` — Capability side: the companion skill has the same agent launch shell commands (lines 62-79) and permits continuing across batches without re-asking when the user requested autonomous execution.
- `baselines/shinka_evaluate.py:24` — This repository's ShinkaEvolve evaluator copies the generated program's output tail into text_feedback, making the feedback block program-controlled.

**Blockers**

- No bounded local observation was permitted in this run (no approved sandbox), so the fence breakout in a rendered bundle is established from source only.
- Whether the consuming coding agent treats Markdown that escaped the fence as instructions, and which tools it may use without approval at that moment, is agent runtime and model behaviour that is not observable from the repository; the repository contains no deterministic control either way.
- Deployment fact: whether the results database being inspected was produced by generated code that already ran unsandboxed under the same uid and host as the agent session (added authority is then limited to what only the agent session holds), or came from a contained backend, another host or another person.

**Local check (sandbox, dummy data).** Inside the no-network sandbox, with ShinkaEvolve importable and pandas present, create a temporary directory containing programs.sqlite with a `programs` table (columns id, code, language, parent_id, generation, timestamp, combined_score, correct, text_feedback, metadata, public_metrics, private_metrics, archive_inspiration_ids, top_k_inspiration_ids, embedding, complexity, code_diff) and two dummy rows with correct=1: row A code = 'x = 1' followed by a newline, a line of three backticks, a blank line, the line '## SHINKA-INSPECT-POC-CODE', a line '```python' and 'y = 2'; row A text_feedback = 'ok', newline, a line of three backticks, blank line, the line '## SHINKA-INSPECT-POC-FEEDBACK', and a line '```text'; row B is a control with code 'z = 3' and empty feedback. JSON columns hold '{}' or '[]'. Run `python baselines/ShinkaEvolve/skills/shinka-inspect/scripts/inspect_best_programs.py --results-dir <tmp> --out <scratch>/bundle.md`. Then scan bundle.md line by line with a fence tracker that toggles on every line beginning with three backticks. Single observable: the lines '## SHINKA-INSPECT-POC-CODE' and '## SHINKA-INSPECT-POC-FEEDBACK' are reached while the tracker state is 'outside fence', while the control row's 'z = 3' is inside a fence. No agent, credential or network is involved.

**Owner-observed check.** Owner-observed: confirm which agent runtime and permission mode load shinka_inspect_context.md in practice, whether shell commands are pre-approved or an autonomous shinka-run loop is used in that session, and whether results directories from other hosts, container/Slurm backends or other people are ever passed to --results-dir.

## `shinka-webui/cors-wildcard-json-api`

**Every JSON endpoint answers with Access-Control-Allow-Origin: *, letting any web page the operator visits read run data through the operator's browser**

Lower-trust principal: a web page from an unrelated origin opened in the browser the operator uses for the web UI (including when the operator correctly uses an SSH tunnel and a firewalled host). Accepted action: a simple cross-origin GET (fetch or XHR without credentials or custom headers) to http://localhost:<port>/... Control that should stop it: the browser same-origin policy, which the server switches off by sending Access-Control-Allow-Origin: * on every JSON response; there is no Origin check and no secret in the URL. Crossed boundary: foreign web origin to operator data. Readable cross-origin: /list_databases, /get_programs, /get_programs_summary, /get_program_details (program source), /get_system_prompts, /get_meta_files, /get_meta_content, /get_plots, /get_database_stats, and, combined with shinka-webui/db-path-traversal, Shinka databases and meta files outside the served directory. Not readable cross-origin: /plot_file/ bodies, the PDF download, error bodies and static files (no CORS header). The page needs the port number; 8000 is the default and 8888 is the documented value. Reviewer note: Parent review confirmed send_json_response sets Access-Control-Allow-Origin: * (visualization.py:1681) for every JSON endpoint; the server uses no credentials, so any origin the operator's browser visits can read these responses if the browser can reach the port.

**Claimed root cause.** send_json_response unconditionally emits Access-Control-Allow-Origin: * for an unauthenticated API whose only intended client is the same-origin web UI, so the wildcard serves no functional purpose and removes the one browser-side barrier.

**Trace**

1. `entrypoint` `baselines/ShinkaEvolve/shinka/webui/visualization.py:274` (DatabaseRequestHandler.do_GET) — A cross-origin simple GET issued by a foreign page in the operator's browser is routed like any other request; the Origin header is never read.
2. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:571` (DatabaseRequestHandler.handle_get_programs_summary) — Program summaries (including full metadata) are passed to send_json_response; the other data handlers do the same.
3. `sink` `baselines/ShinkaEvolve/shinka/webui/visualization.py:1681` (DatabaseRequestHandler.send_json_response) — Access-Control-Allow-Origin: * is attached to the response, so the browser hands the body to the foreign page's script.

**Evidence**

- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1674` — send_json_response is the single helper used by all JSON endpoints, so the wildcard applies to every one of them.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1016` — Limit: the /plot_file/ response sets only Content-Type, Content-Length and Cache-Control, so it is not readable cross-origin.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:34` — DEFAULT_PORT is 8000, a predictable target for a foreign page.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:3924` — The shipped front end calls the API with same-origin relative URLs, so it does not need any CORS header.

**Blockers**

- No bounded local observation exists: this run forbids executing target code because the required OS sandbox is not available.
- Browser policy fact: whether the operator's browser lets a page from a public origin send requests to a loopback or private address without a prompt (Local/Private Network Access enforcement differs by browser and version). Pages served from another local or intranet origin are not subject to that restriction.
- Deployment fact: sensitivity of the run data (program source, stored prompts and responses, costs) for this operator.

**Local check (sandbox, dummy data).** In a no-network sandbox, build the handler as tests/test_visualization_meta.py does but record send_header calls in a list and set wfile=io.BytesIO(); call handler.send_json_response({'k': 'SENTINEL_JSON'}). Expected observable: the recorded headers contain ('Access-Control-Allow-Origin', '*') and wfile contains SENTINEL_JSON. Optional isolated-loopback variant with an empty dummy directory: GET /list_databases with header 'Origin: http://other.test' returns that same header.

**Owner-observed check.** Owner check only: with the web UI running, open a page from a different origin in the browser normally used for it and run fetch('http://localhost:<port>/list_databases').then(r => r.text()) in the console; note whether the browser returns the body, blocks it, or shows a local-network permission prompt.

## `shinka-webui/db-path-traversal`

**db_path query value is joined to search_root without containment, exposing Shinka databases, prompt databases and meta_*.txt files anywhere on the host**

Lower-trust principal: any client that can send a GET to the web UI (network client, or a cross-origin page because these responses carry Access-Control-Allow-Origin: *). Accepted input: the db_path query value on ten endpoints, plus generation/processed_count. Control that should stop it: _get_actual_db_path, which the handlers call first and which is a no-op. Crossed boundary: the operator chose one directory (search_root) to expose; the client reads outside it. What is actually reachable, established from source: (1) /get_programs, /get_programs_summary, /get_program_details, /get_program_count and /get_database_stats return the contents (program source, metrics, metadata including stored LLM prompts/responses and logs) of any sqlite file with the Shinka 'programs' schema that the server uid can read, addressed by absolute path or '../'; (2) /get_system_prompts returns prompts.sqlite from the same out-of-root directory; (3) /get_meta_files lists meta_<int>.txt in an arbitrary directory and returns absolute server paths; /get_meta_content returns the text of such a file; (4) /download_meta_pdf returns meta_<value>.txt and, only where a directory named meta_* already exists, any reachable .txt file; (5) /get_plots lists image file names in any directory ending in results/plots; (6) status differences reveal whether arbitrary files and directories exist and whether a file is a sqlite database. Not reachable through db_path alone: arbitrary non-sqlite files (they produce only an sqlite error string). Variant with a different precondition: path values stored inside a database (attempt_log details.failure_json_path) and inside the referenced failure.json (artifacts.generated_code_path) are also joined to search_root without containment and the referenced file is returned as 'code', so a crafted database placed on the server's disk turns /get_program_details into an arbitrary text-file read; in normal runs those values are written by the framework. Reviewer note: Parent review confirmed _get_actual_db_path returns its argument unchanged and that os.path.join(self.search_root, actual_db_path) at :449 is followed only by an existence check before the database is opened.

**Claimed root cause.** No function confines request- or database-supplied relative paths to search_root: _get_actual_db_path returns its input unchanged and every handler passes the result straight to os.path.join(self.search_root, ...), where an absolute value replaces the root and '..' segments are never normalised or checked.

**Trace**

1. `entrypoint` `baselines/ShinkaEvolve/shinka/webui/visualization.py:284` (DatabaseRequestHandler.do_GET) — db_path is taken verbatim from the query string of an unauthenticated GET /get_programs.
2. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:438` (DatabaseRequestHandler.handle_get_programs) — The value passes through _get_actual_db_path, which returns it unchanged (definition at line 428-430).
3. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:449` (DatabaseRequestHandler.handle_get_programs) — os.path.join(self.search_root, actual_db_path): an absolute value discards search_root, '../' climbs out of it; only os.path.exists is checked afterwards.
4. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:464` (DatabaseRequestHandler.handle_get_programs) — The out-of-root file is opened as a read-only ProgramDatabase and all programs are loaded.
5. `sink` `baselines/ShinkaEvolve/shinka/webui/visualization.py:486` (DatabaseRequestHandler.handle_get_programs) — The full program list (code, metrics, metadata) is serialised to the client with Access-Control-Allow-Origin: *.

**Evidence**

- `baselines/ShinkaEvolve/shinka/webui/visualization.py:430` — _get_actual_db_path body is 'return db_path'; its docstring calls it a no-op.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:546` — Sibling join site in handle_get_programs_summary; the same pattern repeats at lines 616, 694, 785, 843, 891, 948, 1035 and 1134.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:859` — handle_get_meta_content opens meta_<processed_count>.txt under the attacker-chosen directory and returns its text.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:863` — int(processed_count) limits this endpoint to integer-like file suffixes; it is the only value check on any of these parameters.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:815` — handle_get_meta_files returns the absolute filesystem path of each meta file to the client.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:953` — handle_get_plots interpolates the raw generation value into a path component, allowing '../' after an existing gen_<N> directory.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1145` — handle_get_database_stats opens the attacker-chosen path with a plain read-write sqlite3.connect and returns the sqlite error text for non-database files.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:134` — Variant: generated_code_path from failure.json is joined to search_root without containment and the file is later read and returned as 'code' (read at line 196).
- `baselines/ShinkaEvolve/shinka/database/dbase.py:338` — Strongest visible control: ProgramDatabase read-only mode opens the file with mode=ro, which prevents writes but not out-of-root reads.

**Blockers**

- No bounded local observation exists: this run forbids executing target code because the required OS sandbox is not available.
- Deployment fact: whether Shinka-format databases or meta_*.txt files that the operator did not intend to publish exist outside the served directory on the same host.
- Deployment fact: whether any client other than the operator can reach the port, or which browser policy applies to cross-origin reads of the JSON endpoints.

**Local check (sandbox, dummy data).** In a no-network sandbox, create temp tree T with T/root (empty, used as search_root), T/outside/meta/meta_5.txt containing 'SENTINEL_META', and T/outside/p.sqlite created with the stdlib sqlite3 module: CREATE TABLE programs(generation INTEGER, correct INTEGER, combined_score REAL, timestamp REAL, metadata TEXT) plus one row (7, 1, 0.5, 1.0, '{}'). Build the handler as tests/test_visualization_meta.py does (search_root=str(T/'root'), capture send_json_response and send_error). Step 1: handler.handle_get_meta_content('../outside/p.sqlite', '5'); expected observable: captured JSON has content == 'SENTINEL_META'. Step 2: handler.handle_get_database_stats(str(T/'outside'/'p.sqlite')) (absolute path); expected: captured JSON has program_count == 1 and max_generation == 7. Either result proves a read outside search_root.

## `shinka-webui/dom-xss-llm-derived-fields`

**viz_tree.html writes model-derived patch names, descriptions, thoughts and meta summaries into innerHTML without escaping**

Source: text produced by the code-proposing model (the <NAME> and <DESCRIPTION> blocks of its reply, stored as metadata.patch_name and metadata.patch_description), by the meta-summariser model (meta_<N>.txt), by prompt evolution (system prompt name/description) and metadata.thought; equally, any of these fields in a results directory the operator received from someone else. Sink: innerHTML and d3 .html() in viz_tree.html. Browser policy that should stop it: none is present (no CSP, no sanitizer); the page's own escapeHtml helper is applied to code, logs, text feedback and metadata values but not to these fields. Affected origin/session: the web UI origin in the operator's browser (http://localhost:<port>, typically on the operator's workstation behind an SSH tunnel, which is a different machine from the one running generated code). Observable effect: markup such as an img element with an error handler placed in a patch name runs script when the operator hovers a tree node, selects a node, opens the best-path view, or opens the Meta tab. Because viz_tree.html auto-loads the database named in the db_path URL parameter and auto-selects the node named in selected_node, opening a single link is enough to render a chosen node. Script running in that origin can call the same-origin endpoints, including /plot_file/ (not readable cross-origin) and the db_path traversal, read files under the launch directory such as .env and send them to another host, since nothing restricts outbound requests. The program table truncates patch_name to 15 characters, which limits that one sink; index.html and compare.html do not render model-derived text. Reviewer note: Parent review confirmed the patch_name path: extracted from the model reply (core/async_runner.py:1938), stored in metadata (:1981), returned by /get_programs_summary, and written into innerHTML as <h3>${agentName}...</h3> at viz_tree.html:5688-5693 without escaping. The other listed fields were not re-traced by the parent.

**Claimed root cause.** HTML is assembled with template literals and assigned to innerHTML, and escaping is applied field by field; patch_name, patch_description, thought (via marked.parse), meta file text (via marked.parse and a hand-written markdown replacer), system-prompt name/description and several ids were left out, and marked is used without any sanitiser.

**Trace**

1. `entrypoint` `baselines/ShinkaEvolve/shinka/core/async_runner.py:1938` (initial-program and patch generation) — patch_name is extracted verbatim from between <NAME> tags of the model's reply (regex in shinka/llm/llm.py line 883, no character filtering); the same is done for patch_description at line 1941.
2. `propagation` `baselines/ShinkaEvolve/shinka/core/async_runner.py:1981` (initial-program and patch generation) — The value is stored in the program's metadata dictionary, which is persisted to the sqlite programs table.
3. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:571` (DatabaseRequestHandler.handle_get_programs_summary) — /get_programs_summary returns each program with its full parsed metadata as JSON.
4. `propagation` `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:3924` (loadDatabase) — The front end fetches the summaries and keeps them as window.treeData; selecting a node passes its record to displayNodeDetails.
5. `propagation` `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:5688` (displayNodeDetails) — agentName is taken from data.metadata.patch_name with no escaping.
6. `sink` `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:5692` (displayNodeDetails) — The node-summary element's innerHTML is set to a template containing <h3>${agentName} ...</h3>.

**Evidence**

- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:4786` — Tree-node hover tooltip inserts patchName (from line 4758) through d3 .html() without escaping, while the adjacent failure fields are escaped.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:5857` — patch_description is interpolated raw into the node details HTML, which is assigned to innerHTML at line 6022.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:6009` — metadata.thought is passed through marked.parse and inserted via the same innerHTML assignment.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:3042` — Meta tab sink: sectionContent.innerHTML receives marked.parse output (lines 3073, 3076) and the unescaped program-summary formatter output (line 2914) built from meta_<N>.txt text.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:10681` — Best-path timeline inserts patch_name and patch_description (line 10679) through d3 .html().
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:17656` — System-prompt name and description (line 17660) are interpolated raw into detailsPanel.innerHTML, while prompt_text in the same template is escaped.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:5634` — Strongest visible control: escapeHtml is applied to program code (and to logs, text feedback and metadata values elsewhere), showing escaping was intended but is incomplete.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:2077` — marked is loaded unpinned from a CDN with no sanitiser library alongside it; there is no Content-Security-Policy in the page or in the server's headers.
- `baselines/ShinkaEvolve/shinka/webui/viz_tree.html:9167` — The selected_node URL parameter auto-selects a node after load, and db_path from the URL is loaded even if not in the server's list (line 3433), so no click is required.

**Blockers**

- No bounded local observation exists: this run forbids executing target code, and a browser test additionally needs local copies of the CDN libraries (d3, Chart.js, marked, highlight.js, Plotly) because the sandbox has no network.
- Renderer fact: behaviour of the marked version actually delivered by the unpinned CDN URL for raw HTML input (current releases pass it through) must be observed in a browser.
- Deployment fact: whether the operator views results whose text fields come from a less trusted source than their own account (model output steered by untrusted task content, or a results directory supplied by a third party).

**Local check (sandbox, dummy data).** Function-level check without a browser or network: with Node.js, read baselines/ShinkaEvolve/shinka/webui/viz_tree.html, extract the source text of the two pure string functions formatProgramSummaries and processSimpleMarkdown (they start at the lines 'function formatProgramSummaries(content) {' and 'function processSimpleMarkdown(text) {'), evaluate them in an empty vm context, and call formatProgramSummaries('Program Name: <img src=x onerror=XSS_MARKER>\nImplementation: a'). Expected observable: the returned string contains the unescaped substring '<img src=x onerror=XSS_MARKER>'; source line 3042 assigns that string to innerHTML. Optional end-to-end check when a sandboxed headless browser with locally served copies of the CDN scripts is available: create a dummy results directory with a programs.sqlite holding one program whose metadata.patch_name is '<img src=x onerror="document.title=`XSS_MARKER`">', serve it on isolated loopback, open /viz_tree.html?db_path=<that db>&selected_node=<its id>, and observe document.title becoming XSS_MARKER.

## `shinka-webui/plot-file-unrestricted-read`

**/plot_file/ returns any file under the search root (by default the launch directory that holds .env) and its prefix check admits sibling directories and symlinks**

Lower-trust principal: any client that can send an HTTP GET to the web UI port (the server listens on all interfaces without authentication; see shinka-webui/wildcard-bind-no-auth). Accepted input: the URL path after /plot_file/. Control that should stop it: the 'Security check: ensure the path is within search_root' in handle_serve_plot_file. Crossed boundary: network client to operator files. The handler is meant to serve plot images that /get_plots lists (png/gif/jpg/jpeg only), but it applies no extension or sub-directory restriction, so every regular file under search_root is returned as application/octet-stream. search_root defaults to the current working directory, and the documented quick start runs 'shinka_visualize --port 8888' with no directory from the project/launch directory, which is also where the docs tell the operator to keep a .env file with provider API keys and where shinka loads it from. GET /plot_file/.env would then return those keys. Three further weaknesses in the same check: (1) containment is a string startswith on abspath values with no trailing separator, so a root of .../results also admits .../results_old/ or .../results.bak via '../results_old/...'; (2) abspath does not resolve symlinks, so a link placed inside the root is followed out of it; (3) existence is tested before containment, so 404 versus 403 tells the client whether an arbitrary host path exists. Limits: paths outside the root that do not share its string prefix are refused; the response carries no CORS header, so a cross-origin page cannot read it directly (a same-origin script, see shinka-webui/dom-xss-llm-derived-fields, can). Reviewer note: Parent review re-read handle_serve_plot_file (visualization.py:981-1020): the only containment is abspath(...).startswith(abspath(search_root)) at :997, with no trailing separator and no file-type allowlist; search_root defaults to the current working directory (main(), :1750-1757).

**Claimed root cause.** handle_serve_plot_file treats 'inside search_root by string prefix' as the whole authorisation decision: it has no file-type or plots-directory allowlist, compares un-normalised prefixes without a path separator, uses abspath instead of realpath, and checks existence before containment.

**Trace**

1. `entrypoint` `baselines/ShinkaEvolve/shinka/webui/visualization.py:333` (DatabaseRequestHandler.do_GET) — Any GET whose path starts with /plot_file/ is dispatched to handle_serve_plot_file with no caller check.
2. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:985` (DatabaseRequestHandler.handle_serve_plot_file) — The remainder of the URL path is percent-decoded into rel_path, so encoded '../' sequences survive any client-side normalisation.
3. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:987` (DatabaseRequestHandler.handle_serve_plot_file) — rel_path is joined to search_root; no extension, directory or file-type restriction is applied.
4. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:997` (DatabaseRequestHandler.handle_serve_plot_file) — Containment is abspath(abs_path).startswith(abspath(search_root)) with no trailing separator and no symlink resolution.
5. `sink` `baselines/ShinkaEvolve/shinka/webui/visualization.py:1012` (DatabaseRequestHandler.handle_serve_plot_file) — The file is opened in binary mode and its full content is written to the response.

**Evidence**

- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1753` — root_directory defaults to os.getcwd(), so search_root is the launch directory unless the operator passes a results directory.
- `baselines/ShinkaEvolve/docs/webui.md:43` — Documented remote launch is 'shinka_visualize --port 8888' with no directory argument.
- `baselines/ShinkaEvolve/docs/getting_started.md:71` — Docs instruct the operator to create a .env file with provider API keys in the project root.
- `baselines/ShinkaEvolve/shinka/env.py:18` — shinka loads .env from the launch (current working) directory, the same directory the web UI serves by default.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:961` — The listing endpoint restricts plots to .png/.gif/.jpg/.jpeg, showing the intended scope that the serving endpoint does not enforce.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1009` — Unknown extensions fall back to application/octet-stream instead of being rejected.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:990` — os.path.exists runs before the containment check, giving a 404-versus-403 existence oracle for any host path.

**Blockers**

- No bounded local observation exists: this run forbids executing target code because the required OS sandbox is not available.
- Deployment fact: whether the operator starts shinka_visualize from a directory that contains .env or other non-plot files, or always passes a results directory.
- Deployment fact: whether the port is reachable by any client other than the operator (host firewall, shared host or cluster network).

**Local check (sandbox, dummy data).** In a no-network sandbox, create a temp tree T with T/root/.env containing 'DUMMY_KEY=SENTINEL_ENV', T/root_sibling/note.txt containing 'SENTINEL_SIBLING', and T/other/x (empty). Build the handler as tests/test_visualization_meta.py does (DatabaseRequestHandler.__new__, search_root=str(T/'root'), stub send_response/send_header/end_headers, record send_error calls, wfile=io.BytesIO(); stub the 'markdown' module if it is not installed). Step 1: set handler.path='/plot_file/.env' and call handle_serve_plot_file(); expected observable: wfile contains SENTINEL_ENV. Step 2: reset wfile, set handler.path='/plot_file/..%2Froot_sibling%2Fnote.txt'; expected: wfile contains SENTINEL_SIBLING. Step 3: path '/plot_file/..%2Fother%2Fx' records send_error(403) while '/plot_file/..%2Fother%2Fmissing' records send_error(404). Any one of steps 1 or 2 proves the boundary result; stop there.

**Owner-observed check.** Owner check only: from the directory normally used to start shinka_visualize, list which non-image files (for example .env, configs, keys) sit under it, and confirm from a second machine on the same network whether the web UI port accepts connections.

## `shinka-webui/wildcard-bind-no-auth`

**Web UI listens on all interfaces with no authentication while the documentation describes access through an SSH tunnel to localhost**

Lower-trust principal: any host that can open a TCP connection to the operator's machine on the chosen port (other users of a shared GPU server or cluster network, other devices on the same LAN). Accepted action: any GET request. Control that should stop it: none in source; the listening address is the empty string (all IPv4 interfaces) and there is no option to change it, no token, and no Host or Origin validation. The documentation's remote workflow starts the server on the remote machine and reaches it through 'ssh -L 8888:localhost:8888', which only requires a loopback listener and leads an operator to assume the service is tunnel-only; the same page separately shows a cluster tunnel to a compute node's own address and a one-line 'never expose ports publicly' note. Crossed boundary: network client to operator data. Affected resources: every evolved program, metric, stored LLM prompt/response and log in the served databases, system prompts, meta summaries, and through the two file-handling candidates (shinka-webui/plot-file-unrestricted-read, shinka-webui/db-path-traversal) any file under the launch directory such as .env and Shinka databases elsewhere on the host. The absence of Host validation also leaves the loopback case open to DNS rebinding from a web page. This candidate is limited to exposure of the read-only API; no state-changing endpoint exists. Reviewer note: Parent review confirmed ReusableTCPServer(("", port), ...) at visualization.py:1740 and that main() offers no option to choose the bind address; docs/webui.md:189 tells users to rely on SSH tunnels and never expose the port, which the bind address does not enforce.

**Claimed root cause.** start_server hard-codes the bind address to "" and the request handler has no notion of a caller, so reachability of the port is the only access control and it is wider than the documented localhost/SSH-tunnel model.

**Trace**

1. `entrypoint` `baselines/ShinkaEvolve/shinka/webui/visualization.py:1740` (start_server) — ReusableTCPServer(("", port), handler_factory) listens on every IPv4 interface; main() offers no host option.
2. `propagation` `baselines/ShinkaEvolve/shinka/webui/visualization.py:274` (DatabaseRequestHandler.do_GET) — Requests are routed purely on path and query; there is no authentication, token, Host or Origin check on any branch.
3. `sink` `baselines/ShinkaEvolve/shinka/webui/visualization.py:1685` (DatabaseRequestHandler.send_json_response) — Database contents are written to whichever peer connected.

**Evidence**

- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1741` — The startup banner itself prints 'Serving http://0.0.0.0:{port}'.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1818` — The only operator hint is 'remember to forward the port if this is a remote host', which implies a tunnel rather than direct exposure.
- `baselines/ShinkaEvolve/docs/webui.md:46` — Documented remote access is an SSH local forward to localhost:8888 on the remote host.
- `baselines/ShinkaEvolve/docs/webui.md:140` — Cluster example forwards to compute-node:8888, which works only because the server is not loopback-bound; every other cluster user can reach the same address.
- `baselines/ShinkaEvolve/docs/webui.md:189` — Strongest visible control is advisory text: 'Use SSH tunnels for remote access; never expose ports publicly'.
- `baselines/ShinkaEvolve/shinka/webui/visualization.py:1012` — Example of what an unauthenticated peer can obtain: /plot_file/ opens and returns files under the launch directory.

**Blockers**

- No bounded local observation exists: this run forbids executing target code because the required OS sandbox is not available.
- Deployment fact: whether the operator's host firewall or network placement lets any other principal connect to the port; source cannot show this.

**Local check (sandbox, dummy data).** In a sandbox with only an isolated loopback interface, import shinka.webui.visualization, monkeypatch socketserver.TCPServer.serve_forever with a function that stores self.socket.getsockname() in a list and returns, then call start_server(0, <empty temp dir>). Expected observable: the stored address is ('0.0.0.0', <port>), not 127.0.0.1. Optional second observable with the real serve loop on loopback and a dummy empty directory: a GET /list_databases sent with no credentials or special headers returns HTTP 200 and a JSON list.

**Owner-observed check.** Owner check only: while shinka_visualize is running, run 'ss -ltnp' on the host to see the listening address, and try the URL from a second machine or a second user account on the same network.
