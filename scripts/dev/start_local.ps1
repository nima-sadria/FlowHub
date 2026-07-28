[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$stateDir = Join-Path $root ".local\dev"
$logDir = Join-Path $stateDir "logs"
$processFile = Join-Path $stateDir "processes.json"

& (Join-Path $PSScriptRoot "prepare.ps1")
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

if (Test-Path -LiteralPath $processFile) {
    $recorded = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    $running = @($recorded.backendPid, $recorded.frontendPid) |
        Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }
    if ($running.Count -gt 0) {
        throw "A recorded FlowHub local stack is still running. Use scripts/dev/stop_local.ps1 first."
    }
}

$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
$backend = Start-Process -FilePath $powershell `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run_backend.ps1") `
    -WorkingDirectory $root `
    -RedirectStandardOutput (Join-Path $logDir "backend.stdout.log") `
    -RedirectStandardError (Join-Path $logDir "backend.stderr.log") `
    -WindowStyle Hidden `
    -PassThru
$frontend = Start-Process -FilePath $powershell `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run_frontend.ps1") `
    -WorkingDirectory $root `
    -RedirectStandardOutput (Join-Path $logDir "frontend.stdout.log") `
    -RedirectStandardError (Join-Path $logDir "frontend.stderr.log") `
    -WindowStyle Hidden `
    -PassThru

@{
    backendWrapperPid = $backend.Id
    frontendWrapperPid = $frontend.Id
    backendPid = $null
    frontendPid = $null
    startedAt = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding UTF8

function Wait-ForUrl {
    param([string]$Url, [int]$Attempts = 60)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Timed out waiting for $Url. Check .local/dev/logs."
}

try {
    Wait-ForUrl "http://127.0.0.1:8000/api/health"
    Wait-ForUrl "http://127.0.0.1:5173"
} catch {
    & (Join-Path $PSScriptRoot "stop_local.ps1")
    throw
}

$backendListener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction Stop |
    Where-Object { $_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::") } |
    Select-Object -First 1
$frontendListener = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction Stop |
    Where-Object { $_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::") } |
    Select-Object -First 1

@{
    backendWrapperPid = $backend.Id
    frontendWrapperPid = $frontend.Id
    backendPid = $backendListener.OwningProcess
    frontendPid = $frontendListener.OwningProcess
    startedAt = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding UTF8

if (-not $NoBrowser) {
    $chromeCandidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    if ($chromeCandidates.Count -gt 0) {
        Start-Process -FilePath $chromeCandidates[0] `
            -ArgumentList "--user-data-dir=$(Join-Path $root '.local\browser-profile\manual')", "http://127.0.0.1:5173" | Out-Null
    } else {
        Start-Process "http://127.0.0.1:5173" | Out-Null
    }
}

Write-Host "FlowHub backend: http://127.0.0.1:8000"
Write-Host "FlowHub frontend: http://127.0.0.1:5173"
Write-Host "Logs: $logDir"
