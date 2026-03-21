param(
    [string]$ProjectRoot,
    [string]$ListenHost = '127.0.0.1',
    [int]$Port = 8765,
    [switch]$Lan,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Join-Path $workspaceRoot 'webnovel-writer'
$appRoot = Join-Path $repoRoot 'webnovel-writer'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$codexBin = Join-Path $env:APPDATA 'npm'
$nodeDir = Join-Path $env:LOCALAPPDATA 'Programs\NodePortable'
$env:Path = $codexBin + ';' + $nodeDir + ';' + $env:Path
if (-not $env:WEBNOVEL_CODEX_BIN) {
    $env:WEBNOVEL_CODEX_BIN = 'codex.cmd'
}
$env:PYTHONPATH = $appRoot + ';' + (Join-Path $appRoot 'scripts')
$env:WEBNOVEL_WORKSPACE_ROOT = $workspaceRoot

if ($Lan -and -not $PSBoundParameters.ContainsKey('ListenHost')) {
    $ListenHost = '0.0.0.0'
}

function Get-LocalIPv4 {
    $routes = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric, ifMetric
    foreach ($route in $routes) {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Select-Object -First 1
        if ($ip) {
            return $ip.IPAddress
        }
    }
    return $null
}

Write-Host 'Webnovel Dashboard Launcher'
Write-Host

if (-not (Test-Path $pythonExe)) {
    throw "Python virtualenv not found: $pythonExe"
}

$resolvedProjectRoot = $null
if ($ProjectRoot) {
    if (-not (Test-Path $ProjectRoot)) {
        Write-Warning "Project root does not exist. Starting workbench mode instead: $ProjectRoot"
    } else {
        $resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
        $stateFile = Join-Path $resolvedProjectRoot '.webnovel\state.json'
        if (-not (Test-Path $stateFile)) {
            Write-Warning "Project root is not initialized. Starting workbench mode instead: $resolvedProjectRoot"
            $resolvedProjectRoot = $null
        }
    }
}

Write-Host ('Workspace root: ' + $workspaceRoot)
if ($resolvedProjectRoot) {
    Write-Host ('Project root: ' + $resolvedProjectRoot)
    $env:WEBNOVEL_PROJECT_ROOT = $resolvedProjectRoot
} else {
    Write-Host 'Mode: workbench shell'
    Remove-Item Env:WEBNOVEL_PROJECT_ROOT -ErrorAction SilentlyContinue
}
Write-Host 'Starting dashboard...'
Write-Host 'Keep this window open while the dashboard is running.'
Write-Host ('Local URL: http://127.0.0.1:' + $Port)
if ($ListenHost -eq '0.0.0.0') {
    $lanIp = Get-LocalIPv4
    if ($lanIp) {
        Write-Host ('LAN URL: http://' + $lanIp + ':' + $Port)
    } else {
        Write-Host ('LAN URL: use your local IPv4 address on port ' + $Port)
    }
}
Write-Host

Set-Location $appRoot
$args = @('-m', 'dashboard.server', '--workspace-root', $workspaceRoot, '--host', $ListenHost, '--port', "$Port")
if ($resolvedProjectRoot) {
    $args += @('--project-root', $resolvedProjectRoot)
}
if ($NoBrowser) {
    $args += '--no-browser'
}

& $pythonExe @args
$exitCode = $LASTEXITCODE
Write-Host
Write-Host ('Dashboard stopped with exit code: ' + $exitCode)
exit $exitCode
