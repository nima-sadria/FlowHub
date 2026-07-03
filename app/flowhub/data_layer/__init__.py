"""FlowHub - Data Layer package.

The Data Layer is the persistent read model between external systems
(WooCommerce, Nextcloud) and the FlowHub UI.

Sub-modules:
  models              - SQLAlchemy ORM models (dl_* tables)
  product_service     - product cache read model
  health_service      - connector health records
  telemetry_service   - connector telemetry aggregates
  snapshot_service    - source/destination snapshot metadata
  refresh_service     - refresh job status model
  invalidation_service - invalidation event log

Safety: all service methods are read-only from external systems.
        Write methods populate the dl_* tables only. No WC/NC writes.
"""
