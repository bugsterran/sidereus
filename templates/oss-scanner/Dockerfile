# Copy this template to your repo as .oss-scanner/Dockerfile (the path project.yaml names).
# This file must set up the environment, install your project's dependencies and build the project.
# The scanner builds it with your repository as the build context, so `COPY . /src` puts the checkout inside
# the image. Network access is available during this Dockerfile build and is removed after this point, so
# all code that an agent might need to perform its tests must be fetched here.
# ⚠ Fetch everything (packages, toolchains, test data) BEFORE the final `COPY . /src`; nothing after it may download.
FROM debian:bookworm
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates build-essential git python3 \
    && rm -rf /var/lib/apt/lists/*

# --- dependency fetch goes here (pip install -r, npm ci, go mod download, ...) ---

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
WORKDIR /src

# --- build the project as its maintainers build it; a step that fails fails the build ---
# RUN make -j"$(nproc)"

# Run the cheap tests so you know the image works, but do not let a failing test abort the build.
RUN (make test || echo "WARNING: tests reported failures")
