$ErrorActionPreference = 'Stop'

$workspaceRoot = 'D:\CodexProjects\Project1'
$artifactDir = Join-Path $workspaceRoot 'output\verification\supervisor-targeted-audit-20260323'
$fixtureScript = Join-Path $workspaceRoot 'webnovel-writer\webnovel-writer\scripts\supervisor_smoke_fixture.py'
$launcherScript = Join-Path $workspaceRoot 'tools\Start-Webnovel-Writer.ps1'
$preferredPort = 8765
$baseUrl = $null
$dashboardPort = $null
$playwrightDir = Join-Path $workspaceRoot '.playwright-cli'
$transcriptPath = Join-Path $artifactDir 'playwright-transcript.txt'
$fixtureResultPath = Join-Path $artifactDir 'fixture-result.json'
$precheckPath = Join-Path $artifactDir 'precheck.json'
$snapshotIndexPath = Join-Path $artifactDir 'snapshot-index.txt'
$screenshotIndexPath = Join-Path $artifactDir 'screenshot-index.txt'
$resultPath = Join-Path $artifactDir 'result.json'

New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
New-Item -ItemType Directory -Path $playwrightDir -Force | Out-Null
Set-Content -Path $transcriptPath -Value '' -Encoding UTF8
Set-Content -Path $snapshotIndexPath -Value '' -Encoding UTF8
Set-Content -Path $screenshotIndexPath -Value '' -Encoding UTF8

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw 'npx not found. Install Node.js/npm before running Playwright verification.'
}

if (-not $env:CODEX_HOME) {
    $env:CODEX_HOME = Join-Path $HOME '.codex'
}
$PWCLI = Join-Path $env:CODEX_HOME 'skills\playwright\scripts\playwright_cli.ps1'
$env:PLAYWRIGHT_CLI_SESSION = 'edge-supervisor-targeted-audit'

function Invoke-JsonGet {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    return Invoke-RestMethod -Uri $Url -Headers @{ Accept = 'application/json' } -TimeoutSec 5
}

function Get-FreeDashboardPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$PreferredPort
    )

    $candidatePorts = @($PreferredPort)
    $candidatePorts += 8876..8895

    foreach ($candidatePort in $candidatePorts) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $candidatePort -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $listener) {
            return $candidatePort
        }
    }

    throw '无法为 targeted audit 分配空闲端口。'
}

function Stop-DashboardListenerForPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        return
    }

    try {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    } catch {
        Add-Content -Path $transcriptPath -Value ("cleanup warning: failed to stop listener on port {0}: {1}" -f $Port, $_.Exception.Message)
    }
}

function Get-JsonItemCount {
    param(
        [Parameter(Mandatory = $false)]
        $Payload
    )

    if ($null -eq $Payload) {
        return 0
    }

    $propertyNames = @()
    if ($Payload.PSObject -and $Payload.PSObject.Properties) {
        $propertyNames = @($Payload.PSObject.Properties.Name)
    }

    if (($propertyNames -contains 'value') -and ($propertyNames -contains 'Count')) {
        return [int]$Payload.Count
    }

    return @($Payload).Count
}

function Test-PrecheckThresholds {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $encodedRoot = [uri]::EscapeDataString($ProjectRoot)
    $urls = [ordered]@{
        recommendations = "$baseUrl/api/supervisor/recommendations?include_dismissed=true&project_root=$encodedRoot"
        checklists = "$baseUrl/api/supervisor/checklists?project_root=$encodedRoot"
        audit_log = "$baseUrl/api/supervisor/audit-log?project_root=$encodedRoot"
        audit_health = "$baseUrl/api/supervisor/audit-health?project_root=$encodedRoot"
        audit_repair_preview = "$baseUrl/api/supervisor/audit-repair-preview?project_root=$encodedRoot"
        audit_repair_reports = "$baseUrl/api/supervisor/audit-repair-reports?project_root=$encodedRoot"
    }

    $payload = [ordered]@{
        project_root = $ProjectRoot
        checks = [ordered]@{}
        all_passed = $false
    }

    try {
        $recommendations = Invoke-JsonGet -Url $urls.recommendations
        $recommendationsCount = Get-JsonItemCount -Payload $recommendations
        $payload.checks.recommendations = [ordered]@{
            url = $urls.recommendations
            count = $recommendationsCount
            passed = ($recommendationsCount -ge 2)
        }

        $checklists = Invoke-JsonGet -Url $urls.checklists
        $checklistsCount = Get-JsonItemCount -Payload $checklists
        $payload.checks.checklists = [ordered]@{
            url = $urls.checklists
            count = $checklistsCount
            passed = ($checklistsCount -ge 1)
        }

        $auditLog = Invoke-JsonGet -Url $urls.audit_log
        $auditLogCount = Get-JsonItemCount -Payload $auditLog
        $payload.checks.audit_log = [ordered]@{
            url = $urls.audit_log
            count = $auditLogCount
            passed = ($auditLogCount -ge 1)
        }

        $auditHealth = Invoke-JsonGet -Url $urls.audit_health
        $payload.checks.audit_health = [ordered]@{
            url = $urls.audit_health
            exists = [bool]$auditHealth.exists
            issue_count = [int]($auditHealth.issue_count | ForEach-Object { $_ })
            passed = ([bool]$auditHealth.exists -and [int]$auditHealth.issue_count -ge 1)
        }

        $repairPreview = Invoke-JsonGet -Url $urls.audit_repair_preview
        $payload.checks.audit_repair_preview = [ordered]@{
            url = $urls.audit_repair_preview
            exists = [bool]$repairPreview.exists
            manual_review_count = [int]($repairPreview.manual_review_count | ForEach-Object { $_ })
            passed = ([bool]$repairPreview.exists -and [int]$repairPreview.manual_review_count -ge 1)
        }

        $repairReports = Invoke-JsonGet -Url $urls.audit_repair_reports
        $repairReportsCount = Get-JsonItemCount -Payload $repairReports
        $payload.checks.audit_repair_reports = [ordered]@{
            url = $urls.audit_repair_reports
            count = $repairReportsCount
            passed = ($repairReportsCount -ge 1)
        }
    } catch {
        $payload.error = $_.Exception.Message
    }

    $payload.all_passed = -not $payload.error -and @($payload.checks.Values | ForEach-Object { [bool]$_.passed } | Where-Object { -not $_ }).Count -eq 0
    return $payload
}

function Get-NewPlaywrightFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Filter,
        [Parameter(Mandatory = $true)]
        [datetime]$SinceUtc
    )

    $items = @(Get-ChildItem -Path $playwrightDir -Filter $Filter -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc -ge $SinceUtc } | Sort-Object LastWriteTimeUtc)
    if (-not $items.Count) {
        return $null
    }
    return $items[-1].FullName
}

function Invoke-PlaywrightCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [switch]$Open
    )

    $stepStartUtc = (Get-Date).ToUniversalTime()
    Add-Content -Path $transcriptPath -Value ("## " + $Name)
    Add-Content -Path $transcriptPath -Value ("URL: " + $Url)
    if ($Open) {
        & $PWCLI open $Url --browser msedge --headed | Tee-Object -FilePath $transcriptPath -Append | Out-Null
    } else {
        & $PWCLI goto $Url | Tee-Object -FilePath $transcriptPath -Append | Out-Null
    }
    Start-Sleep -Milliseconds 1200
    & $PWCLI snapshot | Tee-Object -FilePath $transcriptPath -Append | Out-Null
    $snapshotPath = Get-NewPlaywrightFile -Filter 'page-*.yml' -SinceUtc $stepStartUtc
    & $PWCLI screenshot | Tee-Object -FilePath $transcriptPath -Append | Out-Null
    $screenshotPath = Get-NewPlaywrightFile -Filter 'page-*.png' -SinceUtc $stepStartUtc
    Add-Content -Path $transcriptPath -Value ''

    return [ordered]@{
        name = $Name
        url = $Url
        snapshot = $snapshotPath
        screenshot = $screenshotPath
    }
}

function Test-PageSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$SnapshotPath
    )

    $text = Get-Content -Path $SnapshotPath -Raw -Encoding UTF8
    $issues = New-Object System.Collections.Generic.List[string]

    if ($Name -eq 'supervisor') {
        foreach ($required in @('第 3 章待回写审批', '第 4 章被审查关卡拦截', '督办 Smoke 清单')) {
            if ($text -notmatch [regex]::Escape($required)) {
                $issues.Add("missing:$required")
            }
        }
        foreach ($forbidden in @('督办台数据刷新失败', '当前没有需要优先处理的建议。', '暂时还没有已保存的清单。', 'approval-gate', 'hard blocking issue')) {
            if ($text -match [regex]::Escape($forbidden)) {
                $issues.Add("forbidden:$forbidden")
            }
        }
    } elseif ($Name -eq 'supervisor-audit') {
        foreach ($required in @('督办 Smoke 清单', '需人工复核', '修复归档', '清单归档')) {
            if ($text -notmatch [regex]::Escape($required)) {
                $issues.Add("missing:$required")
            }
        }
        foreach ($forbidden in @('督办审计数据刷新失败', '当前项目还没有审计日志文件（audit-log.jsonl）。', '未发现损坏记录、关键字段缺失或未来数据结构（schema）兼容问题。', '当前没有可预演的修复动作。', '当前筛选条件下暂无审计事件。', '当前筛选下没有修复报告。', '暂时还没有可用的审计清单。', 'manual-only', 'Detected audit schema', 'through v2')) {
            if ($text -match [regex]::Escape($forbidden)) {
                $issues.Add("forbidden:$forbidden")
            }
        }
    }

    return [ordered]@{
        page = $Name
        snapshot = $SnapshotPath
        passed = ($issues.Count -eq 0)
        issues = @($issues)
    }
}

$fixtureJson = & python $fixtureScript
$fixtureResult = $fixtureJson | ConvertFrom-Json
$fixtureResult | ConvertTo-Json -Depth 6 | Set-Content -Path $fixtureResultPath -Encoding UTF8
$projectRoot = [string]$fixtureResult.project_root
$encodedRoot = [uri]::EscapeDataString($projectRoot)
$dashboardPort = Get-FreeDashboardPort -PreferredPort $preferredPort
$baseUrl = "http://127.0.0.1:$dashboardPort"
Add-Content -Path $transcriptPath -Value ("dashboard port: {0}" -f $dashboardPort)

$precheck = $null
$pageResults = @()
$classification = 'fixture_failure'
$notes = @()

try {
    & $launcherScript -Action dashboard -ProjectRoot $projectRoot -Port $dashboardPort -NoBrowser
    Start-Sleep -Seconds 2

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $precheck = Test-PrecheckThresholds -ProjectRoot $projectRoot
            if ($precheck.all_passed) {
                break
            }
        } catch {}
        Start-Sleep -Seconds 1
    }

    $precheck | ConvertTo-Json -Depth 6 | Set-Content -Path $precheckPath -Encoding UTF8

    if ($precheck.all_passed) {
        try {
            & $PWCLI close | Out-Null
        } catch {}

        $pages = @(
            @{ Name = 'supervisor'; Url = "$baseUrl/?project_root=$encodedRoot&page=supervisor"; Open = $true },
            @{ Name = 'supervisor-audit'; Url = "$baseUrl/?project_root=$encodedRoot&page=supervisor-audit"; Open = $false }
        )

        foreach ($page in $pages) {
            $capture = Invoke-PlaywrightCapture -Name $page.Name -Url $page.Url -Open:([bool]$page.Open)
            $pageCheck = Test-PageSnapshot -Name $page.Name -SnapshotPath $capture.snapshot
            $pageResults += [ordered]@{
                page = $page.Name
                url = $page.Url
                snapshot = $capture.snapshot
                screenshot = $capture.screenshot
                passed = $pageCheck.passed
                issues = $pageCheck.issues
            }
        }

        try {
            & $PWCLI close | Out-Null
        } catch {}

        $snapshotFiles = @($pageResults | ForEach-Object { $_.snapshot } | Where-Object { $_ })
        $screenshotFiles = @($pageResults | ForEach-Object { $_.screenshot } | Where-Object { $_ })
        Set-Content -Path $snapshotIndexPath -Value ($snapshotFiles -join [Environment]::NewLine) -Encoding UTF8
        Set-Content -Path $screenshotIndexPath -Value ($screenshotFiles -join [Environment]::NewLine) -Encoding UTF8

        if (($pageResults | Where-Object { -not $_.passed }).Count -gt 0) {
            $classification = 'ui_defect_reproduced'
            $notes += '预检全部命中，但真实页面仍出现空态、英文内部词或页级异常。'
        } else {
            $classification = 'pass'
            $notes += '预检全部命中，且两个页面都通过固定验收点。'
        }
    } else {
        $notes += '预检未达到夹具阈值，按夹具失败归类，不进入 UI 判断。'
    }
} finally {
    if ($dashboardPort) {
        Stop-DashboardListenerForPort -Port $dashboardPort
    }
}

$result = [ordered]@{
    classification = $classification
    project_root = $projectRoot
    dashboard_port = $dashboardPort
    base_url = $baseUrl
    fixture_result = $fixtureResult
    precheck = $precheck
    page_results = $pageResults
    transcript = $transcriptPath
    snapshot_index = $snapshotIndexPath
    screenshot_index = $screenshotIndexPath
    notes = $notes
}

$result | ConvertTo-Json -Depth 8 | Set-Content -Path $resultPath -Encoding UTF8
$result | ConvertTo-Json -Depth 8
