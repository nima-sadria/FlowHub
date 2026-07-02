# Troubleshooting

## Check Services

```bash
flowhub
flowhub status
flowhub health
flowhub logs app
flowhub restart
```

Running `flowhub` without arguments opens the interactive management menu.
Direct commands continue to work for automation and support sessions.
The installed wrapper calls FlowHub's root-owned helper through a strict
sudoers allowlist, so these commands should not require manually prefixing
`sudo` and should not print `.env.beta` permission errors.

## Repair

```bash
sudo /opt/FlowHub/installer/install.sh --repair
```

Repair re-checks prerequisites, runs migrations, checks service status, and runs
health verification.

The `flowhub` wrapper executes runtime checks through Docker where possible, so
missing host-side Python packages should not block normal operations.

## Domain Edit Fails

Use the domain helper command or the interactive menu item **Edit Domain /
Public URL**:

```bash
flowhub domain set kharidbezan.com
flowhub start
```

Do not use `flowhub configure set app.domain`; dotted config aliases are not
runtime-editable fields.

## Let's Encrypt

Check the recorded TLS mode:

```bash
flowhub tls status
```

Configure the public URL for external reverse-proxy TLS:

```bash
flowhub tls letsencrypt kharidbezan.com
flowhub start
```

The current FlowHub compose stack does not issue certificates itself. Configure
Let's Encrypt issuance and renewal in the external reverse proxy for the same
domain.

## Database Needs Update

Use repair:

```bash
flowhub repair
```

## Legacy Compatibility Path

If `/opt/flowhub` exists, run the installer from the current repository. It will
offer migration to `/opt/FlowHub`.

## Unsupported Host

FlowHub supports Ubuntu Server 24.04 LTS and Ubuntu Server 26.04 LTS on
x86_64/amd64 hosts. Ubuntu Core is rejected because it does not provide the
standard Docker/apt-based server environment required by the installer. Other
Debian/Ubuntu hosts are best-effort only and require confirmation.
