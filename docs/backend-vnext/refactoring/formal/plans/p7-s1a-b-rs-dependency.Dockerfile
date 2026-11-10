FROM gateway-p2r1-repository:lock-6dc9659f0aee
ARG SOURCE_COMMIT
ARG BUILD_INPUT_REVISION
ARG SOURCE_TREE_SHA256
ARG DEPENDENCY_INPUT_SHA256
COPY uv.lock /tmp/gateway-repository-uv.lock
COPY rfc8785-0.1.4-py3-none-any.whl /tmp/rfc8785-0.1.4-py3-none-any.whl
RUN echo 'b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f  /tmp/gateway-repository-uv.lock' | sha256sum -c - \
    && echo '520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48  /tmp/rfc8785-0.1.4-py3-none-any.whl' | sha256sum -c - \
    && UV_OFFLINE=1 uv --no-config pip install --no-index --no-deps --python /app/.venv/bin/python /tmp/rfc8785-0.1.4-py3-none-any.whl \
    && uv --no-config pip check --python /app/.venv/bin/python \
    && rm /tmp/rfc8785-0.1.4-py3-none-any.whl
LABEL org.opencontainers.image.title="gateway-p2r1-repository-dependency-base" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      gateway.p2r1.build-input-revision="${BUILD_INPUT_REVISION}" \
      gateway.p2r1.source-tree-sha256="${SOURCE_TREE_SHA256}" \
      gateway.p2r1.dependency-input-sha256="${DEPENDENCY_INPUT_SHA256}" \
      gateway.p2r1.uv-lock-sha256="b47d6de3cbcef1052422efd4c8e1a0288aac14f96f1eaf6baa3276a219cc316f" \
      gateway.p2r1.dolt-version="2.1.11" \
      gateway.p2r1.uv-version="0.11.28" \
      gateway.p2r1.mysql-connector-version="9.7.0" \
      gateway.p2r1.pyarrow-version="25.0.0" \
      gateway.p2r1.cache-policy="retain-for-development-rebuilds"
