# QuantraCore Apex Gen 2

Repository bootstrap for a private, single-owner runner-intelligence and paper-trading system. This task establishes boundaries and reproducible tooling only; it does not implement scientific, trading, or owner-facing behavior.

## Run & Operate

- `pnpm install --frozen-lockfile` — install the locked JavaScript workspace
- `uv sync --locked` — install the locked Python development tools in a local environment
- `pnpm run lint` — run Ruff and metadata formatting checks
- `pnpm run typecheck` — typecheck the inherited workspace packages
- `pnpm run test` — run Python tests
- `pnpm run smoke` — run the workspace import and Python runtime smoke checks
- `pnpm run verify` — run lint, typecheck, test, and smoke checks

The API server and mockup workflows are inherited Replit scaffolding, not approved product authorities or proof of a production runtime. Do not assume a database connection exists.

## Stack

- Node.js 24.13.0, pnpm 10.26.1, Python 3.13.11, and uv 0.9.24
- TypeScript dependencies are locked by `pnpm-lock.yaml`; Python tools are locked by `uv.lock`
- PostgreSQL 16 is the selected target major; no database is provisioned or verified in this workspace
- `apps/android` is reserved; no Kotlin, Compose, Android SDK, or product behavior is included

## Repository map

- `packages/` — product module boundaries listed in `docs/REPOSITORY_BOUNDARIES.md`
- `apps/android/` — reserved Android client boundary
- `migrations/` — immutable, forward-only schema changes
- `tests/`, `tools/`, and `docs/` — verification, repository tooling, and source-of-truth documentation
- `artifacts/`, `lib/`, and `scripts/` — inherited Replit workspace scaffolding; not substitutes for product authorities

## Architecture decisions

- Authority and import boundaries are documented in `docs/REPOSITORY_BOUNDARIES.md`.
- Environment separation and secret handling are documented in `docs/ENVIRONMENTS.md`.
- Hosting capability limits and unresolved toolchain decisions are recorded in `docs/BOOTSTRAP_TOOLCHAIN.md`.
- Runtime processes must not share all-powerful credentials; the current workspace and inherited Autoscale setting are not evidence of unattended hosting isolation.

## Product

This bootstrap contains no production product behavior. Follow the canonical task contracts before adding authorities, data providers, execution behavior, or Android functionality.

## Gotchas

- Keep `pnpm-lock.yaml` and `uv.lock` committed and use their frozen/locked install modes.
- Do not put credentials, generated market history, datasets, or model binaries in source control.
- No deployment or downstream task is activated by this bootstrap.

## Pointers

- `docs/GEN2_MASTER_SPEC.md` — governing architecture and invariants
- `docs/REPOSITORY_BOUNDARIES.md` — package ownership and dependency rules
- `docs/BOOTSTRAP_TOOLCHAIN.md` — toolchain pins and capability checklist
