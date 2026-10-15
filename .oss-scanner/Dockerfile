# Sidereus image for Anthropic OSS Scanner (filled from templates/oss-scanner/Dockerfile).
# Build context = repo root: docker build -f .oss-scanner/Dockerfile .
# Network is available during the build only. Sidereus has no pip/npm dependencies (standard library only);
# node is needed for the JS syntax gate, git for tests that read repo metadata.
# ⚠ Nothing after the final `COPY . /src` may download; the scan runs offline.
# 3.9 is the supported floor (stock macOS python), so the gates run on the oldest interpreter Sidereus promises.
FROM python:3.9-slim
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHON=python3 \
    PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git nodejs curl \
    && rm -rf /var/lib/apt/lists/*

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
WORKDIR /src

# Syntax gates (python 3.9 is the supported floor); a failure fails the build.
RUN python3 -m py_compile chat_server.py sidereus/*.py mcp/*.py \
    && for f in web/*.js web/js/*.js; do node --check "$f" || exit 1; done

# Run the tests so you know the image works, but do not let a failing test abort the build.
# Drivers: `bash tests/run.sh`, and `python3 chat_server.py --demo --no-open` for a synthetic server.
RUN (bash tests/run.sh || echo "WARNING: tests reported failures")
