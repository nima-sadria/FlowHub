# FlowHub v1.3 Beta

## Release registration

- **Version:** FlowHub v1.3 Beta
- **Release status:** Beta
- **Approved commit:** `fe953bdb3139f3135692cd3b3b3a221c6c371de6`
- **Official development baseline:** FlowHub v1.3 Beta

## Release status

| Area | Status |
| --- | --- |
| Architecture | Stable |
| Backend | Stable |
| Frontend | Stable |
| Workspace | Source-centric |
| Internationalization | Implemented |
| RTL | Implemented |
| Persian | Implemented |
| English | Implemented |
| FlowHub Sheet | Implemented |
| External Sources | Supported |
| Formula Engine | Implemented |
| Migration | `FLOWHUB_018` |
| Review | Stable |
| Apply | Stable |
| Recovery | Stable |
| Audit | Stable |
| Browser E2E | Passed |
| PostgreSQL CI | Passed |

## Intended use and commercial licensing

Current intended usage:

- ✔ Personal
- ✔ Internal
- ✔ Daily operation

Commercial deployment requires a valid Handsontable commercial license while
the Handsontable Workspace remains in use. This requirement does not prevent
the approved personal and internal use of this release.

## Product philosophy

FlowHub exists to save sellers time. Every feature should satisfy at least one
of these outcomes:

- Reduce time;
- Reduce mistakes;
- Reduce repetitive work.

If a feature does not improve seller productivity, it should not receive
priority over features that do.

## Architecture freeze

The FlowHub v1.3 architecture is frozen. Normal feature work must preserve:

- the Source-centric Workspace;
- Canonical Product;
- multi-channel Listings;
- immutable Snapshots;
- Draft Revisions;
- Review;
- the shared Write Pipeline;
- Recovery;
- Reconciliation;
- FlowHub Sheet;
- the translation infrastructure.

Architectural redesign requires explicit Owner approval.

## Development workflow

Normal feature development follows this sequence:

**Idea → Product Design → Implementation → Feature Audit → Merge → Next Feature**

Large architecture audits are no longer part of normal feature development.
They are required only when the Owner explicitly approves an architectural
change.

## References

- [Source-centric pricing Workspace](../architecture/SOURCE_CENTRIC_PRICING_WORKSPACE.md)
- [Internationalization](../i18n/INTERNATIONALIZATION.md)
- [Next priorities](../roadmap/NEXT.md)
- [Changelog](../../CHANGELOG.md)
- [FlowHub v1.2 Stable](FLOWHUB_V1.2_STABLE.md)
