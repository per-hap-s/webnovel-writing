param(
    [string]$PythonExe
)

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path $PSScriptRoot -Parent
$root = Join-Path $workspaceRoot 'webnovel-writer'
$spec = Join-Path $root 'webnovel.spec'

if (-not $PythonExe) {
    $PythonExe = Join-Path $root '.venv\Scripts\python.exe'
}

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

& $PythonExe -m PyInstaller --clean --noconfirm $spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

Write-Host
Write-Host '构建完成，按回车关闭窗口。'
[void](Read-Host)
