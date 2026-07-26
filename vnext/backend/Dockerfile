ARG PYTHON_RUNTIME_IMAGE
ARG UV_VERSION=0.11.28
ARG PYTHON_VERSION=3.14.6
ARG UV_WHEEL_BASENAME
ARG GATEWAY_COMPUTE_WHEEL_BASENAME

FROM ${PYTHON_RUNTIME_IMAGE} AS runtime
ARG UV_VERSION
ARG PYTHON_VERSION
ARG SOURCE_REVISION
ARG WHEEL_SHA256
ARG EXTENSION_SHA256
ARG UV_WHEEL_SHA256
ARG UV_WHEEL_BASENAME
ARG GATEWAY_COMPUTE_WHEEL_BASENAME
LABEL org.opencontainers.image.revision="${SOURCE_REVISION}" \
    gateway.vnext.phase="1" \
    gateway.vnext.wheel.sha256="${WHEEL_SHA256}" \
    gateway.vnext.extension.sha256="${EXTENSION_SHA256}" \
    gateway.vnext.source.revision="${SOURCE_REVISION}"
ENV GATEWAY_SOURCE_REVISION="${SOURCE_REVISION}" \
    GATEWAY_EXPECTED_WHEEL_SHA256="${WHEEL_SHA256}" \
    GATEWAY_EXPECTED_EXTENSION_SHA256="${EXTENSION_SHA256}" \
    GATEWAY_INSTALLED_WHEEL_PATH="/opt/gateway/wheels/${GATEWAY_COMPUTE_WHEEL_BASENAME}"
RUN python --version | grep -F "${PYTHON_VERSION}" >/dev/null
RUN mkdir -p /opt/gateway/wheels
COPY backend/.phase-exit-build/${UV_WHEEL_BASENAME} /opt/gateway/wheels/${UV_WHEEL_BASENAME}
RUN printf '%s  /opt/gateway/wheels/%s\n' "${UV_WHEEL_SHA256}" "${UV_WHEEL_BASENAME}" | sha256sum -c -
RUN pip install --no-cache-dir "/opt/gateway/wheels/${UV_WHEEL_BASENAME}"
WORKDIR /app
COPY shared_kernel /app/shared_kernel
WORKDIR /app/backend
COPY backend/pyproject.container.toml ./pyproject.toml
COPY backend/uv.container.lock ./uv.lock
COPY backend/.python-version ./
COPY backend/src ./src
COPY backend/.phase-exit-build/${GATEWAY_COMPUTE_WHEEL_BASENAME} /opt/gateway/wheels/${GATEWAY_COMPUTE_WHEEL_BASENAME}
RUN printf '%s  /opt/gateway/wheels/%s\n' "${WHEEL_SHA256}" "${GATEWAY_COMPUTE_WHEEL_BASENAME}" | sha256sum -c -
COPY backend/.phase-exit-build/container-deps-wheels /opt/gateway/wheels/deps/
ENV UV_OFFLINE=1 \
    UV_FIND_LINKS=/opt/gateway/wheels/deps
RUN uv export --frozen --offline --no-dev --no-hashes --no-emit-project --no-emit-local \
        --output-file /tmp/requirements.txt \
    && uv venv .venv \
    && uv pip install --python .venv/bin/python --offline --no-index \
        --find-links /opt/gateway/wheels/deps --requirement /tmp/requirements.txt \
    && uv pip install --python .venv/bin/python --reinstall "/opt/gateway/wheels/${GATEWAY_COMPUTE_WHEEL_BASENAME}"
ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONPATH="/app/backend/src:/app/shared_kernel/src"
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["uvicorn", "gateway_backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
