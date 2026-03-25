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
$launcherModule = Join-Path $PSScriptRoot 'Webnovel-DashboardLauncher.psm1'
$loginLauncher = Join-Path $PSScriptRoot 'Login-Codex-CLI.ps1'
$guideSourcePath = Join-Path $repoRoot 'Quick-Start-CN.txt'
$guidePath = Join-Path $env:TEMP 'webnovel-writer-quick-start-cn.txt'
Import-Module $launcherModule -Force

function Test-LauncherExists([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path)) {
        throw ('Missing {0}: {1}' -f $Label, $Path)
    }
}

function Start-DashboardWindow([switch]$LanMode) {
    Test-LauncherExists $dashboardLauncher 'dashboard launcher'

    $listenHost = if ($LanMode) { '0.0.0.0' } else { '127.0.0.1' }
    $baseUrl = Get-WebnovelDashboardBaseUrl -Host $listenHost -Port $Port
    $resolvedProjectRoot = $null
    if ($ProjectRoot -and (Test-Path $ProjectRoot)) {
        $candidateRoot = (Resolve-Path $ProjectRoot).Path
        $stateFile = Join-Path $candidateRoot '.webnovel\state.json'
        if (Test-Path $stateFile) {
            $resolvedProjectRoot = $candidateRoot
        }
    }

    $decision = Resolve-WebnovelDashboardPortAction -Port $Port -BaseUrl $baseUrl -WorkspaceRoot $workspaceRoot -ProjectRoot $resolvedProjectRoot

    if ($decision.Action -eq 'reuse_existing') {
        Write-Host $decision.DiagnosticSummary
        if ($decision.DiagnosticDetail) {
            Write-Host ('Detail: ' + $decision.DiagnosticDetail)
        }
        Write-Host 'Dashboard already running and healthy. Reusing the existing instance.'
        if (-not $NoBrowser) {
            Start-Process -FilePath $decision.BrowserUrl | Out-Null
        }
        return
    }

    if ($decision.Action -eq 'abort_port_in_use') {
        throw ('Port {0} is occupied by another process. Dashboard launch aborted. {1}' -f $Port, $decision.DiagnosticDetail)
    }

    $argList = @(
        '-NoExit',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $dashboardLauncher,
        '-Port', "$Port"
    )

    if ($ProjectRoot) {
        $argList += @('-ProjectRoot', $ProjectRoot)
    }
    if ($NoBrowser) {
        $argList += '-NoBrowser'
    }
    if ($LanMode) {
        $argList += '-Lan'
    }

    $safeArgList = ConvertTo-WebnovelStartProcessArgumentList -Arguments $argList
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $workspaceRoot -ArgumentList $safeArgList | Out-Null
}

function Start-LoginWindow {
    Test-LauncherExists $loginLauncher 'Codex CLI login launcher'
    $safeArgList = ConvertTo-WebnovelStartProcessArgumentList -Arguments @(
        '-NoExit',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $loginLauncher
    )
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList $safeArgList | Out-Null
}

function Start-ProjectShell {
    $targetRoot = $repoRoot
    if ($ProjectRoot -and (Test-Path $ProjectRoot)) {
        $targetRoot = (Resolve-Path $ProjectRoot).Path
    }
    $safeArgList = ConvertTo-WebnovelStartProcessArgumentList -Arguments @(
        '-NoExit',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', "Set-Location -LiteralPath '$targetRoot'"
    )
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $targetRoot -ArgumentList $safeArgList | Out-Null
}

function Open-Guide {
    if (Test-Path $guideSourcePath) {
        $content = Get-Content -LiteralPath $guideSourcePath -Raw -Encoding UTF8
    } else {
        $content = @'
Webnovel Writer Quick Start
==========================

Double-click the launcher to open the dashboard workbench.
From the workbench you can open an existing project, create a project,
switch projects, and use the tools page.
'@
    }
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($guidePath, $content, $utf8Bom)
    $safeArgList = ConvertTo-WebnovelStartProcessArgumentList -Arguments @($guidePath)
    Start-Process -FilePath 'notepad.exe' -ArgumentList $safeArgList | Out-Null
}

function Pause-ForReturn([string]$Message) {
    Write-Host
    [void](Read-Host $Message)
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host 'Webnovel Writer Launcher'
        Write-Host '========================'
        Write-Host '1. Start dashboard workbench'
        Write-Host '2. Start dashboard (LAN)'
        Write-Host '3. Login Codex CLI'
        Write-Host '4. Open shell'
        Write-Host '5. Open quick guide'
        Write-Host 'Q. Quit'
        Write-Host

        $choice = (Read-Host 'Choose an action [1]').Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($choice)) {
            $choice = '1'
        }

        switch ($choice) {
            '1' { Start-DashboardWindow; Pause-ForReturn 'Dashboard started. Press Enter to return.'; continue }
            '2' { Start-DashboardWindow -LanMode; Pause-ForReturn 'LAN dashboard started. Press Enter to return.'; continue }
            '3' { Start-LoginWindow; Pause-ForReturn 'Login window opened. Press Enter to return.'; continue }
            '4' { Start-ProjectShell; Pause-ForReturn 'Shell opened. Press Enter to return.'; continue }
            '5' { Open-Guide; Pause-ForReturn 'Guide opened. Press Enter to return.'; continue }
            'q' { return }
            default {
                Write-Host
                Write-Host 'Invalid choice. Press Enter to try again.'
                [void](Read-Host)
            }
        }
    }
}

function Show-Help {
    Write-Host 'Usage:'
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
    default { throw "Unsupported action: $Action" }
}
