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

if ($Lan -and -not $PSBoundParameters.ContainsKey('ListenHost')) {
    $ListenHost = '0.0.0.0'
}

function Select-ProjectRoot {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = '请选择小说项目所在文件夹，或要新建小说项目的目标文件夹。'
    $dlg.ShowNewFolderButton = $true
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return $dlg.SelectedPath
    }
    return $null
}

function Prompt-Text([string]$Title, [string]$Prompt, [string]$DefaultValue) {
    Add-Type -AssemblyName Microsoft.VisualBasic
    return [Microsoft.VisualBasic.Interaction]::InputBox($Prompt, $Title, $DefaultValue)
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

if (-not $ProjectRoot) {
    $ProjectRoot = Select-ProjectRoot
}

if (-not $ProjectRoot) {
    throw '未选择任何文件夹。'
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$stateFile = Join-Path $ProjectRoot '.webnovel\state.json'

if (-not (Test-Path $stateFile)) {
    $defaultTitle = Split-Path $ProjectRoot -Leaf
    if (-not $defaultTitle) {
        $defaultTitle = '我的小说'
    }

    $title = Prompt-Text '创建小说项目' '请输入小说标题：' $defaultTitle
    if ([string]::IsNullOrWhiteSpace($title)) {
        $title = $defaultTitle
    }

    $genre = Prompt-Text '创建小说项目' '请输入题材（例如：玄幻 / 都市 / 悬疑）：' '玄幻'
    if ([string]::IsNullOrWhiteSpace($genre)) {
        $genre = '玄幻'
    }

    Write-Host ('正在初始化小说项目：' + $ProjectRoot)
    Set-Location $appRoot
    & $pythonExe (Join-Path $appRoot 'scripts\init_project.py') $ProjectRoot $title $genre
    if ($LASTEXITCODE -ne 0) {
        throw ('项目初始化失败，退出码：' + $LASTEXITCODE)
    }

    if (-not (Test-Path $stateFile)) {
        throw '项目初始化后没有生成 .webnovel\state.json。'
    }
}

Write-Host ('项目目录：' + $ProjectRoot)
Write-Host '正在启动 Dashboard...'
Write-Host '使用 Dashboard 期间请保持此窗口开启。'
Write-Host ('本机访问地址：http://127.0.0.1:' + $Port)
if ($ListenHost -eq '0.0.0.0') {
    $lanIp = Get-LocalIPv4
    if ($lanIp) {
        Write-Host ('手机访问地址：http://' + $lanIp + ':' + $Port)
    } else {
        Write-Host ('手机访问地址：请使用本机局域网 IP，端口 ' + $Port)
    }
    Write-Host '手机和电脑需要处于同一局域网，且 Windows 防火墙需要放行该端口。'
}
Write-Host

Set-Location $appRoot
$args = @('-m', 'dashboard.server', '--project-root', $ProjectRoot, '--host', $ListenHost, '--port', $Port)
if ($NoBrowser) {
    $args += '--no-browser'
}

& $pythonExe @args
$exitCode = $LASTEXITCODE
Write-Host
Write-Host ('Dashboard 已停止，退出码：' + $exitCode)
exit $exitCode

