# Migration Status

## Current release head

FlowHub 1.0.0 migration head is **`FLOWHUB_014`**.

`FLOWHUB_014` follows `FLOWHUB_013` and creates normalized channel order,
order item, shipment, invoice, provider event, proposed inventory effect,
sync checkpoint, and order sync audit tables.
`FLOWHUB_013` created durable webhook ingestion tables for immutable receipts,
processing attempts, and dead letters.
`FLOWHUB_012` created the protected multi-channel product price operation
tables used by the Products Dry Run, Approval, Apply, and audit workflow. The
release compatibility suite covers both a fresh database upgrade and the
supported legacy installation upgrade path through the current head.

Use the installer upgrade flow or run:

```bash
alembic -c alembic_flowhub.ini upgrade head
```

Before an upgrade, create a verified `flowhub backup`. For a failed upgrade, use
the explicit procedure in [release/ROLLBACK.md](release/ROLLBACK.md). Do not
manually edit `alembic_version` or attempt an untested automatic downgrade.
