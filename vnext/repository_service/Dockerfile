FROM python:3.14.6-slim-bookworm
ARG UV_VERSION=0.11.28
ARG DOLT_VERSION=2.1.11
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl \
    && curl -fsSL "https://github.com/dolthub/dolt/releases/download/v${DOLT_VERSION}/dolt-linux-amd64.tar.gz" -o /tmp/dolt.tar.gz \
    && tar -xzf /tmp/dolt.tar.gz -C /tmp \
    && install -m 0755 /tmp/dolt-linux-amd64/bin/dolt /usr/local/bin/dolt \
    && rm -rf /tmp/dolt.tar.gz /tmp/dolt-linux-amd64 /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==${UV_VERSION}
WORKDIR /app
COPY repository_service/pyproject.toml repository_service/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY repository_service/src ./src
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH="/app/src"
CMD ["python", "-c", "from gateway_repository_service import RepositoryServiceSettings; print(RepositoryServiceSettings())"]
