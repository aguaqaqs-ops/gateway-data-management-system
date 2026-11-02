# Gateway Data Management frontend

This is the new React/TypeScript frontend. `src/features/` contains functional
logic and generated API types, `src/design-system/` contains shared visual
tokens and components, and `src/pages/` contains routed page composition.
The current FE0 page is only a workspace shell; business flows are implemented
in later frontend stages.

Dependencies are pinned exactly in `package.json` and `package-lock.json`.
Generate API types after updating the checked-in `openapi.json` snapshot with:

```bash
npm run generate:api-types
```

The authoritative test entry is `scripts/run-tests.sh`. It runs in the fixed
Playwright toolchain image and needs the prefilled npm cache at
`/home/dev/gdds-fe-cache/fe0/npm-cache`. It installs with `npm ci --offline`
inside a disposable container, then runs type checking, lint, unit tests, and
the production build. Pass `--e2e` to also run Playwright browser tests.
