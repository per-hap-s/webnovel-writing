Set-StrictMode -Version Latest

function Get-WebnovelReadonlyAuditConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot,
        [string]$OutputRoot,
        [int]$PreferredPort = 8765,
        [string]$ProjectRoot
    )

    $resolvedWorkspaceRoot = [System.IO.Path]::GetFullPath($WorkspaceRoot)
    $artifactDir = if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        Join-Path $resolvedWorkspaceRoot ("output\\verification\\readonly-audit\\run-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    } else {
        [System.IO.Path]::GetFullPath($OutputRoot)
    }

    [pscustomobject]@{
        WorkspaceRoot = $resolvedWorkspaceRoot
        ArtifactDir = $artifactDir
        PreferredPort = $PreferredPort
        ProjectRoot = $ProjectRoot
        FixtureScript = Join-Path $resolvedWorkspaceRoot 'webnovel-writer\\webnovel-writer\\scripts\\supervisor_smoke_fixture.py'
        LauncherScript = Join-Path $resolvedWorkspaceRoot 'tools\\Start-Webnovel-Writer.ps1'
        PlaywrightDir = Join-Path $resolvedWorkspaceRoot '.playwright-cli'
        FixtureResultPath = Join-Path $artifactDir 'fixture-result.json'
        PrecheckPath = Join-Path $artifactDir 'precheck.json'
        TranscriptPath = Join-Path $artifactDir 'playwright-transcript.txt'
        SnapshotIndexPath = Join-Path $artifactDir 'snapshot-index.txt'
        ScreenshotIndexPath = Join-Path $artifactDir 'screenshot-index.txt'
        ResultPath = Join-Path $artifactDir 'result.json'
    }
}

function Get-WebnovelReadonlyAuditPort {
    [CmdletBinding()]
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

    throw 'No free port available for readonly audit.'
}

function Initialize-WebnovelReadonlyAuditArtifacts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    New-Item -ItemType Directory -Path $Config.ArtifactDir -Force | Out-Null
    New-Item -ItemType Directory -Path $Config.PlaywrightDir -Force | Out-Null
    Set-Content -Path $Config.TranscriptPath -Value '' -Encoding UTF8
    Set-Content -Path $Config.SnapshotIndexPath -Value '' -Encoding UTF8
    Set-Content -Path $Config.ScreenshotIndexPath -Value '' -Encoding UTF8
}

function Invoke-WebnovelReadonlyAuditJsonGet {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    Invoke-RestMethod -Uri $Url -Headers @{ Accept = 'application/json' } -TimeoutSec 5
}

function Get-WebnovelReadonlyAuditItemCount {
    [CmdletBinding()]
    param(
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

function Stop-WebnovelReadonlyAuditListener {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [string]$TranscriptPath
    )

    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        return
    }

    try {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    } catch {
        if ($TranscriptPath) {
            Add-Content -Path $TranscriptPath -Value ("cleanup warning: failed to stop listener on port {0}: {1}" -f $Port, $_.Exception.Message)
        }
    }
}

function Test-WebnovelReadonlyAuditPrecheck {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl
    )

    $encodedRoot = [uri]::EscapeDataString($ProjectRoot)
    $urls = [ordered]@{
        recommendations = "$BaseUrl/api/supervisor/recommendations?include_dismissed=true&project_root=$encodedRoot"
        checklists = "$BaseUrl/api/supervisor/checklists?project_root=$encodedRoot"
        audit_log = "$BaseUrl/api/supervisor/audit-log?project_root=$encodedRoot"
        audit_health = "$BaseUrl/api/supervisor/audit-health?project_root=$encodedRoot"
        audit_repair_preview = "$BaseUrl/api/supervisor/audit-repair-preview?project_root=$encodedRoot"
        audit_repair_reports = "$BaseUrl/api/supervisor/audit-repair-reports?project_root=$encodedRoot"
    }

    $payload = [ordered]@{
        project_root = $ProjectRoot
        checks = [ordered]@{}
        error = $null
        all_passed = $false
    }

    try {
        $recommendations = Invoke-WebnovelReadonlyAuditJsonGet -Url $urls.recommendations
        $recommendationsCount = Get-WebnovelReadonlyAuditItemCount -Payload $recommendations
        $payload.checks.recommendations = [ordered]@{
            url = $urls.recommendations
            count = $recommendationsCount
            passed = ($recommendationsCount -ge 2)
        }

        $checklists = Invoke-WebnovelReadonlyAuditJsonGet -Url $urls.checklists
        $checklistsCount = Get-WebnovelReadonlyAuditItemCount -Payload $checklists
        $payload.checks.checklists = [ordered]@{
            url = $urls.checklists
            count = $checklistsCount
            passed = ($checklistsCount -ge 1)
        }

        $auditLog = Invoke-WebnovelReadonlyAuditJsonGet -Url $urls.audit_log
        $auditLogCount = Get-WebnovelReadonlyAuditItemCount -Payload $auditLog
        $payload.checks.audit_log = [ordered]@{
            url = $urls.audit_log
            count = $auditLogCount
            passed = ($auditLogCount -ge 1)
        }

        $auditHealth = Invoke-WebnovelReadonlyAuditJsonGet -Url $urls.audit_health
        $payload.checks.audit_health = [ordered]@{
            url = $urls.audit_health
            exists = [bool]$auditHealth.exists
            issue_count = [int]($auditHealth.issue_count | ForEach-Object { $_ })
            passed = ([bool]$auditHealth.exists -and [int]$auditHealth.issue_count -ge 1)
        }

        $repairPreview = Invoke-WebnovelReadonlyAuditJsonGet -Url $urls.audit_repair_preview
        $payload.checks.audit_repair_preview = [ordered]@{
            url = $urls.audit_repair_preview
            exists = [bool]$repairPreview.exists
            manual_review_count = [int]($repairPreview.manual_review_count | ForEach-Object { $_ })
            passed = ([bool]$repairPreview.exists -and [int]$repairPreview.manual_review_count -ge 1)
        }

        $repairReports = Invoke-WebnovelReadonlyAuditJsonGet -Url $urls.audit_repair_reports
        $repairReportsCount = Get-WebnovelReadonlyAuditItemCount -Payload $repairReports
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

function Get-WebnovelReadonlyAuditPlaywrightScript {
    [CmdletBinding()]
    param()

    if (-not $env:CODEX_HOME) {
        $env:CODEX_HOME = Join-Path $HOME '.codex'
    }

    Join-Path $env:CODEX_HOME 'skills\\playwright\\scripts\\playwright_cli.ps1'
}

function Get-WebnovelReadonlyAuditNewPlaywrightFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory,
        [Parameter(Mandatory = $true)]
        [string]$Filter,
        [Parameter(Mandatory = $true)]
        [datetime]$SinceUtc
    )

    $items = @(Get-ChildItem -Path $Directory -Filter $Filter -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTimeUtc -ge $SinceUtc } |
        Sort-Object LastWriteTimeUtc)

    if (-not $items.Count) {
        return $null
    }

    return $items[-1].FullName
}

function Invoke-WebnovelReadonlyAuditCapture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string]$PlaywrightScript,
        [Parameter(Mandatory = $true)]
        [string]$PlaywrightDir,
        [Parameter(Mandatory = $true)]
        [string]$TranscriptPath,
        [switch]$Open
    )

    $stepStartUtc = (Get-Date).ToUniversalTime()
    Add-Content -Path $TranscriptPath -Value ("## " + $Name)
    Add-Content -Path $TranscriptPath -Value ("URL: " + $Url)

    if ($Open) {
        & $PlaywrightScript open $Url --browser msedge --headed | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
    } else {
        & $PlaywrightScript goto $Url | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
    }

    Start-Sleep -Milliseconds 1200
    & $PlaywrightScript snapshot | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
    $snapshotPath = Get-WebnovelReadonlyAuditNewPlaywrightFile -Directory $PlaywrightDir -Filter 'page-*.yml' -SinceUtc $stepStartUtc
    & $PlaywrightScript screenshot | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
    $screenshotPath = Get-WebnovelReadonlyAuditNewPlaywrightFile -Directory $PlaywrightDir -Filter 'page-*.png' -SinceUtc $stepStartUtc
    Add-Content -Path $TranscriptPath -Value ''

    [ordered]@{
        name = $Name
        url = $Url
        snapshot = $snapshotPath
        screenshot = $screenshotPath
    }
}

function Test-WebnovelReadonlyAuditSnapshot {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$SnapshotPath
    )

    $text = Get-Content -Path $SnapshotPath -Raw -Encoding UTF8
    $issues = New-Object System.Collections.Generic.List[string]
    $requiredPatterns = @()
    $forbiddenPatterns = @()

    if ($Name -eq 'supervisor') {
        $requiredPatterns = @(
            '\u7b2c 3 \u7ae0\u5f85\u56de\u5199\u5ba1\u6279',
            '\u7b2c 4 \u7ae0\u88ab\u5ba1\u67e5\u5173\u5361\u62e6\u622a',
            '\u7763\u529e Smoke \u6e05\u5355'
        )
        $forbiddenPatterns = @(
            '\u7763\u529e\u53f0\u6570\u636e\u5237\u65b0\u5931\u8d25',
            '\u5f53\u524d\u6ca1\u6709\u9700\u8981\u4f18\u5148\u5904\u7406\u7684\u5efa\u8bae\u3002',
            '\u6682\u65f6\u8fd8\u6ca1\u6709\u5df2\u4fdd\u5b58\u7684\u6e05\u5355\u3002',
            'approval-gate',
            'hard blocking issue'
        )
    } elseif ($Name -eq 'supervisor-audit') {
        $requiredPatterns = @(
            '\u7763\u529e Smoke \u6e05\u5355',
            '\u9700\u4eba\u5de5\u590d\u6838',
            '\u4fee\u590d\u5f52\u6863',
            '\u6e05\u5355\u5f52\u6863'
        )
        $forbiddenPatterns = @(
            '\u7763\u529e\u5ba1\u8ba1\u6570\u636e\u5237\u65b0\u5931\u8d25',
            '\u5f53\u524d\u9879\u76ee\u8fd8\u6ca1\u6709\u5ba1\u8ba1\u65e5\u5fd7\u6587\u4ef6\uff08audit-log\.jsonl\uff09\u3002',
            '\u672a\u53d1\u73b0\u635f\u574f\u8bb0\u5f55\u3001\u5173\u952e\u5b57\u6bb5\u7f3a\u5931\u6216\u672a\u6765\u6570\u636e\u7ed3\u6784\uff08schema\uff09\u517c\u5bb9\u95ee\u9898\u3002',
            '\u5f53\u524d\u6ca1\u6709\u53ef\u9884\u6f14\u7684\u4fee\u590d\u52a8\u4f5c\u3002',
            '\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u6682\u65e0\u5ba1\u8ba1\u4e8b\u4ef6\u3002',
            '\u5f53\u524d\u7b5b\u9009\u4e0b\u6ca1\u6709\u4fee\u590d\u62a5\u544a\u3002',
            '\u6682\u65f6\u8fd8\u6ca1\u6709\u53ef\u7528\u7684\u5ba1\u8ba1\u6e05\u5355\u3002',
            'manual-only',
            'Detected audit schema',
            'through v2'
        )
    }

    foreach ($pattern in $requiredPatterns) {
        if ($text -notmatch $pattern) {
            $issues.Add("missing:$pattern")
        }
    }

    foreach ($pattern in $forbiddenPatterns) {
        if ($text -match $pattern) {
            $issues.Add("forbidden:$pattern")
        }
    }

    [ordered]@{
        page = $Name
        snapshot = $SnapshotPath
        passed = ($issues.Count -eq 0)
        issues = @($issues)
    }
}

function Invoke-WebnovelReadonlyAudit {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [switch]$SkipBrowser
    )

    if (-not (Test-Path $Config.FixtureScript)) {
        throw "Fixture script not found: $($Config.FixtureScript)"
    }

    if (-not (Test-Path $Config.LauncherScript)) {
        throw "Launcher script not found: $($Config.LauncherScript)"
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'python not found. Install Python before running readonly audit.'
    }

    if ((-not $SkipBrowser) -and -not (Get-Command npx -ErrorAction SilentlyContinue)) {
        throw 'npx not found. Install Node.js/npm before running Playwright verification.'
    }

    Initialize-WebnovelReadonlyAuditArtifacts -Config $Config

    $playwrightScript = if ($SkipBrowser) { $null } else { Get-WebnovelReadonlyAuditPlaywrightScript }
    if ($playwrightScript -and -not (Test-Path $playwrightScript)) {
        throw "Playwright CLI script not found: $playwrightScript"
    }

    $env:PLAYWRIGHT_CLI_SESSION = 'webnovel-readonly-audit'

    $fixtureCommand = @($Config.FixtureScript)
    if ($Config.ProjectRoot) {
        $fixtureCommand += @('--project-root', $Config.ProjectRoot)
    }

    $fixtureJson = & python @fixtureCommand
    $fixtureResult = $fixtureJson | ConvertFrom-Json
    $fixtureResult | ConvertTo-Json -Depth 6 | Set-Content -Path $Config.FixtureResultPath -Encoding UTF8

    $projectRoot = [string]$fixtureResult.project_root
    $dashboardPort = Get-WebnovelReadonlyAuditPort -PreferredPort $Config.PreferredPort
    $baseUrl = "http://127.0.0.1:$dashboardPort"
    Add-Content -Path $Config.TranscriptPath -Value ("dashboard port: {0}" -f $dashboardPort)

    $precheck = $null
    $pageResults = @()
    $classification = 'fixture_failure'
    $notes = @()

    try {
        & $Config.LauncherScript -Action dashboard -ProjectRoot $projectRoot -Port $dashboardPort -NoBrowser
        Start-Sleep -Seconds 2

        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            try {
                $precheck = Test-WebnovelReadonlyAuditPrecheck -ProjectRoot $projectRoot -BaseUrl $baseUrl
                if ($precheck.all_passed) {
                    break
                }
            } catch {
            }

            Start-Sleep -Seconds 1
        }

        if (-not $precheck) {
            $precheck = [ordered]@{
                project_root = $projectRoot
                checks = [ordered]@{}
                error = 'Precheck did not return a payload.'
                all_passed = $false
            }
        }

        $precheck | ConvertTo-Json -Depth 6 | Set-Content -Path $Config.PrecheckPath -Encoding UTF8

        if ($precheck -and $precheck.all_passed) {
            if ($SkipBrowser) {
                $classification = 'verification_complete_docs_pending'
                $notes += 'Precheck passed, but browser verification was skipped.'
            } else {
                try {
                    & $playwrightScript close | Out-Null
                } catch {
                }

                $encodedRoot = [uri]::EscapeDataString($projectRoot)
                $pages = @(
                    @{ Name = 'supervisor'; Url = "$baseUrl/?project_root=$encodedRoot&page=supervisor"; Open = $true },
                    @{ Name = 'supervisor-audit'; Url = "$baseUrl/?project_root=$encodedRoot&page=supervisor-audit"; Open = $false }
                )

                foreach ($page in $pages) {
                    $capture = Invoke-WebnovelReadonlyAuditCapture `
                        -Name $page.Name `
                        -Url $page.Url `
                        -PlaywrightScript $playwrightScript `
                        -PlaywrightDir $Config.PlaywrightDir `
                        -TranscriptPath $Config.TranscriptPath `
                        -Open:([bool]$page.Open)
                    $pageCheck = Test-WebnovelReadonlyAuditSnapshot -Name $page.Name -SnapshotPath $capture.snapshot
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
                    & $playwrightScript close | Out-Null
                } catch {
                }

                $snapshotFiles = @($pageResults | ForEach-Object { $_.snapshot } | Where-Object { $_ })
                $screenshotFiles = @($pageResults | ForEach-Object { $_.screenshot } | Where-Object { $_ })
                Set-Content -Path $Config.SnapshotIndexPath -Value ($snapshotFiles -join [Environment]::NewLine) -Encoding UTF8
                Set-Content -Path $Config.ScreenshotIndexPath -Value ($screenshotFiles -join [Environment]::NewLine) -Encoding UTF8

                if (@($pageResults | Where-Object { -not $_.passed }).Count -gt 0) {
                    $classification = 'ui_defect_reproduced'
                    $notes += 'Precheck passed, but readonly pages still showed an empty state, internal English copy, or a page-level error.'
                } else {
                    $classification = 'pass'
                    $notes += 'Precheck passed and both readonly pages matched the expected checkpoints.'
                }
            }
        } else {
            $notes += 'Precheck did not reach the fixture threshold, so the run is classified as fixture failure before UI inspection.'
        }
    } finally {
        if ($dashboardPort) {
            Stop-WebnovelReadonlyAuditListener -Port $dashboardPort -TranscriptPath $Config.TranscriptPath
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
        transcript = $Config.TranscriptPath
        snapshot_index = $Config.SnapshotIndexPath
        screenshot_index = $Config.ScreenshotIndexPath
        notes = $notes
    }

    $result | ConvertTo-Json -Depth 8 | Set-Content -Path $Config.ResultPath -Encoding UTF8
    [pscustomobject]$result
}

Export-ModuleMember -Function `
    Get-WebnovelReadonlyAuditConfig, `
    Get-WebnovelReadonlyAuditPort, `
    Initialize-WebnovelReadonlyAuditArtifacts, `
    Invoke-WebnovelReadonlyAudit
