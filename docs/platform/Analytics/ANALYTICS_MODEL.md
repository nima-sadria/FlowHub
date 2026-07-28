# Analytics Model

## Authority

Operational analytics derive from owner-scoped confirmed history, durable job
facts, and explicit cache/snapshot records. Raw attempts alone cannot establish
successful business change.

## Required Provenance

Every analytical response SHOULD identify:

- metric definition and unit;
- source record families;
- owner/resource scope;
- time window and timezone;
- freshness or generated-at time;
- exclusions and partial-data warnings.

## Standard Views

- Workspace throughput and outcome distribution;
- Connector availability and freshness;
- confirmed change history;
- reconciliation backlog;
- Source coverage and data quality;
- Channel cache coverage;
- job latency, retries, and failure classes.

## Safety

Analytics are read models. They MUST NOT define Apply scope, mutate operational
state, or hide partial/unknown outcomes. Cross-owner analytics require the same
reasoned administrative override as cross-owner audit reads.

## Durable Reports

FlowHub does not currently define a canonical immutable report artifact store.
Exports are projections unless explicitly persisted with query, filters,
generated-at time, and source watermark. Report artifact retention requires an
Owner decision.

