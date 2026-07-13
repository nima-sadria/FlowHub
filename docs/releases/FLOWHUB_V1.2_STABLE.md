# FlowHub v1.2 Stable

## Release registration

- **Version:** FlowHub v1.2 Stable
- **Release status:** Stable
- **Approved commit:** `4a02fbbcf25f0d82d05f7dc5f0f1dd3efa322a0c`
- **Production use status:** Personal/Internal approved

## Verification status

| Area | Status |
| --- | --- |
| Architecture | Complete |
| Implementation | Complete |
| Technical verification | Complete |
| Visual audit | Complete |
| Backend tests | Passed |
| Frontend tests | Passed |
| Browser E2E | Passed |
| PostgreSQL CI | Passed |
| 10,000-product benchmark | Passed |

## Commercial-use note

FlowHub v1.2 is approved for personal and internal use. Commercial deployment
requires a valid Handsontable commercial license before commercial use.

## Architecture freeze

The FlowHub v1.2 architecture is frozen for normal feature development:

- normal feature work must not redesign the architecture;
- future changes must preserve the approved v1.2 invariants;
- architecture changes require explicit Owner approval.

## Future development policy

Normal feature work follows this sequence:

**Feature Design → Implementation → Targeted Feature Audit → Merge → Next Feature**

Full architecture audits are not required for normal feature development unless
a future release intentionally changes the architecture.

## References

- [Current architecture](../architecture/CURRENT_ARCHITECTURE.md)
- [Unified Multi-Channel Workspace](../architecture/UNIFIED_MULTI_CHANNEL_WORKSPACE.md)
- [Release notes](../../RELEASE_NOTES.md)
- [Roadmap](../../ROADMAP.md)
