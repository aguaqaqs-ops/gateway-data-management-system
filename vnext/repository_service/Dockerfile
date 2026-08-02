FROM python:3.14.6-slim-bookworm
ARG UV_VERSION=0.11.28
ARG DOLT_VERSION=2.1.11
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/dolthub/dolt/releases/download/v${DOLT_VERSION}/dolt-linux-amd64.tar.gz', '/tmp/dolt.tar.gz')" \
    && tar -xzf /tmp/dolt.tar.gz -C /tmp \
    && install -m 0755 /tmp/dolt-linux-amd64/bin/dolt /usr/local/bin/dolt \
    && rm -rf /tmp/dolt.tar.gz /tmp/dolt-linux-amd64 \
    && pip install --no-cache-dir uv==${UV_VERSION}
WORKDIR /app
COPY repository_service/pyproject.toml repository_service/uv.lock ./
COPY repository_contracts/pyproject.toml repository_contracts/uv.lock /repository_contracts/
COPY repository_contracts/src /repository_contracts/src
RUN uv sync --frozen --no-install-project --all-groups
COPY repository_service/src ./src
RUN addgroup --system gateway && adduser --system --ingroup gateway gateway \
    && mkdir -p /var/lib/gateway/repository \
    && chown -R gateway:gateway /var/lib/gateway
USER gateway
ENV HOME="/home/gateway"
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH="/app/src"
CMD ["python", "-c", "from gateway_repository_service import RepositoryServiceSettings; print(RepositoryServiceSettings())"]
