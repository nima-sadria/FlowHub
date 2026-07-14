# Changelog

## FlowHub v1.3 — Source-Centric Pricing Workspace

- Added immutable Source and per-Channel Mapping revisions.
- Added Source Product grouped Workspace rows with independent Listing children.
- Added automatic selection of eligible changed Review items and a separate Data
  Quality workflow for blocked rows.
- Added the internal FlowHub Sheet, deterministic formula engine, and CSV/XLSX
  import with checksummed metadata.
- Added forward-only migration `FLOWHUB_018` without changing v1.2 history or the
  shared Write Pipeline.
- Added isolated browser coverage at four desktop viewports and a 10,000-row
  virtualized data set.

## First Public Release

- Added production-ready README and release documentation.
- Standardized installer path to `/opt/FlowHub`.
- Added Legacy Compatibility migration from `/opt/flowhub`.
- Added Integration Platform and Unified Logging Platform implementation.
- Cleaned Setup Wizard to Welcome, Server Profile, Database, Admin Account, Finish.
- Kept connector configuration in Settings.
- Preserved read-only safety for all external systems.
