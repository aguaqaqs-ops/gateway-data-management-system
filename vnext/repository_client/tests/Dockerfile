ARG BASE_IMAGE=python:3.14.6-slim-bookworm
FROM ${BASE_IMAGE}
ARG UV_VERSION=0.11.28
ARG UV_LOCK_SHA256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
ARG CANDIDATE_SHA=unknown
ARG UV_BOOTSTRAP_INDEX_URL=https://pypi.org/simple
ARG UV_BOOTSTRAP_TRUSTED_HOST
ARG USE_PRELOADED_DEPENDENCIES=0
USER root
RUN if [ "${USE_PRELOADED_DEPENDENCIES}" = "1" ]; then \
      test -x /usr/local/bin/uv; \
    elif [ -n "${UV_BOOTSTRAP_TRUSTED_HOST}" ]; then \
      pip install --no-cache-dir --index-url="${UV_BOOTSTRAP_INDEX_URL}" --trusted-host "${UV_BOOTSTRAP_TRUSTED_HOST}" uv==${UV_VERSION}; \
    else \
        pip install --no-cache-dir --index-url="${UV_BOOTSTRAP_INDEX_URL}" uv==${UV_VERSION}; \
    fi
WORKDIR /src/repository_client
COPY repository_contracts /src/repository_contracts
COPY repository_client/pyproject.toml repository_client/uv.lock ./
RUN test "$(sha256sum uv.lock | cut -d ' ' -f1)" = "${UV_LOCK_SHA256}"
COPY repository_client/src ./src
COPY repository_client/tests/support ./tests/support
RUN if [ "${USE_PRELOADED_DEPENDENCIES}" = "1" ]; then \
      test -d /src/repository_client/.venv/lib/python3.14/site-packages; \
    else \
      uv sync --frozen --group dev; \
    fi \
    && printf '%s' "${CANDIDATE_SHA}" | grep -Eq '^[0-9a-f]{40}$' \
    && printf '%s' "${UV_LOCK_SHA256}" | grep -Eq '^[0-9a-f]{64}$'
ENV PATH="/src/repository_client/.venv/bin:${PATH}"
LABEL org.opencontainers.image.revision="${CANDIDATE_SHA}" \
      gateway.p2r6.client-uv-lock-sha256="${UV_LOCK_SHA256}"
USER nobody
CMD ["python", "/src/repository_client/tests/support/versioned_fixture_consumer.py"]
