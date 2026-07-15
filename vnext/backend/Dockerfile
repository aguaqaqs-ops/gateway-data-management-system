FROM rust:1.97.0-bookworm AS builder
ARG UV_VERSION=0.11.28
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /build/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
COPY rust /build/rust
RUN uv python install 3.14.6
RUN uv sync --frozen --no-install-project
RUN uv run maturin build --release --manifest-path /build/rust/gateway-compute-python/Cargo.toml

FROM python:3.14.6-slim-bookworm
ARG UV_VERSION=0.11.28
RUN pip install --no-cache-dir uv==${UV_VERSION}
WORKDIR /app/backend
COPY rust /app/rust
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-install-project --no-dev
COPY backend/src ./src
COPY --from=builder /build/rust/target/wheels/*.whl /tmp/
RUN .venv/bin/pip install /tmp/*.whl
ENV PATH="/app/backend/.venv/bin:${PATH}" PYTHONPATH="/app/backend/src"
CMD ["uvicorn", "gateway_backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
