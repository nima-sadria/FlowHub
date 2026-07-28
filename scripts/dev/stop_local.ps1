[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$processFile = Join-Path $root ".local\dev\processes.json"

if (-not (Test-Path -LiteralPath $processFile)) {
    Write-Host "No recorded FlowHub local stack is running."
    exit 0
}

$recorded = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json

function Stop-ProcessTree {
    param([int]$TargetProcessId)

    $children = Get-CimInstance Win32_Process |
        Where-Object { $_.ParentProcessId -eq $TargetProcessId }
    foreach ($child in $children) {
        Stop-ProcessTree -TargetProcessId $child.ProcessId
    }
    if (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $TargetProcessId -Force
    }
}

$listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8000, 5173 }
$safeListenerPids = @($listeners.OwningProcess)

@($recorded.backendPid, $recorded.frontendPid) |
    Where-Object { $_ -and $_ -in $safeListenerPids } |
    Select-Object -Unique |
    ForEach-Object { Stop-ProcessTree -TargetProcessId $_ }

@($recorded.backendWrapperPid, $recorded.frontendWrapperPid) |
    Where-Object { $_ } |
    Select-Object -Unique |
    ForEach-Object {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $_" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -like "*$root*scripts*dev*run_*") {
            Stop-ProcessTree -TargetProcessId $_
        }
    }

Remove-Item -LiteralPath $processFile
Write-Host "FlowHub local stack stopped."
