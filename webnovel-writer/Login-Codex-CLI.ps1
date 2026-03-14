param(
    [switch]$CheckOnly,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'

function T([string]$Codes) {
    return -join (($Codes -split ' ') | ForEach-Object { [char][Convert]::ToInt32($_, 16) })
}

$host.UI.RawUI.WindowTitle = 'Codex CLI ' + (T '767B 5F55')

$textNotFound = T '672A 627E 5230'
$textExpectedPath = (T '9884 671F 8DEF 5F84') + [char]0xFF1A
$textStartingLogin = (T '6B63 5728 542F 52A8') + ' Codex CLI ' + (T '767B 5F55') + '...'
$textCheckingStatus = (T '6B63 5728 68C0 67E5') + ' Codex CLI ' + (T '767B 5F55 72B6 6001') + '...'
$textCheckOnlyDone = 'Codex CLI ' + (T '68C0 67E5 5B8C 6210') + [char]0x3002
$textPressEnter = (T '6309 56DE 8F66 952E 5173 95ED 7A97 53E3') + [char]0x3002

$codexCmd = Join-Path $env:APPDATA 'npm\codex.cmd'
$nodeDir = Join-Path $env:LOCALAPPDATA 'Programs\NodePortable'
$env:Path = (Join-Path $env:APPDATA 'npm') + ';' + $nodeDir + ';' + $env:Path

if (-not (Test-Path $codexCmd)) {
    Write-Host ($textNotFound + ' Codex CLI' + [char]0x3002)
    Write-Host ($textExpectedPath + ' ' + $codexCmd)
    if (-not $NoPause) {
        Write-Host
        [void](Read-Host $textPressEnter)
    }
    exit 1
}

if ($CheckOnly) {
    Write-Host ('Codex CLI: ' + $codexCmd)
    Write-Host $textCheckOnlyDone
    if (-not $NoPause) {
        Write-Host
        [void](Read-Host $textPressEnter)
    }
    exit 0
}

Write-Host $textStartingLogin
Write-Host
& $codexCmd login
$loginCode = $LASTEXITCODE
Write-Host

Write-Host $textCheckingStatus
Write-Host
& $codexCmd login status
$statusCode = $LASTEXITCODE
Write-Host

if (-not $NoPause) {
    [void](Read-Host $textPressEnter)
}

if ($loginCode -ne 0) {
    exit $loginCode
}

exit $statusCode
