# Bootstrap toolchain and hosting capability record

## Toolchain pins

| Component | Pin | Evidence and limit |
| --- | --- | --- |
| Node.js | 24.13.0 | Measured in this workspace; `.node-version`, the smoke test, and CI enforce the patch; root `engines` checks major compatibility |
| pnpm | 10.26.1 | Measured in this workspace; root `packageManager`, CI, and `pnpm-lock.yaml` |
| Python | 3.13.11 | Measured in this workspace; `.python-version`, `pyproject.toml`, and CI enforce the patch |
| uv | 0.9.24 | Measured in this workspace; `pyproject.toml` and CI enforce the version |
| Replit Nix channel | `stable-25_05` | Recorded in `.replit` |
| pytest | 9.1.1 | Exact development dependency; package hashes are recorded in `uv.lock` |
| Ruff | 0.16.10 | Exact development dependency; package hashes are recorded in `uv.lock` |
| TypeScript and JavaScript dependencies | Exact lockfile resolutions | `pnpm-lock.yaml` records versions and integrity data |
| PostgreSQL | 16 target major | Replit documentation reports PostgreSQL 16 support; no database is provisioned here and its provider patch/build digest is not observed |
| Android SDK / JVM / build tool | Not selected | The active workspace has no Java or Gradle executable and no Android SDK. The available Java module is not installed or verified for Android builds. `apps/android` remains an empty product boundary |

The current Replit modules select Node.js 24 and Python 3.13 by minor version.
The exact patch pins above are enforced by project files, CI, and the smoke test;
a platform patch drift must fail verification rather than pass silently. Do not
claim an Android toolchain or PostgreSQL patch-level reproduction until those
components are actually available and measured.

The workspace's `node` and `pnpm exec node` report 24.13.0, while pnpm's install
engine warning reported 24.12.0. The root engine range therefore checks Node 24
compatibility; exact patch enforcement remains in `.node-version`, CI, and the
smoke check instead of treating pnpm's reported patch as authoritative.

## Reproduction commands

```sh
pnpm install --frozen-lockfile
uv sync --locked
pnpm run verify
```

`pnpm-lock.yaml` and `uv.lock` are committed dependency locks. Do not use floating
`latest` dependencies or bypass locked installation in CI.

## Hosting and resource checklist

| Capability | Status in this checkout |
| --- | --- |
| Scheduling while the editor is idle | Unverified; development workflows do not prove durable scheduling |
| Persistent PostgreSQL access | Not provisioned or verified |
| Persistent object/artifact storage | Not provisioned or verified |
| Production secrets isolated from research and development | No production runtime or credentials configured; deployment isolation not tested |
| Outbound provider access | Not configured or tested; no runtime fallback is permitted |
| Maximum job runtime and resource budgets | Not measured |
| Restart recovery, duplicate prevention, and concurrency limits | Not measured |
| Storage quotas and backup/restore behavior | Not provisioned or tested |
| Runtime separation between core, execution, research, owner API, and promotion | Not implemented or demonstrated |
| Cost and resource ceilings | Not measured; no paid resource requested |

## Deployment-isolation decision

This checkout is development-only. No deployment has been activated. The existing
`deploymentTarget = "autoscale"` entry in `.replit` is inherited scaffold
configuration, not an approved hosting selection and not evidence of an
unattended worker. Do not use the development preview or that setting for durable
research scheduling, execution, or production authority.

Before any unattended or production workload, measure and record the checklist
above and demonstrate separate credentials and process permissions for the
execution, research, owner API, and promotion boundaries. If the selected host
cannot enforce those boundaries, use separately permissioned deployments or an
isolated worker environment. No paid service or production credential was
requested or added by this bootstrap.

PostgreSQL version reference: [Replit development and production databases](https://docs.replit.com/features/data-and-storage/development-and-production)
(checked 2026-10-06). The managed service version must be recorded when a database
is provisioned; this bootstrap does not claim a live database test.
