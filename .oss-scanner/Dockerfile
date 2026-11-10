# Build image for security scanning and for the approval-gated PoC sandbox (security/DESIGN.md).
#
# Two consumers:
#   1. anthropics/oss-scanner, if this project is ever enrolled (see .oss-scanner/README.md).
#   2. security/pipeline/verify.py --backend docker, which runs approved PoC harnesses in this image
#      with --network none and the repository mounted read-only at /target.
#
# Network access exists only while this file builds. Everything a harness needs must be installed here.
# No code from this repository is executed during the build: the vendored baselines are made importable
# with a .pth file instead of `pip install -e`, so their setup.py files never run.
FROM python:3.13-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
WORKDIR /src

# The paper's pinned environment for OpenEvolve and ShinkaEvolve, wheels only, no resolution
# (same flags as baselines/setup_baselines.sh), then the unpinned-in-the-paper extras.
# antlr4-python3-runtime (needed by hydra-core) ships no wheel, so it alone may build from source.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --only-binary=:all: --no-deps \
         -r baselines/requirements_openevolve_shinkaevolve.txt \
    && /opt/venv/bin/pip install --only-binary=:all: --no-binary=antlr4-python3-runtime --no-deps \
         -r .oss-scanner/requirements-sandbox-extra.txt

RUN printf '%s\n' /src/baselines/openevolve /src/baselines/ShinkaEvolve /src/baselines/CodeEvolve/src \
      > "$(/opt/venv/bin/python -c 'import site; print(site.getsitepackages()[0])')/swarmevolve_baselines.pth"

# Fail the build early if the environment is unusable.
RUN /opt/venv/bin/python -c "import flask, numpy, scipy, yaml, hydra, pandas; print('sandbox image ok')"
