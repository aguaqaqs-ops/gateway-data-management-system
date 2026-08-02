# P2-R1 persistent dependency cache

This is a development-host cache for the repository-service target image. It
is intentionally outside Docker images, containers, and named volumes so that
matrix cleanup does not remove it. The cache is served only on the Docker
bridge gateway (`172.17.0.1:18080`) by
`gateway-p2r1-dependency-cache.service`.

The current pinned artifact is:

```text
/dolt/2.1.11/dolt-linux-amd64.tar.gz
```

The remote development host also retains a dependency-base image containing
the lock-resolved Python 3.14 environment, Dolt 2.1.11 and uv 0.11.28. It is a
build accelerator, not a production release image; keep it when cleaning probe
containers and named volumes.

The verified retained image tags from the 2026-08-02 build are:

```text
gateway-p2r1-repository:dependency-base-python3.14-dolt2.1.11-uv0.11.28
gateway-p2r1-repository:20260802-cached
```

The cache also retains the exact uv 0.11.28 wheel under both its versioned
artifact path and the small PEP 503 bootstrap index at `/uv/simple/uv/`.

The service and cache directory are persistent across Docker restarts and host
reboots. Do not remove them as part of probe cleanup. Add a new versioned
artifact directory for dependency updates; retain old versions until no active
build references them.

The formal probe's test named volume, matrix container and temporary build
contexts may be removed after results are copied. The two image tags above and
the versioned cache artifacts must remain available for subsequent source-only
rebuilds.

## Remote host setup

Run as root on the development host:

```sh
install -d -o gateway-p2r1-cache -g gateway-p2r1-cache \
  /var/lib/gateway/p2r1-dependency-cache/dolt/2.1.11
install -m 0644 dolt-linux-amd64.tar.gz \
  /var/lib/gateway/p2r1-dependency-cache/dolt/2.1.11/dolt-linux-amd64.tar.gz
install -m 0644 gateway-p2r1-dependency-cache.service \
  /etc/systemd/system/gateway-p2r1-dependency-cache.service
systemctl daemon-reload
systemctl enable --now gateway-p2r1-dependency-cache.service
```

The `gateway-p2r1-cache` system user must own the cache directory. The service
is read-only and has no write access outside that directory.

## Cached build

From the `vnext` Docker build context, pass the cache URL and preserve the
Docker service proxy for PyPI/uv dependencies:

```sh
docker build \
  --network=host \
  --build-arg DOLT_DOWNLOAD_URL=http://172.17.0.1:18080/dolt/2.1.11/dolt-linux-amd64.tar.gz \
  --build-arg UV_BOOTSTRAP_INDEX_URL=http://172.17.0.1:18080/uv/simple \
  --build-arg UV_BOOTSTRAP_TRUSTED_HOST=172.17.0.1 \
  --build-arg HTTP_PROXY \
  --build-arg HTTPS_PROXY \
  --build-arg NO_PROXY=172.17.0.1,localhost,127.0.0.1 \
  --tag gateway-p2r1-repository:dev \
  --file repository_service/Dockerfile .
```

`UV_BOOTSTRAP_INDEX_URL` remains public by default and only controls installing
the pinned uv bootstrap wheel. The Docker layer created by
`uv sync --frozen` is retained by Docker for source-only rebuilds. A future
full Python package mirror can be wired to uv separately without changing the
artifact-cache contract. When the persistent dependency-base image is
available, the formal Dockerfile can reuse it without network downloads:

```sh
docker build --network=host \
  --build-arg BASE_IMAGE=gateway-p2r1-repository:dependency-base-python3.14-dolt2.1.11-uv0.11.28 \
  --build-arg USE_PRELOADED_DEPENDENCIES=1 \
  --tag gateway-p2r1-repository:dev \
  --file repository_service/Dockerfile .
```
