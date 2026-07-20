# Changelog

## FlowHub v1.3 Beta

- Added the Source-centric Workspace with grouped Source Products and independent
  multi-channel Listings.
- Added immutable Source Mapping and per-Channel Mapping revisions.
- Added the internal FlowHub Sheet and deterministic Formula Engine.
- Added the XLSX/CSV Import Wizard with checksummed import metadata.
- Added a dedicated Data Quality workflow for blocked Source and Listing issues.
- Added centralized internationalization, English and Persian catalogs, and RTL
  layout support.
- Added forward-only PostgreSQL migration `FLOWHUB_019` while preserving v1.2
  history and the shared Write Pipeline.
- Completed the current seller UI release across Application Shell, Dashboard,
  Products, Orders, Sources, Channels, Activity, Data Quality, Diagnostics,
  Settings, User Management, Rate Limits, Setup Wizard, and Login.
- Strengthened durable Recovery and uncertain-only Reconciliation coverage.
- Passed browser E2E, PostgreSQL CI, and virtualized 10,000-product coverage.

## First Public Release

- Added production-ready README and release documentation.
- Standardized installer path to `/opt/FlowHub`.
- Added Legacy Compatibility migration from `/opt/flowhub`.
- Added Integration Platform and Unified Logging Platform implementation.
- Updated Setup Wizard to Workspace, Database, Owner, and Review while retaining
  the real database verification and owner-account flows.
- Kept connector configuration in Settings.
- Preserved read-only safety for all external systems.
