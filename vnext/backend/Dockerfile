ARG DEPENDENCY_BASE_IMAGE=rust:1.97.0-bookworm
FROM ${DEPENDENCY_BASE_IMAGE} AS dependency-base

ARG DEPENDENCY_BASE_IMAGE
ARG USE_PRELOADED_DEPENDENCIES=0
ARG UV_VERSION=0.11.28
ARG RUSTUP_TOOLCHAIN=1.97.0
ENV PATH="/root/.local/bin:${PATH}" RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN}
WORKDIR /build/backend

COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/README.md ./
COPY rust/Cargo.toml rust/Cargo.lock rust/rust-toolchain.toml /build/rust/
COPY rust/gateway-architecture-check/Cargo.toml /build/rust/gateway-architecture-check/Cargo.toml
COPY rust/gateway-compute-core/Cargo.toml /build/rust/gateway-compute-core/Cargo.toml
COPY rust/gateway-compute-python-impl/Cargo.toml /build/rust/gateway-compute-python-impl/Cargo.toml
COPY rust/gateway-compute-python/Cargo.toml /build/rust/gateway-compute-python/Cargo.toml
COPY rust/gateway-shared-kernel/Cargo.toml /build/rust/gateway-shared-kernel/Cargo.toml

RUN if [ "${USE_PRELOADED_DEPENDENCIES}" = "1" ]; then \
      python3 -c 'import hashlib,json,sys; from pathlib import Path; root=Path("/usr/local/share/gateway-backend-dependency-base"); raw=(root/"inputs.json").read_bytes(); inputs=json.loads(raw); digest=hashlib.sha256(raw).hexdigest(); expected={"backend/pyproject.toml":Path("/build/backend/pyproject.toml"),"backend/uv.lock":Path("/build/backend/uv.lock"),"backend/.python-version":Path("/build/backend/.python-version"),"rust/Cargo.lock":Path("/build/rust/Cargo.lock"),"rust/rust-toolchain.toml":Path("/build/rust/rust-toolchain.toml")}; assert (root/"input-sha256").read_text(encoding="ascii").strip()==digest, "dependency-base digest file is inconsistent"; assert len(sys.argv)==2 and sys.argv[1].rsplit(":lock-",1)[-1]==digest[:12], "dependency-base tag does not match its input digest"; assert all(inputs["files"].get(name)==hashlib.sha256(path.read_bytes()).hexdigest() for name,path in expected.items()), "dependency-base lock inputs do not match this source tree"' "${DEPENDENCY_BASE_IMAGE}"; \
    else \
      curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o /tmp/uv-install.sh \
      && sh /tmp/uv-install.sh \
      && rm -f /tmp/uv-install.sh \
      && uv python install "$(cat .python-version)" \
      && ln -sfn "$(uv python find "$(cat .python-version)")" /usr/local/bin/python3 \
      && uv sync --locked --no-install-local --no-install-project \
      && uv pip install \
          --python "$(uv python find "$(cat .python-version)")" \
          "uv==${UV_VERSION}" \
      && for crate in gateway-architecture-check gateway-compute-core gateway-compute-python-impl gateway-compute-python gateway-shared-kernel; do \
           mkdir -p "/build/rust/${crate}/src"; \
         done \
      && touch \
          /build/rust/gateway-architecture-check/src/main.rs \
          /build/rust/gateway-architecture-check/src/lib.rs \
          /build/rust/gateway-compute-core/src/lib.rs \
          /build/rust/gateway-compute-python-impl/src/lib.rs \
          /build/rust/gateway-compute-python/src/lib.rs \
          /build/rust/gateway-shared-kernel/src/lib.rs \
      && cargo fetch --locked --manifest-path /build/rust/Cargo.toml; \
    fi

FROM dependency-base AS builder
WORKDIR /build/backend
COPY rust /build/rust
COPY shared_kernel /build/shared_kernel
COPY repository_client /build/repository_client
COPY repository_contracts /build/repository_contracts
RUN UV_OFFLINE=1 uv sync --locked --no-install-local --no-install-project \
    && rm -rf /build/wheels \
    && mkdir -p /build/wheels \
    && CARGO_NET_OFFLINE=true .venv/bin/maturin build \
        --release \
        --locked \
        --manifest-path /build/rust/gateway-compute-python/Cargo.toml \
        --interpreter /build/backend/.venv/bin/python \
        --out /build/wheels

FROM python:3.14.6-slim-bookworm AS runtime
ARG USE_PRELOADED_DEPENDENCIES=0
ARG UV_VERSION=0.11.28
ARG UV_BOOTSTRAP_INDEX_URL=https://pypi.org/simple
ARG UV_BOOTSTRAP_TRUSTED_HOST
WORKDIR /app/backend

COPY --from=dependency-base /root/.local/bin/uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/README.md ./
RUN --mount=type=bind,from=dependency-base,source=/root/.cache/uv,target=/root/.cache/uv \
    if [ "${USE_PRELOADED_DEPENDENCIES}" = "1" ]; then \
      uv pip install --system --offline "uv==${UV_VERSION}"; \
    elif [ -n "${UV_BOOTSTRAP_TRUSTED_HOST}" ]; then \
      pip install --no-cache-dir --index-url="${UV_BOOTSTRAP_INDEX_URL}" --trusted-host "${UV_BOOTSTRAP_TRUSTED_HOST}" "uv==${UV_VERSION}"; \
    else \
      pip install --no-cache-dir --index-url="${UV_BOOTSTRAP_INDEX_URL}" "uv==${UV_VERSION}"; \
    fi \
    && UV_OFFLINE=1 uv sync \
        --frozen \
        --no-install-project \
        --no-dev \
        --no-install-local \
        --no-install-package gateway-compute-python

COPY rust /app/rust
COPY shared_kernel /app/shared_kernel
COPY repository_client /app/repository_client
COPY repository_contracts /app/repository_contracts
COPY backend/src ./src
RUN --mount=type=bind,from=builder,source=/build/wheels,target=/tmp/backend-wheels \
    UV_OFFLINE=1 uv sync \
        --frozen \
        --no-install-project \
        --no-dev \
        --no-install-package gateway-compute-python \
    && UV_OFFLINE=1 uv pip install \
        --python /app/backend/.venv/bin/python \
        --no-deps \
        /tmp/backend-wheels/*.whl

ENV PATH="/app/backend/.venv/bin:${PATH}" PYTHONPATH="/app/backend/src"
CMD ["python", "-m", "gateway_backend.bootstrap.http_server"]
