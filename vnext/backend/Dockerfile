FROM rust:1.97.0-bookworm AS builder
ARG UV_VERSION=0.11.28
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /build/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/README.md ./
COPY rust /build/rust
COPY shared_kernel /build/shared_kernel
COPY repository_client /build/repository_client
COPY repository_contracts /build/repository_contracts
RUN uv python install 3.14.6
ARG RUSTUP_TOOLCHAIN=1.97.0
ENV RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN}
RUN uv sync --frozen --no-install-project
RUN rm -rf /build/wheels \
    && mkdir -p /build/wheels \
    && .venv/bin/maturin build \
        --release \
        --manifest-path /build/rust/gateway-compute-python/Cargo.toml \
        --interpreter /build/backend/.venv/bin/python \
        --out /build/wheels

FROM python:3.14.6-slim-bookworm
ARG UV_VERSION=0.11.28
RUN pip install --no-cache-dir uv==${UV_VERSION}
WORKDIR /app/backend
COPY rust /app/rust
COPY shared_kernel /app/shared_kernel
COPY repository_client /app/repository_client
COPY repository_contracts /app/repository_contracts
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/README.md ./
RUN uv sync \
    --frozen \
    --no-install-project \
    --no-dev \
    --no-install-package gateway-compute-python
COPY backend/src ./src
COPY --from=builder /build/wheels/*.whl /tmp/
RUN uv pip install \
    --python /app/backend/.venv/bin/python \
    --no-deps \
    /tmp/*.whl
ENV PATH="/app/backend/.venv/bin:${PATH}" PYTHONPATH="/app/backend/src"
CMD ["uvicorn", "gateway_backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
