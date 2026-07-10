# Migration Status

## Current release head

FlowHub 1.0.0 migration head is **`FLOWHUB_011`**.

`FLOWHUB_011` follows `FLOWHUB_010` and creates the database-backed login
rate-limit state. The release compatibility suite covers both a fresh database
upgrade and the supported legacy installation upgrade path through the current
head.

Use the installer upgrade flow or run:

```bash
alembic -c alembic_flowhub.ini upgrade head
```

Before an upgrade, create a verified `flowhub backup`. For a failed upgrade, use
the explicit procedure in [release/ROLLBACK.md](release/ROLLBACK.md). Do not
manually edit `alembic_version` or attempt an untested automatic downgrade.
