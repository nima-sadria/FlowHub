# FlowHub v1.3 PDF Bug Remediation

Acceptance reference: `Flowhuib bug.pdf` (five pages), preserved as page images under
`docs/screenshots/v1.3/pdf-bug-remediation/reference/`.

## Safety boundary

The browser audit uses only `http://127.0.0.1:4188`, an in-process isolated API fixture,
synthetic Sources and Channels, and an installed local Chrome executable. The
fixture rejects every non-local request and every unregistered API request. No
database, credential, Source, marketplace endpoint, Apply, Publish, Refresh, or
external write is available to the fixture.

## Finding matrix

| PDF page | Screenshot area / route | Classification | Reproduction and root cause | Correction | Regression evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | Managed Sources, `/sources` | Behavioral / safety | A managed Source had only Open and Configure actions. There was no lifecycle impact check or permission-gated destructive action. | Added an admin-only, confirmation-first lifecycle flow. The server locks and rechecks the Source version. Active Workspace ownership blocks removal; protected immutable history converts removal to archive; only an unused Source is physically deleted. Every completed lifecycle action appends Audit evidence. | `test_source_lifecycle.py`, `SourceCenter.test.tsx`, `source-delete-confirmation-en-1280x720.png`, `source-archived-result-en-1280x720.png` |
| 1 | Source configuration, `/sources/:sourceId` | UX / translation | Seller guidance exposed implementation language and used Mapping terminology in the primary workflow. | Replaced primary copy with practical descriptions of worksheets, starting rows, column choices, disabled fields, and blank/x/dash/zero/formula handling. Normal labels use Column setup / تنظیم ستون‌ها; technical names remain internal. | `SourceConfiguration.test.tsx`, English and Persian configuration screenshots |
| 1 | Worksheet rules | Behavioral / data | The saved configuration represented all sheets or one sheet; it could not express shared rules for an arbitrary selected subset, and separate layouts were not explicit. | Added immutable, versioned shared and per-worksheet rule sets. Shared rules may target selected sheet identities; per-sheet sections control inclusion, start row, Source fields, Channel fields, and value policies independently. The workbook is acquired once and resolved in memory. Duplicate cross-sheet identity handling is explicit (`block` or user-selected last-sheet-wins). | `test_worksheet_rules.py`, `test_source_workspace_019.py`, four shared/per-sheet viewport screenshots |
| 1 | Source preview statistics | Data / UX | Counts were technical and the client fallback counted issues instead of distinct affected product rows. | Preview now reports distinct products found, ready, needing attention, and Channel readiness. The typed preview contract carries worksheet identity and issue-aware readiness, so Ready/Attention filters cannot disagree with the server. Price/stock/unchanged comparisons remain explicitly unavailable until Channel comparison rather than showing invented zeroes. Cards filter rows where a meaningful row filter exists; internal revision details stay secondary. | Source Workspace service tests, `SourceConfiguration.test.tsx`, `source-preview-business-summary-en-1440x900.png` |
| 2 | Data Quality entry and former Workspace validation area | UX | Search and raw validation rows appeared before useful business context. | Added a summary-first Data Quality report: total/blocking/warning counts, affected products/Channels/Sources, trend, resolved count, common categories, then collapsed filters and grouped issue rows. | `DataQuality.test.tsx`, four issue-report screenshots |
| 3 | Data Quality empty state, `/data-quality` | Behavioral / data | Absence of persisted scan provenance was rendered like a healthy result; loose `all` filters and latest-scan scope could hide issues. | Added durable scan state and normalized scan scope. Never checked, checking, healthy, issues found, failed, and permission-denied are distinct. Global reports select the latest global scan; a newer single-Source scan cannot replace it. Blank/locale `all` filters normalize to no filter. Failed scans persist as failures. External worksheet/row identities are stored without truncating meaningful prefixes, and severity order is deterministic. | `test_data_quality_scans.py`, never-checked/healthy/issues/failed screenshots |
| 4 | Diagnostics overview, `/diagnostics` | UX / translation | Raw per-connector dimensions dominated the page and Source connectors could be duplicated as Channels. | Added a status-first summary for system, Sources, Channels, database, background jobs, rate limits, and failures. Source and Channel cards show only connection, successful activity, current action, and a collapsed technical-details disclosure. Channel health excludes Source connectors. Database status uses diagnostic evidence rather than process liveness; missing or skipped evidence cannot be presented as healthy. Disabled, pending, and unchecked Sources are described truthfully. | `Diagnostics.test.tsx`, `test_unified_channel_health.py`, summary screenshots |
| 5 | Diagnostics details and rate limits | UX / data | Engineering counters and null values appeared as unexplained zero, Unknown, or healthy no-wait states. | Added practical rate-limit labels and explicit unavailable evidence. Null limiter data never becomes a healthy zero. Technical latency/capability/heartbeat values remain in collapsed details. Every state includes icon plus text. | Diagnostics unavailable-data unit test and expanded-details screenshots |

## Data and compatibility decisions

- `FLOWHUB_019` is additive and follows `FLOWHUB_018`; historical migrations are unchanged.
- Existing FLOWHUB_018 Source mappings synthesize the former shared rule and remain readable.
- Worksheet rule aggregates and terminal scan evidence are protected at database level.
- Source files are acquired once per discovery/analysis operation; no Channel reads a workbook independently.
- Historical Snapshots, revisions, Apply jobs, and Audit events are never cascade-deleted by Source lifecycle actions.
- Review invalidation remains conservative when a Source column revision changes.

## Independent post-implementation review

An independent read-only diff review found and closed eight correctness gaps before
final validation: preview filter truth, worksheet identity, long Data Quality row
identity, evidence-backed Database health, truthful inactive Source status, stale
lifecycle-impact responses, explicit severity ordering, and seller-facing wording
for FlowHub Sheet column identity. Focused regressions cover each correction.

## Validation evidence

- Backend: `python -m pytest -q` — 2,940 passed, 19 skipped, 0 failed.
- Frontend: `npm test -- --run` — 44 files and 281 tests passed.
- Browser: `npm run test:e2e` — 15 passed in installed Google Chrome
  150.0.7871.115 from
  `C:\Program Files\Google\Chrome\Application\chrome.exe` on Windows 11
  (10.0.26200).
- Requested viewports: 1280x720, 1366x768, 1440x900, and 1920x1080.
- 10,000-product benchmark: initial API window 500 rows, 19 DOM rows,
  8,972 ms readiness, 163 ms scroll, approximately 66.2 MB JavaScript heap.
- i18n: 1,279 messages in 17 namespaces; English and Persian both 1,279/1,279;
  zero missing keys, interpolation-token mismatches, hardcoded-string violations, or
  critical Persian leakage values.
- Frontend build, scoped Ruff, Python compilation, OpenAPI serialization,
  SQLite fresh migration through FLOWHUB_019, dependency integrity, dependency
  audit, and `git diff --check` passed locally.
- PostgreSQL 16 live migration/trigger/foreign-key evidence is produced by the
  fail-on-skip `FlowHub PostgreSQL safety` workflow for the release commit.

## Screenshot index

- PDF reference: `docs/screenshots/v1.3/pdf-bug-remediation/reference/`
- Baseline application: `docs/screenshots/v1.3/pdf-bug-remediation/before/`
- Corrected Chromium audit: `docs/screenshots/v1.3/pdf-bug-remediation/after/`

The corrected set includes English LTR and Persian RTL, all four requested
viewports (1280x720, 1366x768, 1440x900, and 1920x1080), Source lifecycle,
shared/per-sheet configuration, Source Preview, every Data Quality state, and
Diagnostics summary and expanded details.
