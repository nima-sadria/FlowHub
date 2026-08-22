# FlowHub Operations Runbook

## Authoritative Ubuntu Deployment Topology

FlowHub is deployed on the Ubuntu 24.04 host at `192.168.100.80`. This host
is the deployment server itself; it is not a development machine that deploys
to another host.

The only canonical checkout on that host is
`/home/nima/Projects/FlowHub`, operated by user `nima`. Git, builds, and
updates run as `nima`: do not use `sudo git`, do not create an alternate
deployment checkout, and do not use `/opt/FlowHub`. `/opt/FlowHub` is
permanently retired.

The canonical Compose runtime on this host is:

- `flowhub-app-1`
- `flowhub-postgres-1`
- `flowhub-order-sync-runner-1`
- `flowhub-exchange-rate-runner-1`

The canonical browser and backend target is `http://192.168.100.80:8085`.
The application uses `postgres:5432/flowhub` inside Compose. Preserve the
persistent data for `flowhub-postgres-1`; `flowhub-postgres-test` on
`127.0.0.1:5433` is disposable test infrastructure and must never be chosen
for a normal deployment or runtime operation.

Nginx Proxy Manager runs separately at `192.168.100.11` and only reverse
proxies public FlowHub traffic to `192.168.100.80:8085`. It is not part of
the Ubuntu FlowHub runtime and is not changed during normal FlowHub updates.

`flowhub-preview-20260805` was a historical preview on port `5174`. It is
non-authoritative and must never be used to identify the deployed version.
Any future preview must be explicitly labelled non-authoritative.

## Normal update

Run the canonical menu as `nima` from the canonical checkout:

```bash
cd /home/nima/Projects/FlowHub
flowhub
```

The host command is `/usr/local/bin/flowhub`; its privileged helper is
`/usr/local/lib/flowhub/flowhub-helper`. Source operations still execute as
`nima`.

Update is fail-closed: it stops for a dirty tracked tree, local `main` ahead
of or diverged from `origin/main`, a non-fast-forward pull, migration failure,
build/restart failure, or a failed health check. Normal updates preserve the
existing `.env` and PostgreSQL data. Never reset the database as part of an
update.

## Runtime identity check

Before claiming that a FlowHub URL is current, verify all of the following:

1. The canonical repository HEAD.
2. `origin/main` synchronization.
3. The canonical Compose app was built from that source.
4. The persistent database is the normal FlowHub database.
5. Alembic is at the current head.
6. `GET /api/health` returns HTTP 200.

The current migration family is `alembic_flowhub`. `FLOWHUB_031` was the head
when this document was written; do not treat it as permanently latest—always
verify the current Alembic head at runtime.

Never infer deployment identity from an old container, `/opt/FlowHub`, a
stale preview, cached `origin/main`, or another checkout.
