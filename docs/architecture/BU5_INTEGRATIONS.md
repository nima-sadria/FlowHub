# Legacy Compatibility: BU5 Integration Notes

This file is retained so historical links do not break.

The current first-release connector architecture is documented in:

- `docs/architecture/CURRENT_ARCHITECTURE.md`
- `docs/architecture/INTEGRATION_PLATFORM.md`
- `docs/architecture/DATA_LAYER_ARCHITECTURE.md`

Current behavior:

- Connector configuration belongs in Settings -> Integrations.
- Setup does not configure connectors.
- Integration Platform is the permanent connector boundary.
- Data Layer is canonical for read models and snapshots.
- Write execution remains disabled.
