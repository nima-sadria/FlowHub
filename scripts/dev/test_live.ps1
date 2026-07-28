[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$startedHere = -not (Test-Path -LiteralPath (Join-Path $root ".local\dev\processes.json"))

try {
    if ($startedHere) {
        & (Join-Path $PSScriptRoot "start_local.ps1") -NoBrowser
    }
    & $npm run test:e2e:live --prefix (Join-Path $root "frontend")
    if ($LASTEXITCODE -ne 0) {
        throw "Live Playwright smoke test failed."
    }
} finally {
    if ($startedHere) {
        & (Join-Path $PSScriptRoot "stop_local.ps1")
    }
}
