# How we would like patches made

## Size and scope of a fix
- As narrow as possible. Fix the faulty function; no refactoring.
- The three frameworks under `baselines/` are vendored unmodified at the commits the paper used. Propose
  fixes for them as a separate patch file and say that it belongs upstream; do not mix them with fixes
  to `benchmarks/` or the glue scripts.

## Code style
- Match the surrounding code. Few comments, only where the code is not obvious.

## Tests
- Add a regression test next to the change when a test directory exists for that component.

## Branch and commit message
- Against `main`; subject line in the form `component: what changed`.
