# Troubleshooting

## Check Services

```bash
flowhub status
flowhub health
flowhub logs app
```

## Repair

```bash
sudo /opt/FlowHub/installer/install.sh --repair
```

Repair re-checks prerequisites, runs migrations, checks service status, and runs
health verification.

## Database Needs Update

Use repair:

```bash
flowhub repair
```

## Legacy Compatibility Path

If `/opt/flowhub` exists, run the installer from the current repository. It will
offer migration to `/opt/FlowHub`.
