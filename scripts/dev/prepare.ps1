[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $pythonLauncher) {
        & $pythonLauncher.Source -3.12 -m venv (Join-Path $root ".venv")
    } else {
        $python = Get-Command python -ErrorAction Stop
        & $python.Source -m venv (Join-Path $root ".venv")
    }
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $root "requirements.txt") -r (Join-Path $root "requirements-test.txt")
}

$mcpCli = Join-Path $frontend "node_modules\@playwright\mcp\cli.js"
if (-not (Test-Path -LiteralPath $mcpCli)) {
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    & $npm ci --prefix $frontend
}

& $venvPython (Join-Path $PSScriptRoot "bootstrap_local.py")

$node = (Get-Command node.exe -ErrorAction Stop).Source
$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$mcpArgs = @(
    $mcpCli,
    "--user-data-dir", (Join-Path $root ".local\browser-profile\claude"),
    "--output-dir", (Join-Path $root ".local\browser-mcp"),
    "--output-mode", "file",
    "--console-level", "debug",
    "--caps", "devtools",
    "--allowed-origins", "http://127.0.0.1:*;http://localhost:*"
)
if ($chromeCandidates.Count -gt 0) {
    $mcpArgs += @("--browser", "chrome")
}

$mcpConfig = @{
    mcpServers = @{
        playwright = @{
            command = $node
            args = $mcpArgs
        }
    }
}
$mcpConfigPath = Join-Path $root ".mcp.json"
$mcpConfig | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $mcpConfigPath -Encoding UTF8

Write-Host "FlowHub local development is prepared."
Write-Host "Claude MCP config: $mcpConfigPath"
Write-Host "Credentials: $(Join-Path $root '.local\dev\credentials.json')"
