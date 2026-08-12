ARG BASE_IMAGE=python:3.14.6-slim-bookworm
FROM ${BASE_IMAGE}
ARG UV_VERSION=0.11.28
ARG DOLT_VERSION=2.1.11
ARG DOLT_SHA256=7e5583b7e35ad329fe3f4705cf51db29be583bd50fd801516237d593210524d3
ARG UV_LOCK_SHA256=6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
ARG BUILD_REVISION=unknown
ARG SOURCE_TREE_SHA256=unknown
ARG MYSQL_CONNECTOR_VERSION=9.7.0
ARG PYARROW_VERSION=25.0.0
ARG DOLT_DOWNLOAD_URL
ARG UV_BOOTSTRAP_INDEX_URL=https://pypi.org/simple
ARG UV_BOOTSTRAP_TRUSTED_HOST
ARG USE_PRELOADED_DEPENDENCIES=0
RUN if [ "${USE_PRELOADED_DEPENDENCIES}" = "1" ]; then \
      test -x /usr/local/bin/dolt && test -x /usr/local/bin/uv; \
    else \
      python -c "import urllib.request; url='${DOLT_DOWNLOAD_URL}' or 'https://github.com/dolthub/dolt/releases/download/v${DOLT_VERSION}/dolt-linux-amd64.tar.gz'; urllib.request.urlretrieve(url, '/tmp/dolt.tar.gz')" \
         && echo "${DOLT_SHA256}  /tmp/dolt.tar.gz" | sha256sum -c - \
         && tar -xzf /tmp/dolt.tar.gz -C /tmp \
         && install -m 0755 /tmp/dolt-linux-amd64/bin/dolt /usr/local/bin/dolt \
         && rm -rf /tmp/dolt.tar.gz /tmp/dolt-linux-amd64 \
         && if [ -n "${UV_BOOTSTRAP_TRUSTED_HOST}" ]; then \
              pip install --no-cache-dir --index-url="${UV_BOOTSTRAP_INDEX_URL}" --trusted-host "${UV_BOOTSTRAP_TRUSTED_HOST}" uv==${UV_VERSION}; \
            else \
              pip install --no-cache-dir --index-url="${UV_BOOTSTRAP_INDEX_URL}" uv==${UV_VERSION}; \
            fi; \
    fi
WORKDIR /app
COPY repository_service/pyproject.toml repository_service/uv.lock ./
RUN test "$(sha256sum uv.lock | cut -d ' ' -f1)" = "${UV_LOCK_SHA256}"
COPY repository_contracts/pyproject.toml repository_contracts/uv.lock /repository_contracts/
COPY repository_contracts/src /repository_contracts/src
RUN if [ "${USE_PRELOADED_DEPENDENCIES}" = "1" ]; then \
      test -d /app/.venv/lib/python3.14/site-packages; \
    else \
      uv sync --frozen --no-install-project --all-groups; \
    fi
RUN test "$(/usr/local/bin/dolt version | awk '$1 == "dolt" && $2 == "version" && $3 ~ /^[0-9]+\.[0-9]+\.[0-9]+$/ { print $3; exit }')" = "${DOLT_VERSION}" \
    && test "$(uv --version | awk '{print $2}')" = "${UV_VERSION}" \
    && uv pip check --python /app/.venv/bin/python
COPY repository_service/src ./src
COPY repository_service/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh \
    && addgroup --system gateway \
    && adduser --system --ingroup gateway gateway \
    && addgroup --system artifact-broker \
    && adduser --system --ingroup artifact-broker artifact-broker \
    && usermod -a -G gateway artifact-broker \
    && mkdir -p /home/gateway /home/artifact-broker /var/lib/gateway/repository/run /var/lib/gateway/repository/artifacts \
    && chown -R gateway:gateway /home/gateway \
    && chown -R artifact-broker:artifact-broker /home/artifact-broker \
    && chown gateway:gateway /var/lib/gateway /var/lib/gateway/repository \
    && chown artifact-broker:gateway /var/lib/gateway/repository/run /var/lib/gateway/repository/artifacts \
    && chmod 0750 /var/lib/gateway/repository/run /var/lib/gateway/repository/artifacts
ENV HOME="/home/gateway"
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH="/app/.venv/lib/python3.14/site-packages:/app/src:/repository_contracts/src"
# Entrypoint starts as root, launches artifact-broker, then drops to gateway (ADR 0011).
USER root
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
LABEL org.opencontainers.image.revision="${BUILD_REVISION}" \
      gateway.p2r1.source-tree-sha256="${SOURCE_TREE_SHA256}" \
      gateway.p2r1.mysql-connector-version="${MYSQL_CONNECTOR_VERSION}" \
      gateway.p2r1.pyarrow-version="${PYARROW_VERSION}" \
      gateway.p2r1.dolt-version="${DOLT_VERSION}" \
      gateway.p2r1.uv-version="${UV_VERSION}" \
      gateway.p2r1.uv-lock-sha256="${UV_LOCK_SHA256}" \
      gateway.p2r1.cache-policy="retain-for-development-rebuilds"
CMD ["python", "-m", "uvicorn", "gateway_repository_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
