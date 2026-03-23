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
$modulePath = Join-Path $PSScriptRoot 'Webnovel-DashboardLauncher.psm1'
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

Import-Module $modulePath -Force

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

$baseUrl = Get-WebnovelDashboardBaseUrl -Host $ListenHost -Port $Port
$browserUrl = Get-WebnovelDashboardBrowserUrl -Host $ListenHost -Port $Port
$healthProbeSpec = Get-WebnovelDashboardHealthProbeSpec -BaseUrl $baseUrl -ProjectRoot $resolvedProjectRoot
$launchDecision = Resolve-WebnovelDashboardPortAction -Port $Port -BaseUrl $baseUrl -WorkspaceRoot $workspaceRoot -ProjectRoot $resolvedProjectRoot

Write-Host ('Local URL: ' + $browserUrl)
if ($ListenHost -eq '0.0.0.0') {
    $lanIp = Get-LocalIPv4
    if ($lanIp) {
        Write-Host ('LAN URL: http://' + $lanIp + ':' + $Port)
    } else {
        Write-Host ('LAN URL: use your local IPv4 address on port ' + $Port)
    }
}
Write-Host
Write-Host ('Launch mode: ' + $launchDecision.ModeLabel)
Write-Host ('Probe target: ' + $launchDecision.ProbeDescription)
Write-Host ('Decision: ' + $launchDecision.DiagnosticSummary)
if ($launchDecision.DiagnosticDetail) {
    Write-Host ('Decision detail: ' + $launchDecision.DiagnosticDetail)
}
Write-Host

switch ($launchDecision.Action) {
    'reuse_existing' {
        Write-Host 'An existing dashboard instance is healthy. Reusing it.'
        if (-not $NoBrowser) {
            Start-Process -FilePath $browserUrl | Out-Null
        }
        exit 0
    }
    'abort_port_in_use' {
        throw ('Port {0} is already occupied by another process. Dashboard will not overwrite it. {1}' -f $Port, $launchDecision.DiagnosticDetail)
    }
    'restart_existing' {
        Write-Host ('Found a stale dashboard listener ({0}). Restarting it.' -f $launchDecision.ListenerProcessId)
        $stopResult = Stop-WebnovelDashboardProcess -ProcessId $launchDecision.ListenerProcessId
        if (-not $stopResult.Succeeded) {
            if ($stopResult.EnvironmentIssue) {
                throw ('Environment issue while stopping stale dashboard listener: {0}' -f $stopResult.Message)
            }
            throw ('Failed to stop stale dashboard listener: {0}' -f $stopResult.Message)
        }
        Write-Host ('Stop result: ' + $stopResult.Message)
    }
}

Write-Host 'Starting dashboard...'
Write-Host 'Keep this window open while the dashboard is running.'
Write-Host ('Health probe: ' + $healthProbeSpec.Path)
Write-Host

Set-Location $appRoot
$serverProcess = Start-WebnovelDashboardServer -PythonExe $pythonExe -AppRoot $appRoot -WorkspaceRoot $workspaceRoot -ProjectRoot $resolvedProjectRoot -ListenHost $ListenHost -Port $Port

try {
    $probe = Wait-WebnovelDashboardHealthy -BaseUrl $baseUrl -ProjectRoot $resolvedProjectRoot -ProcessId $serverProcess.Id -TimeoutSeconds 45
    Write-Host ('Dashboard health check passed: ' + $probe.Reason)
} catch {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw
}

if (-not $NoBrowser) {
    Start-Process -FilePath $browserUrl | Out-Null
}

Write-Host
Write-Host ('Dashboard started with process id: ' + $serverProcess.Id)
Wait-Process -Id $serverProcess.Id
$serverProcess.Refresh()
$exitCode = $serverProcess.ExitCode
Write-Host
Write-Host ('Dashboard stopped with exit code: ' + $exitCode)
exit $exitCode
