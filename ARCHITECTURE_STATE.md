# FlowHub Architecture State

This file records the current architecture as implemented and verified in the repository. It is intended to be a standing reference for future Codex threads.

## Backend architecture

### Primary responsibility

The backend owns:

- Pricing Matrix persistence, validation, concurrency, activation, and immutable revision handling
- Source Acquisition runs, observations, assessments, diagnostics, and security boundaries
- Migration management
- Release verification and backend regression coverage

### Key backend boundaries

- `app/flowhub/pricing_matrix/` contains the declarative pricing engine and persistence/service layer.
- `app/flowhub/source_workspace/` contains the source/workspace integration boundaries.
- `app/flowhub/api/v2/` exposes callable backend APIs.
- `SourceHttpClient` is the only approved outbound network boundary for acquisition.

### Immutable backend rules

- Pricing policy revisions are immutable.
- Product group revisions are immutable.
- Channel configuration revisions are immutable.
- Channel policy lifecycle events are append-only.
- Runs are durable and have terminal lifecycle states.
- Source Observations are immutable.
- Schema assessments are immutable or append-safe, never rewritten in place.
- Security rejection fails closed and does not fabricate observation data.

## Frontend architecture

### Ownership boundary

- Claude UI owns the dedicated `FlowHub-Claude-UI` worktree and the Pricing Matrix UI implementation.
- The backend repo owns `FRONTEND_CONTRACT.md`, which is the callable backend contract for the current product surface.
- `docs/architecture/PRICING_UI_CONTRACT.md` is a proposed future architecture document, not the callable API contract.

### Frontend contract shape

- Requests use the documented casing in `FRONTEND_CONTRACT.md`.
- Responses are the documented object shapes and are authoritative.
- No shared envelope or `contract_version` exists on the callable API today.
- No pagination exists on the current callable Pricing Matrix lists.
- Exact monetary and identifier values must be treated as string-safe / BigInt-safe where JavaScript precision is involved.

## Pricing architecture

### Core model

The pricing system is a declarative matrix, not a runtime spreadsheet formula engine.

Core objects:

- Policy revisions
- Product group revisions
- Unit declarations
- Channel policy heads
- Lifecycle events
- Apply / review projections

### Pricing invariants

- No runtime pricing path evaluates arbitrary formula text.
- Pricing uses exact arithmetic and one final round.
- Policy creation is inert; per-Channel activation makes the policy effective.
- Apply is per Channel; a blocked Channel must not block a healthy Channel.
- All currency-unit declarations are explicit.
- IRR uses explicit `RIAL` or `TOMAN`; magnitude inference is forbidden.
- The backend performs every conversion; the frontend never derives currency conversions.
- Feature activation for formula migration stays disabled until inventory, fixtures, and the broken-formula gate are resolved.

### Current pricing release boundary

- The Pricing Matrix backend contract is implemented.
- The pricing UI is integrated in the dedicated Claude worktree.
- Migration activation remains gated by Appendix A / translator inventory / broken-formula remediation.

## Source Acquisition architecture

### Core model

Source Acquisition is split into durable, isolated domain steps:

1. Acquisition Run
2. Immutable Observation
3. Evidence / provenance
4. Schema assessment
5. Diagnostics
6. Workspace safety boundaries

### Acquisition invariants

- `SourceHttpClient` is the only approved network boundary.
- No direct ad hoc `httpx` / `requests` usage is allowed outside the approved abstraction.
- Runs are durable and terminal.
- Observations are immutable and append-only.
- Assessments are deterministic, versioned, and tied to an Observation plus the expected mapping/schema revision.
- Structural drift never mutates the source Observation.
- Security rejections happen before unsafe network access and do not create fabricated observations.

### Source design elements

- Execution policy snapshots are persisted with Runs.
- Provider change tokens are opaque and version-aware.
- Logical Resource Bindings are distinct from display metadata.
- Raw and canonical schema forms are both preserved.
- Drift detection is machine-readable and uses stable reason/action codes.

## Contracts

### Callable backend contract

- `FRONTEND_CONTRACT.md` is authoritative for currently callable Pricing Matrix endpoints.
- `PRICING_UI_CONTRACT.md` is future architecture only.
- Changes to routes, enums, error codes, request casing, or nullability must update `FRONTEND_CONTRACT.md` and `RESUME.md` together.

### Source acquisition design contract

- `docs/architecture/SOURCE_ACQUISITION_DESIGN.md` is the implementation-facing Source design.
- `ADR_SOURCE_ARCHITECTURE_V2.md` is the stable decision record.
- Schema assessment, observations, and acquisition security are now explicitly modeled and versioned.

## Important ownership boundaries

- Backend owns safety, persistence, and execution truth.
- Frontend owns presentation only and must not infer hidden server state.
- Deployment owns private-network configuration, secrets, and environment-specific allow-lists.
- Review/Apply safety remains server-side.
- Pricing activation remains separate from pricing UI availability.
