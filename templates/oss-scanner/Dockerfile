# Copy this template to your repo as .oss-scanner/Dockerfile (the path project.yaml names).
# This file must set up the environment, install your project's dependencies and build the project.
# The scanner builds it with your repository as the build context, so `COPY . /src` puts the checkout inside
# the image. Network access is available during this Dockerfile build and is removed after this point, so
# all code that an agent might need to perform its tests must be fetched here.
# ⚠ Fetch everything (packages, toolchains, test data) BEFORE the final `COPY . /src`; nothing after it may download.
# Pin variant + digest so builds are reproducible; `apt-get upgrade` below still pulls OS security fixes.
# Refresh: docker pull debian:bookworm && docker inspect --format '{{index .RepoDigests 0}}' debian:bookworm
FROM debian:bookworm@sha256:2c037a04925515fdd6ea85ea14a682d0e79931f5e9f5d07b6dbfc6ba12f9e858
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
      ca-certificates build-essential git python3 \
    && rm -rf /var/lib/apt/lists/*

# Package installs need root; the build and tests run as an unprivileged user that owns /src and its HOME.
# ⚠ Create the user and set HOME before the fetch step: anything fetched with HOME=/root (pip/npm/go caches,
# `pip install --user`) lands in /root and is unreadable once the build switches to `USER scanner`.
RUN useradd --create-home --shell /usr/sbin/nologin scanner
ENV HOME=/home/scanner

# --- dependency fetch goes here (pip install -r, npm ci, go mod download, ...) ---
# System-wide installs may stay root; per-user fetches go after `USER scanner` (switch back with `USER root` if needed).

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
RUN chown -R scanner:scanner /src
WORKDIR /src
USER scanner

# --- build the project as its maintainers build it; a step that fails fails the build ---
# RUN make -j"$(nproc)"

# Run the cheap tests so you know the image works, but do not let a failing test abort the build.
RUN (make test || echo "WARNING: tests reported failures")

# Cheap offline health probe: the checkout is present; needs no network or extra packages.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD test -d /src || exit 1
USER scanner
