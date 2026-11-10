# How we would like reports written

## Layout and length
- Under one page per finding, sections in this order: Summary, Affected component and file, Attacker
  starting position, Reproduction, Impact, Suggested fix.

## What every report should state
- Whether the affected code is this repository's own (`benchmarks/`, `baselines/*.py`, `baselines/*.sh`)
  or a vendored baseline (`baselines/openevolve`, `baselines/ShinkaEvolve`, `baselines/CodeEvolve`), and
  for a vendored baseline the upstream commit from `baselines/setup_baselines.sh`.
- The non-default options the issue needs, if any.
- A reproduction that uses only dummy data, no network, and stops at the first observable effect.

## Style
- Plain Markdown, one root cause per report, title starts with the component name.
