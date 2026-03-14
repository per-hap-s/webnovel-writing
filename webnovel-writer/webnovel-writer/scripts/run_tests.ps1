param(
    [ValidateSet("smoke", "full")]
    [string]$Mode = "smoke",
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

$appRoot = $ProjectRoot
if (Test-Path (Join-Path $ProjectRoot "webnovel-writer")) {
    $appRoot = (Resolve-Path (Join-Path $ProjectRoot "webnovel-writer")).Path
}

Set-Location $appRoot

$tmpRoot = Join-Path $ProjectRoot ".tmp\\pytest"
New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null

$env:TMP = $tmpRoot
$env:TEMP = $tmpRoot
$env:PYTHONPATH = $appRoot + ";" + (Join-Path $appRoot "scripts")

$pythonExe = "python"
$venvCandidates = @(
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $ProjectRoot -Parent) ".venv\Scripts\python.exe")
)
foreach ($candidate in $venvCandidates) {
    if ($candidate -and (Test-Path $candidate)) {
        $pythonExe = (Resolve-Path $candidate).Path
        break
    }
}

# 閬垮厤 Windows 涓?basetemp 鐩綍鍥犳潈闄?娈嬬暀閿佸鑷?rm_rf 澶辫触锛堜細璁╂墍鏈夌敤渚嬪湪 setup 闃舵鐩存帴鎶ラ敊锛夈€?
$runId = Get-Date -Format "yyyyMMdd_HHmmssfff"
$baseTemp = Join-Path $tmpRoot ("run-" + $Mode + "-" + $runId)

Write-Host "ProjectRoot: $ProjectRoot"
Write-Host "AppRoot: $appRoot"
Write-Host "TMP/TEMP: $tmpRoot"
Write-Host "Mode: $Mode"

# 棰勬锛氭煇浜?Windows Python 鍙戣鐗堬紙灏ゅ叾 WindowsApps shim锛夊湪 tempfile.mkdtemp 鏃朵細鍒涘缓鈥滀笉鍙闂洰褰曗€濓紝
# 浼氬鑷?pytest 鍦ㄥ垱寤?娓呯悊涓存椂鐩綍闃舵鐩存帴 WinError 5銆?
@"
import tempfile
from pathlib import Path
import sys

try:
    d = Path(tempfile.mkdtemp(prefix="webnovel_writer_pytest_"))
    # 鏃㈣鑳藉垪鐩綍锛屼篃瑕佽兘鍐欐枃浠讹紱鍚﹀垯 pytest 蹇呮寕銆?
    list(d.iterdir())
    (d / "probe.txt").write_text("ok", encoding="utf-8")
except Exception as exc:
    print(f"PYTEST_TMPDIR_PRECHECK_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise
"@ | & $pythonExe - 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "鉂?Python 涓存椂鐩綍棰勬澶辫触锛堝父瑙佸師鍥狅細WindowsApps 鐨?python.exe shim / 鏉冮檺寮傚父锛?
    Write-Host "寤鸿锛氭敼鐢ㄦ爣鍑?Python锛坧ython.org 瀹夎鐗堬級鎴栫敤 uv/uvx 鎻愪緵鐨?Python 杩愯娴嬭瘯銆?
    exit 1
}

if ($Mode -eq "smoke") {
    & $pythonExe -m pytest -q `
        scripts/data_modules/tests/test_extract_chapter_context.py `
        scripts/data_modules/tests/test_rag_adapter.py `
        --basetemp $baseTemp `
        --no-cov `
        -p no:cacheprovider
    exit $LASTEXITCODE
}

& $pythonExe -m pytest -q `
    scripts/data_modules/tests `
    dashboard/tests `
    --basetemp $baseTemp `
    -p no:cacheprovider
exit $LASTEXITCODE
