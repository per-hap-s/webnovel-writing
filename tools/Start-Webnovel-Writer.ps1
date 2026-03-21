param(
    [ValidateSet('menu', 'dashboard', 'dashboard-lan', 'login', 'shell', 'readme', 'help')]
    [string]$Action = 'dashboard',
    [string]$ProjectRoot,
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Join-Path $workspaceRoot 'webnovel-writer'
$dashboardLauncher = Join-Path $PSScriptRoot 'Launch-Webnovel-Dashboard.ps1'
$loginLauncher = Join-Path $PSScriptRoot 'Login-Codex-CLI.ps1'
$guideSourcePath = Join-Path $repoRoot 'Quick-Start-CN.txt'
$guidePath = Join-Path $env:TEMP 'webnovel-writer-quick-start-cn.txt'

function Test-LauncherExists([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path)) {
        throw "未找到$Label：$Path"
    }
}

function Start-DashboardWindow([switch]$LanMode) {
    Test-LauncherExists $dashboardLauncher 'Dashboard 启动脚本'

    $argList = @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-File', "`"$dashboardLauncher`"",
        '-Port', $Port
    )

    if ($ProjectRoot) {
        $argList += @('-ProjectRoot', "`"$ProjectRoot`"")
    }
    if ($NoBrowser) {
        $argList += '-NoBrowser'
    }
    if ($LanMode) {
        $argList += '-Lan'
    }

    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $workspaceRoot -ArgumentList $argList | Out-Null
}

function Start-LoginWindow {
    Test-LauncherExists $loginLauncher 'Codex CLI 登录脚本'
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-File', "`"$loginLauncher`""
    ) | Out-Null
}

function Start-ProjectShell {
    $targetRoot = $repoRoot
    if ($ProjectRoot -and (Test-Path $ProjectRoot)) {
        $targetRoot = (Resolve-Path $ProjectRoot).Path
    }
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $targetRoot -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command', "Set-Location -LiteralPath '$targetRoot'"
    ) | Out-Null
}

function Open-Guide {
    if (Test-Path $guideSourcePath) {
        $content = Get-Content -LiteralPath $guideSourcePath -Raw -Encoding UTF8
    } else {
        $content = @'
Webnovel Writer 快速说明
========================

双击桌面快捷方式后会直接进入 Web 工作台。
你可以在工作台里打开已有项目、新建项目、切换项目，并从工具页执行登录 Codex CLI、打开终端、查看说明或开启局域网访问。
'@
    }
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($guidePath, $content, $utf8Bom)
    Start-Process -FilePath 'notepad.exe' -ArgumentList "`"$guidePath`"" | Out-Null
}

function Pause-ForReturn([string]$Message) {
    Write-Host
    [void](Read-Host $Message)
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host 'Webnovel Writer 启动器'
        Write-Host '======================'
        Write-Host '1. 启动 Dashboard 工作台'
        Write-Host '   直接启动本机 Web 工作台'
        Write-Host '2. 启动 Dashboard（局域网）'
        Write-Host '   允许手机或局域网其他设备访问'
        Write-Host '3. 登录 Codex CLI'
        Write-Host '   打开登录窗口并检查当前状态'
        Write-Host '4. 打开终端'
        Write-Host '   有项目参数时进入项目目录，否则进入仓库目录'
        Write-Host '5. 打开快速说明'
        Write-Host '   用记事本查看当前使用说明'
        Write-Host 'Q. 退出'
        Write-Host

        $choice = (Read-Host '请选择操作 [1]').Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($choice)) {
            $choice = '1'
        }

        switch ($choice) {
            '1' { Start-DashboardWindow; Pause-ForReturn '已启动 Dashboard。按回车返回主菜单。'; continue }
            '2' { Start-DashboardWindow -LanMode; Pause-ForReturn '已启动局域网 Dashboard。按回车返回主菜单。'; continue }
            '3' { Start-LoginWindow; Pause-ForReturn '已打开 Codex CLI 登录窗口。按回车返回主菜单。'; continue }
            '4' { Start-ProjectShell; Pause-ForReturn '已打开终端窗口。按回车返回主菜单。'; continue }
            '5' { Open-Guide; Pause-ForReturn '已打开快速说明。按回车返回主菜单。'; continue }
            'q' { return }
            default {
                Write-Host
                Write-Host '无效选择，按回车后重试。'
                [void](Read-Host)
            }
        }
    }
}

function Show-Help {
    Write-Host '用法：'
    Write-Host '  tools\Start-Webnovel-Writer.bat'
    Write-Host '  tools\Start-Webnovel-Writer.bat menu'
    Write-Host '  tools\Start-Webnovel-Writer.bat dashboard'
    Write-Host '  tools\Start-Webnovel-Writer.bat dashboard-lan'
    Write-Host '  tools\Start-Webnovel-Writer.bat login'
    Write-Host '  tools\Start-Webnovel-Writer.bat shell'
    Write-Host '  tools\Start-Webnovel-Writer.bat readme'
}

switch ($Action) {
    'menu' { Show-Menu }
    'dashboard' { Start-DashboardWindow }
    'dashboard-lan' { Start-DashboardWindow -LanMode }
    'login' { Start-LoginWindow }
    'shell' { Start-ProjectShell }
    'readme' { Open-Guide }
    'help' { Show-Help }
    default { throw "不支持的动作：$Action" }
}
