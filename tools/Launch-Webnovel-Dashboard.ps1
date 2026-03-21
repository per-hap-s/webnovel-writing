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

Write-Host 'Webnovel Dashboard 启动器'
Write-Host

if (-not (Test-Path $pythonExe)) {
    throw "未找到 Python 虚拟环境：$pythonExe"
}

$resolvedProjectRoot = $null
if ($ProjectRoot) {
    if (-not (Test-Path $ProjectRoot)) {
        Write-Warning "指定的项目目录不存在，将改为仅启动工作台：$ProjectRoot"
    } else {
        $resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
        $stateFile = Join-Path $resolvedProjectRoot '.webnovel\state.json'
        if (-not (Test-Path $stateFile)) {
            Write-Warning "指定目录尚未初始化为小说项目，将改为仅启动工作台：$resolvedProjectRoot"
            $resolvedProjectRoot = $null
        }
    }
}

Write-Host ('工作区目录：' + $workspaceRoot)
if ($resolvedProjectRoot) {
    Write-Host ('当前项目：' + $resolvedProjectRoot)
    $env:WEBNOVEL_PROJECT_ROOT = $resolvedProjectRoot
} else {
    Write-Host '当前模式：全局工作台（先进入 Web，再选/建项目）'
    Remove-Item Env:WEBNOVEL_PROJECT_ROOT -ErrorAction SilentlyContinue
}
Write-Host '正在启动 Dashboard...'
Write-Host '使用 Dashboard 期间请保持此窗口开启。'
Write-Host ('本机访问地址：http://127.0.0.1:' + $Port)
if ($ListenHost -eq '0.0.0.0') {
    $lanIp = Get-LocalIPv4
    if ($lanIp) {
        Write-Host ('局域网访问地址：http://' + $lanIp + ':' + $Port)
    } else {
        Write-Host ('局域网访问地址：请使用本机局域网 IP，端口 ' + $Port)
    }
    Write-Host '手机和电脑需要处于同一局域网，且 Windows 防火墙需要放行该端口。'
}
Write-Host

Set-Location $appRoot
$args = @('-m', 'dashboard.server', '--workspace-root', $workspaceRoot, '--host', $ListenHost, '--port', $Port)
if ($resolvedProjectRoot) {
    $args += @('--project-root', $resolvedProjectRoot)
}
if ($NoBrowser) {
    $args += '--no-browser'
}

& $pythonExe @args
$exitCode = $LASTEXITCODE
Write-Host
Write-Host ('Dashboard 已停止，退出码：' + $exitCode)
exit $exitCode
