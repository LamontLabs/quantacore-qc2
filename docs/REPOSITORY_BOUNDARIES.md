# Repository boundaries

These directories define the product boundaries required by `docs/GEN2_MASTER_SPEC.md`.
Bootstrap creates the boundaries only; it does not implement domain authorities.

| Boundary | Owns | Must not |
| --- | --- | --- |
| `packages/contracts` | Versioned shared schemas, types, and messages | Persist domain state or make decisions |
| `packages/science` | Deterministic scientific transforms over explicit, versioned inputs | Perform network I/O, persistence, or execution side effects |
| `packages/core` | Core domain coordination through narrowly authorized operations | Become a catch-all writer or bypass an authority boundary |
| `packages/execution` | Paper execution intent and reconciliation boundaries | Place live trades, train models, or use runtime provider/feed fallback |
| `packages/apexlab` | Research datasets, experiments, and candidate artifacts | Mutate production authority or receive execution credentials |
| `packages/owner_api` | Authenticated read projections and narrow owner commands | Expose arbitrary SQL, code execution, or direct broker calls |
| `packages/promotion` | Eligibility verification and restricted promotion transitions | Self-certify a candidate or override a failed verifier |
| `apps/android` | Owner-facing Kotlin/Compose client boundary | Become an authority or write state outside approved owner commands |
| `migrations` | Versioned, forward-only schema changes | Run automatically at application startup or rewrite applied history |
| `tests` | Tests for contracts, boundaries, and authorized behavior | Treat fixtures or synthetic evidence as production truth |
| `tools` | Repository maintenance and explicit operator tooling | Hold runtime authority or embed credentials |
| `docs` | Specifications, decisions, operating limits, and evidence references | Replace machine-enforced authorization controls |

## Dependency and runtime rules

- Contracts are the shared compile-time boundary. Runtime services must communicate
  through explicit contracts rather than importing another service's private
  persistence or authority implementation.
- Scientific computation must remain deterministic and side-effect free.
- Execution, research, owner access, and promotion require separately scoped runtime
  identities. Shared source files do not justify shared all-powerful credentials.
- Owner API commands are narrow requests; the owning authority performs and records
  the actual state transition.
- Schema migration credentials are offline from application processes.
- Existing `artifacts/`, `lib/`, and `scripts/` directories are inherited Replit
  scaffolding. They are not product authority packages or evidence of a production
  deployment boundary.
