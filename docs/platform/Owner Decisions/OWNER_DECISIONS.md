# Platform Owner Decisions

## Approved

### OD-001: FlowHub is canonical

Reference documents are evidence. FlowHub terminology, architecture, and
provider-neutral behavior define the product.

### OD-002: Granular Workspace authorization

Canonical named capabilities are exposed through `/api/auth/me` and enforced
at route and action boundaries. Legacy aliases are compatibility only.

### OD-003: Audit remediation scope

Small and medium contract, recovery, validation, and presentation gaps may be
fixed during adoption when they do not alter architecture.

## Required

### OD-004: Canonical Workspace entry point

Choose the canonical route, compatibility period, redirect behavior, saved-link
support, and retirement plan for legacy `/workspace` and unified
`/workspace/:workspaceId`.

### OD-005: Exact-operation confirmation object

Approve either a persisted pre-Apply operation manifest or immutable Review
items plus selection checksum as the canonical confirmation object. The
decision must cover invalidation, operation presentation, idempotency, and API
compatibility.

### OD-006: Legacy permission retirement

Select the release and telemetry gate for removing legacy `can_*` aliases.

### OD-007: Reference publication

Decide whether the Owner-provided reference source documents should be
committed as archived evidence. Canonical rules are already merged here.

### OD-008: Retention and archival

Define retention, legal/audit requirements, archive format, deletion
authorization, and restore behavior for audit, operation, history, diagnostics,
webhook, metric, and log records.

### OD-009: Durable diagnostic history

Decide whether diagnostic runs require a persisted history API, ownership
scope, retention, and export.

### OD-010: Alert transport

Choose whether FlowHub needs durable alerts and external delivery. Define
channels, deduplication, acknowledgement, escalation, and secret handling.

### OD-011: Immutable report artifacts

Decide whether management reports require durable snapshots with query,
filters, source watermarks, generated-at time, and retention.

### OD-012: Connector activation transaction

Approve the canonical candidate/verification/activation persistence boundary
for active runtime configuration. Current local Integration Platform metadata
is read-only/unverified and must not be mistaken for activated configuration.

## Decision Template

Every new decision records affected invariants, API and persistence impact,
compatibility, migration, authorization, tests, rollout, and rollback.

