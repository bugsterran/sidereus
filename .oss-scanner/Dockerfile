# Sidereus image for Anthropic OSS Scanner (filled from templates/oss-scanner/Dockerfile).
# Build context = repo root: docker build -f .oss-scanner/Dockerfile .
# Network is available during the build only. Sidereus has no pip/npm dependencies (standard library only);
# node is needed for the JS syntax gate, git for tests that read repo metadata.
# ⚠ Nothing after the final `COPY . /src` may download; the scan runs offline.
# 3.9 is the supported floor (stock macOS python), so the gates run on the oldest interpreter Sidereus promises.
# ⚠ 3.9 is EOL: upstream stopped rebuilding python:3.9-* (last push 2025-11-01), so the base OS packages go stale.
# Variant + digest pin keeps builds reproducible; `apt-get upgrade` below pulls Debian security fixes at build time.
# Refresh the digest: docker pull python:3.9.25-slim-trixie && docker inspect --format '{{index .RepoDigests 0}}' python:3.9.25-slim-trixie
FROM python:3.9.25-slim-trixie@sha256:2d97f6910b16bd338d3060f261f53f144965f755599aab1acda1e13cf1731b1b
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHON=python3 \
    PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates git nodejs curl \
    && rm -rf /var/lib/apt/lists/*
# apt-get needs root; everything after the checkout runs as an unprivileged user (trivy DS-0002).
RUN useradd --create-home --shell /usr/sbin/nologin scanner
ENV HOME=/home/scanner

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
RUN chown -R scanner:scanner /src
WORKDIR /src
USER scanner

# Syntax gates (python 3.9 is the supported floor); a failure fails the build.
RUN python3 -m py_compile chat_server.py sidereus/*.py mcp/*.py \
    && for f in web/*.js web/js/*.js; do node --check "$f" || exit 1; done

# Run the tests so you know the image works, but do not let a failing test abort the build.
# Drivers: `bash tests/run.sh`, and `python3 chat_server.py --demo --no-open` for a synthetic server.
RUN (bash tests/run.sh || echo "WARNING: tests reported failures")

# Offline liveness probe (trivy DS-0026): the interpreter starts and the checkout is present; no network.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python3 -c "import os, sys; sys.exit(0 if os.path.isdir('/src/sidereus') else 1)"
USER scanner
