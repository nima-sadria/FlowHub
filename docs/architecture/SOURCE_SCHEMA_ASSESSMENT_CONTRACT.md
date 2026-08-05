# Source Schema Assessment Contract

## Scope

This contract defines persisted schema compatibility facts for an immutable
Source Observation. It does not define provider acquisition, mapping mutation,
drift approval, scheduling, or a callable UI/API.

## Identity and Immutability

An assessment is uniquely identified by:

```text
(observation_id, mapping_identity, assessment_algorithm_version)
```

`mapping_identity` is either `mapping:{mapping_revision_id}` or `no_mapping`.
The same identity replays the same immutable Assessment. A different semantic
input conflicts rather than overwriting it. Assessment, expectation, Diff, and
Diagnostic records are append-only application records.

Expected headers are frozen in `SourceMappingSchemaExpectation`, one record per
Mapping revision. Raw observed headers are read only from the Observation's
`schema_headers` Evidence and are copied into the Assessment. Neither raw
representation is overwritten by canonicalization.

## Versions and Fingerprints

- canonicalization: `header-canonical-v1`
- assessment algorithm: `schema-assessment-v1`

The canonical form uses NFKC, maps Arabic Yeh/Kaf to Persian forms, removes
bidi controls, removes whitespace and ZWNJ for comparison, and applies Unicode
casefolding. Raw values remain unchanged. Fingerprints are SHA-256 checksums of
stable JSON containing algorithm/version, representation kind, and ordered
headers.

## Status Axes

Execution status and freshness are separate.

```text
execution: not_run | pending | running | passed | failed | skipped | not_applicable
freshness: current | stale | unknown
schema: match | drift | ambiguous | no_mapping | null
```

`schema` is null when comparison did not run. `failed`, `skipped`, `not_run`,
and `not_applicable` never imply successful compatibility.

Freshness is a read-time projection, not a mutation of an Assessment fact. It
is `stale` when the assessment algorithm is no longer current, a newer
Observation exists for the same Source/scope, or a newer Mapping revision
exists. It is `unknown` for non-comparison execution states. The persisted
freshness basis records Observation checksum/version/timestamp, Mapping
checksum/expectation checksum, and algorithm versions.

## Drift and Diagnostics

The structural Diff kinds are `added`, `removed`, `reordered`,
`rename_candidate`, `duplicate_header`, `canonical_collision`,
`required_field_missing`, and `unsupported_shape`.

`rename_candidate` is emitted only for exactly one removed and one added header
at the same position, with `exact_position` confidence and explicit evidence.
One removed/added pair at different positions is `ambiguous`; no rename is
invented.

Diagnostics persist only stable fields: stage ID, execution status, reason code,
recommended action code, bounded parameters, and timestamp. They do not store
localized prose, credentials, tokens, or upstream exception bodies. No Stage 7
operation approves or applies a schema change.
