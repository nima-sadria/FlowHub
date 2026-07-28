# Metrics Model

## Metric Classes

- **Process metrics:** in-memory counters and latency observations that reset
  on process restart.
- **Durable operational metrics:** persisted Connector telemetry, job facts,
  and daily aggregates.
- **Business metrics:** values derived from confirmed history and scoped
  domain records.

An API MUST disclose the class, time window, unit, and reset semantics.

## Required Dimensions

Metrics MAY be grouped by owner, Connector type/instance, operation, transport,
job state, and time bucket. High-cardinality identifiers MUST be bounded.

## Correctness

- Request acceptance is not write success.
- Retries, rate limits, and unknown outcomes are separate counters.
- Percentiles require a documented sampling/aggregation method.
- Empty data is not zero unless the metric definition says so.
- Durable and process-reset values MUST NOT be added without an explicit
  interpretation.

## Current Boundary

FlowHub persists Connector telemetry but also exposes runtime-derived
information. Durable long-term retention and reset policy require explicit
Owner decisions before metrics are treated as historical reporting.

