[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envFile = Join-Path $root ".local\dev\backend.env"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Local environment is missing. Run scripts/dev/prepare.ps1 first."
}

Get-Content -LiteralPath $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $key, $value = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

Set-Location $root
& $python -m uvicorn app.flowhub.app:app --reload --reload-dir app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
