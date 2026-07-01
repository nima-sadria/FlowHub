"""FlowHub â€” Data Layer package.

The Data Layer is the persistent read model between external systems
(WooCommerce, Nextcloud) and the FlowHub UI.

Sub-modules:
  models              â€” SQLAlchemy ORM models (dl_* tables)
  product_service     â€” product cache read model
  health_service      â€” connector health records
  telemetry_service   â€” connector telemetry aggregates
  snapshot_service    â€” source/destination snapshot metadata
  refresh_service     â€” refresh job status model
  invalidation_service â€” invalidation event log

Safety: all service methods are read-only from external systems.
        Write methods populate the dl_* tables only. No WC/NC writes.
"""
