[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontend = Join-Path $root "frontend"
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source

Set-Location $frontend
& $npm run dev -- --host 127.0.0.1 --port 5173
exit $LASTEXITCODE
