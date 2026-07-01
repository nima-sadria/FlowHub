# Troubleshooting

## Check Services

```bash
flowhub status
flowhub health
flowhub logs app
flowhub restart
```

## Repair

```bash
sudo /opt/FlowHub/installer/install.sh --repair
```

Repair re-checks prerequisites, runs migrations, checks service status, and runs
health verification.

The `flowhub` wrapper executes runtime checks through Docker where possible, so
missing host-side Python packages should not block normal operations.

## Database Needs Update

Use repair:

```bash
flowhub repair
```

## Legacy Compatibility Path

If `/opt/flowhub` exists, run the installer from the current repository. It will
offer migration to `/opt/FlowHub`.
