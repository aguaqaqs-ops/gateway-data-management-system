# Gateway Data Management frontend

This is the new React/TypeScript frontend. `src/features/` contains functional
logic and generated API types, `src/design-system/` contains shared visual
tokens and components, and `src/pages/` contains routed page composition.
FE1 supplies the authenticated OpenAPI client, operation and journey data
flows, verified local tar bundle storage, lazy Parquet access, view-model and
URL command layers, and reusable P1/P2 design-system components. The sample
page is a component preview; full business screens follow in FE2.

Dependencies are pinned exactly in `package.json` and `package-lock.json`.
Generate API types after updating the checked-in `openapi.json` snapshot with:

```bash
npm run generate:api-types
```

The authoritative test entry is `scripts/run-tests.sh`. It runs in the fixed
Playwright toolchain image and installs with `npm ci --offline` inside a
disposable container, then runs type checking, lint, unit tests, and the
production build. Pass `--e2e` to also run Playwright browser tests.

The stage-neutral defaults are `/home/dev/gdds-fe-cache/frontend/npm-cache`
for the npm cache, `/home/dev/gdds-fe-cache/frontend/npm-cacache.tar.gz` for
the source archive, and `/home/dev/gdds-fe-logs/frontend` for logs. Override
them with `GATEWAY_FRONTEND_NPM_CACHE`,
`GATEWAY_FRONTEND_NPM_CACHE_ARCHIVE`, and `GATEWAY_FE_LOG_DIR` when a node uses
different prepared paths.

When changing dependencies on CT201, keep every lockfile `resolved` source at
`https://registry.npmjs.org/`. The LAN registry is only for fetching package
tarballs; do not write its host into `package-lock.json`. The test entry rejects
nonofficial `resolved` hosts.

The Docker network defaults to `none`, which is suitable for mocked-backend
browser tests. FE3 browser tests that connect to a real backend need host
networking or an explicitly reachable backend address, configured with
`GATEWAY_FRONTEND_DOCKER_NETWORK` and `GATEWAY_FRONTEND_ENTRY_ORIGIN`.

All ordinary API requests carry the immutable session's Bearer and exact device
route key. Long workflows stop with “会话已变化” if that session is replaced.
The real backend runner owns two isolated processing groups and a public Nginx
entry; every scope is registered with `add-device`. Browser traffic uses the
entry, while OpenAPI comparison reads a controlled backend loopback directly.
`--suite journeys --subphase s2b-routing` runs only the synthetic routing and hot
add browser checks. Normal journeys also include those checks; t1 runs only at
the agreed evidence point. The runner owns its node marker and Compose cleanup.
