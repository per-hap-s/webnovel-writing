Set-StrictMode -Version Latest

$script:WebnovelChapterDir = ([string][char]0x6B63) + ([char]0x6587)
$script:WebnovelOutlineDir = ([string][char]0x5927) + ([char]0x7EB2)
$script:WebnovelMasterOutlineFile = (([string][char]0x603B) + ([char]0x7EB2) + '.md')

function Get-WebnovelRealE2EConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot,
        [string]$OutputRoot,
        [int]$PreferredPort = 8765,
        [string]$ProjectRoot,
        [string]$RunId,
        [string]$Title = 'Night Rain Rewind',
        [string]$Genre = 'Urban Supernatural'
    )

    $resolvedWorkspaceRoot = [System.IO.Path]::GetFullPath($WorkspaceRoot)
    $dateStamp = Get-Date -Format 'yyyyMMdd'
    $resolvedRunId = if ([string]::IsNullOrWhiteSpace($RunId)) {
        Get-Date -Format 'HHmmss'
    } else {
        $RunId.Trim()
    }
    $runKey = '{0}-{1}' -f $dateStamp, $resolvedRunId
    $artifactDir = if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        Join-Path $resolvedWorkspaceRoot ("output\verification\real-e2e\{0}" -f $runKey)
    } else {
        [System.IO.Path]::GetFullPath($OutputRoot)
    }
    $resolvedProjectRoot = if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
        Join-Path $resolvedWorkspaceRoot ("webnovel-writer\.tmp-real-e2e-{0}" -f $runKey)
    } else {
        [System.IO.Path]::GetFullPath($ProjectRoot)
    }

    $repoRoot = Join-Path $resolvedWorkspaceRoot 'webnovel-writer'
    $appRoot = Join-Path $repoRoot 'webnovel-writer'

    [pscustomobject]@{
        WorkspaceRoot = $resolvedWorkspaceRoot
        RepoRoot = $repoRoot
        AppRoot = $appRoot
        ArtifactDir = $artifactDir
        ProjectRoot = $resolvedProjectRoot
        PreferredPort = $PreferredPort
        RunId = $resolvedRunId
        RunKey = $runKey
        Title = $Title
        Genre = $Genre
        PythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
        LauncherModulePath = Join-Path $resolvedWorkspaceRoot 'tools\Webnovel-DashboardLauncher.psm1'
        ReadonlyAuditModulePath = Join-Path $resolvedWorkspaceRoot 'tools\Webnovel-ReadonlyAudit.psm1'
        PlaywrightDir = Join-Path $resolvedWorkspaceRoot '.playwright-cli'
        EnvironmentPath = Join-Path $artifactDir 'environment.json'
        BootstrapResponsePath = Join-Path $artifactDir 'bootstrap-response.json'
        PlanningProfileBeforePath = Join-Path $artifactDir 'planning-profile-before.json'
        PlanningProfileAfterPath = Join-Path $artifactDir 'planning-profile-after.json'
        PlanSummaryPath = Join-Path $artifactDir 'task-summary-plan.json'
        WriteChapter1SummaryPath = Join-Path $artifactDir 'task-summary-write-ch1.json'
        WriteChapter2SummaryPath = Join-Path $artifactDir 'task-summary-write-ch2.json'
        WriteChapter3SummaryPath = Join-Path $artifactDir 'task-summary-write-ch3.json'
        ReviewSummaryPath = Join-Path $artifactDir 'task-summary-review-1-3.json'
        RepairSummaryPath = Join-Path $artifactDir 'task-summary-repair.json'
        ProjectStateFinalPath = Join-Path $artifactDir 'project-state-final.json'
        ReadonlyAuditArtifactDir = Join-Path $artifactDir 'readonly-audit'
        ReadonlyAuditResultPath = Join-Path $artifactDir 'readonly-audit-result.json'
        DashboardTranscriptPath = Join-Path $artifactDir 'dashboard-playwright-transcript.txt'
        DashboardSnapshotIndexPath = Join-Path $artifactDir 'dashboard-snapshot-index.txt'
        DashboardScreenshotIndexPath = Join-Path $artifactDir 'dashboard-screenshot-index.txt'
        DashboardPagesPath = Join-Path $artifactDir 'dashboard-pages.json'
        AcceptanceReportPath = Join-Path $artifactDir 'acceptance-report.md'
    }
}

function Get-WebnovelRealE2EPort {
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

    throw 'No free port available for real e2e verification.'
}

function Initialize-WebnovelRealE2EArtifacts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    New-Item -ItemType Directory -Path $Config.ArtifactDir -Force | Out-Null
    New-Item -ItemType Directory -Path $Config.PlaywrightDir -Force | Out-Null
    Set-Content -Path $Config.DashboardTranscriptPath -Value '' -Encoding UTF8
    Set-Content -Path $Config.DashboardSnapshotIndexPath -Value '' -Encoding UTF8
    Set-Content -Path $Config.DashboardScreenshotIndexPath -Value '' -Encoding UTF8

    @{
        skipped = $true
        reason = 'repair stage skipped: not triggered yet.'
    } | ConvertTo-Json -Depth 4 | Set-Content -Path $Config.RepairSummaryPath -Encoding UTF8

    @{
        skipped = $true
        reason = 'readonly audit skipped: not run yet.'
    } | ConvertTo-Json -Depth 4 | Set-Content -Path $Config.ReadonlyAuditResultPath -Encoding UTF8

    @() | ConvertTo-Json -Depth 4 | Set-Content -Path $Config.DashboardPagesPath -Encoding UTF8
}

function Get-WebnovelRealE2EClassification {
    [CmdletBinding()]
    param(
        [switch]$EnvironmentBlocked,
        [switch]$MainlineFailed,
        [switch]$PageRegression,
        [string]$ReadonlyAuditClassification = ''
    )

    if ($EnvironmentBlocked) {
        return 'environment_blocked'
    }
    if ($MainlineFailed) {
        return 'mainline_failure'
    }
    if ($PageRegression) {
        return 'page_regression'
    }
    if ($ReadonlyAuditClassification -and $ReadonlyAuditClassification -ne 'pass') {
        return 'readonly_audit_failure'
    }
    return 'pass'
}

function New-WebnovelRealE2EAcceptanceReport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Result
    )

    $lines = @(
        '# Webnovel Real E2E Report',
        '',
        ('- Project Root: `{0}`' -f [string]$Result.project_root),
        ('- Title / Genre: `{0}` / `{1}`' -f [string]$Result.title, [string]$Result.genre),
        ('- Passed: `{0}`' -f ($(if ($Result.passed) { 'yes' } else { 'no' }))),
        ('- Classification: `{0}`' -f [string]$Result.classification)
    )

    if (-not [string]::IsNullOrWhiteSpace([string]$Result.failure_category)) {
        $lines += ('- Failure Category: `{0}`' -f [string]$Result.failure_category)
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$Result.minimal_repro)) {
        $lines += ('- Minimal Repro: {0}' -f [string]$Result.minimal_repro)
    }

    $lines += ''
    $lines += '## Phase Results'

    foreach ($phase in @($Result.phases)) {
        $phaseName = [string]$phase.name
        $phaseConclusion = [string]$phase.conclusion
        $phaseDetail = [string]$phase.detail
        $lines += ('- {0}: `{1}`' -f $phaseName, $phaseConclusion)
        if (-not [string]::IsNullOrWhiteSpace($phaseDetail)) {
            $lines += ('  - {0}' -f $phaseDetail)
        }
    }

    return ($lines -join [Environment]::NewLine)
}

function Write-WebnovelRealE2EJson {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        $Data
    )

    $Data | ConvertTo-Json -Depth 12 | Set-Content -Path $Path -Encoding UTF8
}

function Get-WebnovelRealE2ETwitterNowIso {
    [CmdletBinding()]
    param()

    (Get-Date).ToUniversalTime().ToString('o')
}

function Get-WebnovelRealE2EItemCount {
    [CmdletBinding()]
    param(
        $Items
    )

    if ($null -eq $Items) {
        return 0
    }

    return @($Items).Count
}

function Get-WebnovelRealE2EFailureCategory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Classification
    )

    switch ($Classification) {
        'environment_blocked' { return 'environment blocked' }
        'mainline_failure' { return 'mainline failure' }
        'page_regression' { return 'page regression' }
        'readonly_audit_failure' { return 'readonly audit failure' }
        default { return '' }
    }
}

function Get-WebnovelRealE2EPlaywrightScript {
    [CmdletBinding()]
    param()

    if (-not $env:CODEX_HOME) {
        $env:CODEX_HOME = Join-Path $HOME '.codex'
    }

    Join-Path $env:CODEX_HOME 'skills\playwright\scripts\playwright_cli.ps1'
}

function Get-WebnovelRealE2ELastExitCode {
    [CmdletBinding()]
    param()

    $exitCodeVariable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($null -eq $exitCodeVariable) {
        return 0
    }

    return [int]$exitCodeVariable.Value
}

function Get-WebnovelRealE2ENewPlaywrightFile {
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

function Invoke-WebnovelRealE2ECapture {
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
        [Parameter(Mandatory = $true)]
        [string]$PlaywrightWorkdir,
        [switch]$Open
    )

    $stepStartUtc = (Get-Date).ToUniversalTime()
    Add-Content -Path $TranscriptPath -Value ("## " + $Name)
    Add-Content -Path $TranscriptPath -Value ("URL: " + $Url)

    Push-Location $PlaywrightWorkdir
    try {
        if ($Open) {
            & $PlaywrightScript open $Url --browser msedge --headed | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
            $openExitCode = Get-WebnovelRealE2ELastExitCode
            if ($openExitCode -ne 0) {
                throw ("Playwright open failed for {0} (exit code {1}). See transcript: {2}" -f $Name, $openExitCode, $TranscriptPath)
            }
        } else {
            & $PlaywrightScript goto $Url | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
            $gotoExitCode = Get-WebnovelRealE2ELastExitCode
            if ($gotoExitCode -ne 0) {
                throw ("Playwright goto failed for {0} (exit code {1}). See transcript: {2}" -f $Name, $gotoExitCode, $TranscriptPath)
            }
        }

        Start-Sleep -Milliseconds 1200
        & $PlaywrightScript snapshot | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
        $snapshotExitCode = Get-WebnovelRealE2ELastExitCode
        if ($snapshotExitCode -ne 0) {
            throw ("Playwright snapshot failed for {0} (exit code {1}). See transcript: {2}" -f $Name, $snapshotExitCode, $TranscriptPath)
        }
        & $PlaywrightScript screenshot | Tee-Object -FilePath $TranscriptPath -Append | Out-Null
        $screenshotExitCode = Get-WebnovelRealE2ELastExitCode
        if ($screenshotExitCode -ne 0) {
            throw ("Playwright screenshot failed for {0} (exit code {1}). See transcript: {2}" -f $Name, $screenshotExitCode, $TranscriptPath)
        }
    } finally {
        Pop-Location
    }

    $snapshot = Get-WebnovelRealE2ENewPlaywrightFile -Directory $PlaywrightDir -Filter 'page-*.yml' -SinceUtc $stepStartUtc
    $screenshot = Get-WebnovelRealE2ENewPlaywrightFile -Directory $PlaywrightDir -Filter 'page-*.png' -SinceUtc $stepStartUtc
    Add-Content -Path $TranscriptPath -Value ''

    [ordered]@{
        name = $Name
        snapshot = $snapshot
        screenshot = $screenshot
    }
}

function Test-WebnovelRealE2ESnapshot {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$SnapshotPath,
        [string[]]$RequiredPatterns = @(),
        [string[]]$ForbiddenPatterns = @()
    )

    $issues = New-Object System.Collections.Generic.List[string]
    if (-not $SnapshotPath -or -not (Test-Path $SnapshotPath)) {
        $issues.Add('missing:snapshot')
        return [ordered]@{
            page = $Name
            snapshot = $SnapshotPath
            passed = $false
            issues = @($issues)
        }
    }

    $text = Get-Content -Path $SnapshotPath -Raw -Encoding UTF8

    foreach ($pattern in @($RequiredPatterns)) {
        if ($text -notmatch $pattern) {
            $issues.Add("missing:$pattern")
        }
    }

    foreach ($pattern in @($ForbiddenPatterns)) {
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

function Set-WebnovelRealE2EEnvironment {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    $codexBin = Join-Path $env:APPDATA 'npm'
    $nodeDir = Join-Path $env:LOCALAPPDATA 'Programs\NodePortable'
    $env:Path = $codexBin + ';' + $nodeDir + ';' + $env:Path
    if (-not $env:WEBNOVEL_CODEX_BIN) {
        $env:WEBNOVEL_CODEX_BIN = 'codex.cmd'
    }
    $env:PYTHONPATH = $Config.AppRoot + ';' + (Join-Path $Config.AppRoot 'scripts')
    $env:WEBNOVEL_WORKSPACE_ROOT = $Config.WorkspaceRoot
}

function Invoke-WebnovelRealE2EJsonGet {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    Invoke-RestMethod -Uri $Url -Headers @{ Accept = 'application/json' } -TimeoutSec 15
}

function Invoke-WebnovelRealE2EJsonPost {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        $Body
    )

    $jsonBody = $Body | ConvertTo-Json -Depth 10
    Invoke-RestMethod -Uri $Url -Method Post -Headers @{ Accept = 'application/json' } -ContentType 'application/json; charset=utf-8' -Body $jsonBody -TimeoutSec 30
}

function Get-WebnovelRealE2EQueryString {
    [CmdletBinding()]
    param(
        [hashtable]$Pairs
    )

    $parts = @()
    foreach ($key in @($Pairs.Keys)) {
        $value = $Pairs[$key]
        if ($null -eq $value -or [string]::IsNullOrWhiteSpace([string]$value)) {
            continue
        }
        $parts += ('{0}={1}' -f [uri]::EscapeDataString([string]$key), [uri]::EscapeDataString([string]$value))
    }
    if (-not $parts.Count) {
        return ''
    }
    return ('?' + ($parts -join '&'))
}

function Get-WebnovelRealE2EEnvFileValues {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line.TrimStart().StartsWith('#')) {
            continue
        }
        $parts = $line -split '=', 2
        if ($parts.Count -lt 2) {
            continue
        }
        $values[$parts[0].Trim()] = $parts[1]
    }

    return $values
}

function Get-WebnovelRealE2EApiConfigSource {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    $fileValues = Get-WebnovelRealE2EEnvFileValues -Path (Join-Path $Config.AppRoot '.env')
    $resolve = {
        param([string[]]$Keys, [string]$Default = '')
        foreach ($key in $Keys) {
            $envValue = [Environment]::GetEnvironmentVariable($key)
            if (-not [string]::IsNullOrWhiteSpace($envValue)) {
                return $envValue
            }
            if ($fileValues.ContainsKey($key) -and -not [string]::IsNullOrWhiteSpace([string]$fileValues[$key])) {
                return [string]$fileValues[$key]
            }
        }
        return $Default
    }

    $llm = [ordered]@{
        provider = (& $resolve @('WEBNOVEL_LLM_PROVIDER') 'openai-compatible')
        base_url = (& $resolve @('WEBNOVEL_LLM_BASE_URL', 'OPENAI_BASE_URL') 'https://api.openai.com/v1')
        model = (& $resolve @('WEBNOVEL_LLM_MODEL', 'OPENAI_MODEL') '')
        api_key = (& $resolve @('WEBNOVEL_LLM_API_KEY', 'OPENAI_API_KEY') '')
    }
    $rag = [ordered]@{
        base_url = (& $resolve @('WEBNOVEL_RAG_BASE_URL') 'https://api.siliconflow.cn/v1')
        embed_model = (& $resolve @('WEBNOVEL_RAG_EMBED_MODEL') '')
        rerank_model = (& $resolve @('WEBNOVEL_RAG_RERANK_MODEL') '')
        api_key = (& $resolve @('WEBNOVEL_RAG_API_KEY') '')
    }

    $reasons = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrWhiteSpace([string]$llm.model)) {
        $reasons.Add('LLM model is missing from the reusable API config source.')
    }
    if ([string]::IsNullOrWhiteSpace([string]$llm.api_key)) {
        $reasons.Add('LLM API key is missing from the reusable API config source.')
    }
    if ([string]::IsNullOrWhiteSpace([string]$rag.embed_model)) {
        $reasons.Add('RAG embed model is missing from the reusable API config source.')
    }
    if ([string]::IsNullOrWhiteSpace([string]$rag.rerank_model)) {
        $reasons.Add('RAG rerank model is missing from the reusable API config source.')
    }
    if ([string]::IsNullOrWhiteSpace([string]$rag.api_key)) {
        $reasons.Add('RAG API key is missing from the reusable API config source.')
    }

    return [ordered]@{
        env_file = (Join-Path $Config.AppRoot '.env')
        llm = $llm
        rag = $rag
        available = ($reasons.Count -eq 0)
        missing_reasons = @($reasons)
    }
}

function Get-WebnovelRealE2EEnvironmentBaseline {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl
    )

    $gitBranch = ''
    $gitCommit = ''
    try {
        $gitBranch = (& git -C $Config.WorkspaceRoot branch --show-current 2>$null | Select-Object -First 1)
    } catch {
        $gitBranch = ''
    }
    try {
        $gitCommit = (& git -C $Config.WorkspaceRoot rev-parse HEAD 2>$null | Select-Object -First 1)
    } catch {
        $gitCommit = ''
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $npxCommand = Get-Command npx -ErrorAction SilentlyContinue
    $playwrightScript = Get-WebnovelRealE2EPlaywrightScript

    $pythonVersion = ''
    $nodeVersion = ''
    try {
        if ($pythonCommand) {
            $pythonVersion = (& $pythonCommand.Source --version 2>&1 | Select-Object -First 1)
        }
    } catch {
        $pythonVersion = ''
    }
    try {
        if ($nodeCommand) {
            $nodeVersion = (& $nodeCommand.Source --version 2>&1 | Select-Object -First 1)
        }
    } catch {
        $nodeVersion = ''
    }

    $apiSource = Get-WebnovelRealE2EApiConfigSource -Config $Config

    $reasons = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path $Config.PythonExe) -and -not $pythonCommand) {
        $reasons.Add('Python runtime is not available.')
    }
    if (-not $nodeCommand) {
        $reasons.Add('Node.js runtime is not available.')
    }
    if (-not $npxCommand) {
        $reasons.Add('npx is not available, so Playwright checks cannot run.')
    }
    if (-not (Test-Path $playwrightScript)) {
        $reasons.Add('Playwright CLI script is missing under CODEX_HOME.')
    }
    foreach ($reason in @($apiSource.missing_reasons)) {
        $reasons.Add([string]$reason)
    }

    [ordered]@{
        captured_at = Get-WebnovelRealE2ETwitterNowIso
        git = @{
            branch = $gitBranch
            commit = $gitCommit
        }
        runtime = @{
            python = @{
                configured_python = $Config.PythonExe
                configured_python_exists = (Test-Path $Config.PythonExe)
                command_available = [bool]$pythonCommand
                version = $pythonVersion
            }
            node = @{
                command_available = [bool]$nodeCommand
                version = $nodeVersion
            }
            npx = @{
                command_available = [bool]$npxCommand
            }
            playwright = @{
                script_path = $playwrightScript
                exists = (Test-Path $playwrightScript)
            }
        }
        api_source = @{
            env_file = $apiSource.env_file
            available = [bool]$apiSource.available
            llm = @{
                provider = [string]$apiSource.llm.provider
                base_url = [string]$apiSource.llm.base_url
                model = [string]$apiSource.llm.model
                has_api_key = -not [string]::IsNullOrWhiteSpace([string]$apiSource.llm.api_key)
            }
            rag = @{
                base_url = [string]$apiSource.rag.base_url
                embed_model = [string]$apiSource.rag.embed_model
                rerank_model = [string]$apiSource.rag.rerank_model
                has_api_key = -not [string]::IsNullOrWhiteSpace([string]$apiSource.rag.api_key)
            }
        }
        environment_blocked = ($reasons.Count -gt 0)
        blocking_reasons = @($reasons)
    }
}

function Set-WebnovelRealE2EProjectApiSettings {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $apiSource = Get-WebnovelRealE2EApiConfigSource -Config $Config
    if (-not $apiSource.available) {
        throw ('Reusable API config is incomplete: ' + (@($apiSource.missing_reasons) -join '; '))
    }

    $query = Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $ProjectRoot }
    $llmResult = Invoke-WebnovelRealE2EJsonPost -Url ($BaseUrl.TrimEnd('/') + '/api/settings/llm' + $query) -Body @{
        provider = $apiSource.llm.provider
        base_url = $apiSource.llm.base_url
        model = $apiSource.llm.model
        api_key = $apiSource.llm.api_key
    }
    $ragResult = Invoke-WebnovelRealE2EJsonPost -Url ($BaseUrl.TrimEnd('/') + '/api/settings/rag' + $query) -Body @{
        base_url = $apiSource.rag.base_url
        embed_model = $apiSource.rag.embed_model
        rerank_model = $apiSource.rag.rerank_model
        api_key = $apiSource.rag.api_key
    }

    return [ordered]@{
        llm = $llmResult
        rag = $ragResult
    }
}

function Get-WebnovelRealE2EProjectApiStatus {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $query = Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $ProjectRoot }
    $llmStatus = Invoke-WebnovelRealE2EJsonGet -Url ($BaseUrl.TrimEnd('/') + '/api/llm/status' + $query)
    $ragStatus = Invoke-WebnovelRealE2EJsonGet -Url ($BaseUrl.TrimEnd('/') + '/api/rag/status' + $query)
    return [ordered]@{
        llm = $llmStatus
        rag = $ragStatus
    }
}

function Get-WebnovelRealE2EStatusLabel {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        $Payload
    )

    if ($null -eq $Payload) {
        return ''
    }
    if ($Payload.PSObject -and ($Payload.PSObject.Properties.Name -contains 'effective_status')) {
        return [string]$Payload.effective_status
    }
    if ($Payload.PSObject -and ($Payload.PSObject.Properties.Name -contains 'connection_status')) {
        return [string]$Payload.connection_status
    }
    return ''
}

function Get-WebnovelRealE2EObjectProperty {
    [CmdletBinding()]
    param(
        $Payload,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        $Default = $null
    )

    if ($null -eq $Payload) {
        return $Default
    }
    $propertyNames = @()
    if ($Payload.PSObject -and $Payload.PSObject.Properties) {
        $propertyNames = @($Payload.PSObject.Properties | ForEach-Object { $_.Name })
    }
    if ($propertyNames -contains $Name) {
        return $Payload.$Name
    }
    if ($Payload -is [System.Collections.IDictionary] -and $Payload.Contains($Name)) {
        return $Payload[$Name]
    }
    return $Default
}

function New-WebnovelRealE2ERepairRequestBody {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$SourceTaskId,
        [Parameter(Mandatory = $true)]
        [psobject]$RepairCandidate
    )

    $chapter = [int](Get-WebnovelRealE2EObjectProperty -Payload $RepairCandidate -Name 'chapter' -Default 0)
    $guardrails = @(Get-WebnovelRealE2EObjectProperty -Payload $RepairCandidate -Name 'guardrails' -Default @())
    $normalizedGuardrails = @($guardrails | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })

    $options = [ordered]@{
        source_task_id = $SourceTaskId
        issue_type = [string](Get-WebnovelRealE2EObjectProperty -Payload $RepairCandidate -Name 'issue_type' -Default '')
        issue_title = [string](Get-WebnovelRealE2EObjectProperty -Payload $RepairCandidate -Name 'issue_title' -Default '')
        rewrite_goal = [string](Get-WebnovelRealE2EObjectProperty -Payload $RepairCandidate -Name 'rewrite_goal' -Default '')
    }
    if ($normalizedGuardrails.Count -gt 0) {
        $options['guardrails'] = $normalizedGuardrails
    }

    return [ordered]@{
        project_root = $ProjectRoot
        chapter = $chapter
        mode = 'standard'
        require_manual_approval = $false
        options = $options
    }
}

function Start-WebnovelRealE2EDashboard {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    if (-not (Test-Path $Config.LauncherModulePath)) {
        throw "Dashboard launcher module not found: $($Config.LauncherModulePath)"
    }
    if (-not (Test-Path $Config.PythonExe)) {
        throw "Python virtualenv not found: $($Config.PythonExe)"
    }

    Import-Module $Config.LauncherModulePath -Force
    Set-WebnovelRealE2EEnvironment -Config $Config

    $dashboardPort = Get-WebnovelRealE2EPort -PreferredPort $Config.PreferredPort
    $baseUrl = Get-WebnovelDashboardBaseUrl -Host '127.0.0.1' -Port $dashboardPort
    $process = Start-WebnovelDashboardServer -PythonExe $Config.PythonExe -AppRoot $Config.AppRoot -WorkspaceRoot $Config.WorkspaceRoot -ListenHost '127.0.0.1' -Port $dashboardPort
    $probe = Wait-WebnovelDashboardHealthy -BaseUrl $baseUrl -TimeoutSeconds 45 -ProcessId $process.Id

    [pscustomobject]@{
        Process = $process
        Port = $dashboardPort
        BaseUrl = $baseUrl
        Probe = $probe
    }
}

function Stop-WebnovelRealE2EDashboard {
    [CmdletBinding()]
    param(
        $Process
    )

    if (-not $Process) {
        return
    }

    try {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction Stop
            Wait-Process -Id $Process.Id -ErrorAction SilentlyContinue
        }
    } catch {
    }
}

function Get-WebnovelRealE2ETaskSummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [int]$Limit = 50
    )

    $query = Get-WebnovelRealE2EQueryString -Pairs @{ limit = $Limit; project_root = $ProjectRoot }
    Invoke-WebnovelRealE2EJsonGet -Url ($BaseUrl.TrimEnd('/') + '/api/tasks/summary' + $query)
}

function Save-WebnovelRealE2ETaskSummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $summary = Get-WebnovelRealE2ETaskSummary -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot
    Write-WebnovelRealE2EJson -Path $Path -Data $summary
    return $summary
}

function Get-WebnovelRealE2ETaskDetail {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$TaskId
    )

    $query = Get-WebnovelRealE2EQueryString -Pairs @{ event_limit = 200; project_root = $ProjectRoot }
    Invoke-WebnovelRealE2EJsonGet -Url ($BaseUrl.TrimEnd('/') + "/api/tasks/$TaskId/detail" + $query)
}

function Wait-WebnovelRealE2ETask {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$TaskId,
        [Parameter(Mandatory = $true)]
        [string]$SummaryPath,
        [int]$Chapter = 0,
        [switch]$AllowRetryOnce,
        [int]$TimeoutSeconds = 3600
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $retryTriggered = $false
    $approvalActions = New-Object System.Collections.Generic.List[string]
    $lastDetail = $null

    while ((Get-Date) -lt $deadline) {
        $lastDetail = Get-WebnovelRealE2ETaskDetail -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot -TaskId $TaskId
        $task = $lastDetail.task
        $status = [string]$task.status

        if ($status -eq 'awaiting_chapter_brief_approval' -and $Chapter -gt 0) {
            Invoke-WebnovelRealE2EJsonPost -Url ($BaseUrl.TrimEnd('/') + "/api/chapters/$Chapter/brief/approve" + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $ProjectRoot })) -Body @{
                reason = 'Real E2E auto approval for chapter brief.'
            } | Out-Null
            $approvalActions.Add("chapter-brief:$Chapter")
            Start-Sleep -Seconds 2
            continue
        }

        if ($status -eq 'awaiting_writeback_approval') {
            Invoke-WebnovelRealE2EJsonPost -Url ($BaseUrl.TrimEnd('/') + '/api/review/approve' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $ProjectRoot })) -Body @{
                task_id = $TaskId
                reason = 'Real E2E auto approval for writeback.'
            } | Out-Null
            $approvalActions.Add("writeback:$TaskId")
            Start-Sleep -Seconds 2
            continue
        }

        if ($status -eq 'completed') {
            Save-WebnovelRealE2ETaskSummary -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot -Path $SummaryPath | Out-Null
            return [ordered]@{
                success = $true
                task = $task
                detail = $lastDetail
                retried = $retryTriggered
                approvals = @($approvalActions)
            }
        }

        if ($status -in @('failed', 'interrupted', 'rejected')) {
            $errorPayload = Get-WebnovelRealE2EObjectProperty -Payload $task -Name 'error'
            $errorDetails = Get-WebnovelRealE2EObjectProperty -Payload $errorPayload -Name 'details'
            $errorCode = [string](Get-WebnovelRealE2EObjectProperty -Payload $errorPayload -Name 'code' -Default '')
            $recoverability = [string](Get-WebnovelRealE2EObjectProperty -Payload $errorDetails -Name 'recoverability' -Default '')
            $resumeStep = [string](Get-WebnovelRealE2EObjectProperty -Payload $errorDetails -Name 'suggested_resume_step' -Default '')
            $canRetry = $AllowRetryOnce -and -not $retryTriggered -and ($errorCode -eq 'INVALID_STEP_OUTPUT' -or $recoverability -in @('retriable', 'auto_retried'))
            if ($canRetry) {
                $retryBody = @{}
                if (-not [string]::IsNullOrWhiteSpace($resumeStep)) {
                    $retryBody.resume_from_step = $resumeStep
                }
                Invoke-WebnovelRealE2EJsonPost -Url ($BaseUrl.TrimEnd('/') + "/api/tasks/$TaskId/retry" + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $ProjectRoot })) -Body $retryBody | Out-Null
                $retryTriggered = $true
                Start-Sleep -Seconds 2
                continue
            }

            Save-WebnovelRealE2ETaskSummary -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot -Path $SummaryPath | Out-Null
            return [ordered]@{
                success = $false
                task = $task
                detail = $lastDetail
                retried = $retryTriggered
                approvals = @($approvalActions)
            }
        }

        Start-Sleep -Seconds 3
    }

    Save-WebnovelRealE2ETaskSummary -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot -Path $SummaryPath | Out-Null
    return [ordered]@{
        success = $false
        task = if ($lastDetail) { $lastDetail.task } else { $null }
        detail = $lastDetail
        retried = $retryTriggered
        approvals = @($approvalActions)
        timeout = $true
    }
}

function Get-WebnovelRealE2EChapterFileHits {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [int]$Chapter
    )

    $chapterDigits = '{0:d4}' -f $Chapter
    @(Get-ChildItem -Path (Join-Path $ProjectRoot $script:WebnovelChapterDir) -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -eq '.md' -and $_.FullName -match [regex]::Escape($chapterDigits) })
}

function Test-WebnovelRealE2EProjectOutputs {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $summaryFiles = 1..3 | ForEach-Object {
        Test-Path (Join-Path $ProjectRoot ('.webnovel\summaries\ch{0:d4}.md' -f $_))
    }
    $chapterFiles = 1..3 | ForEach-Object {
        (Get-WebnovelRealE2EItemCount -Items (Get-WebnovelRealE2EChapterFileHits -ProjectRoot $ProjectRoot -Chapter $_)) -gt 0
    }
    $volumePlanExists = Test-Path (Join-Path (Join-Path $ProjectRoot $script:WebnovelOutlineDir) 'volume-01-plan.md')
    $statePath = Join-Path $ProjectRoot '.webnovel\state.json'
    $state = if (Test-Path $statePath) {
        Get-Content -Path $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        $null
    }

    [ordered]@{
        volume_plan_exists = $volumePlanExists
        chapter_files = @{
            ch1 = $chapterFiles[0]
            ch2 = $chapterFiles[1]
            ch3 = $chapterFiles[2]
        }
        summary_files = @{
            ch1 = $summaryFiles[0]
            ch2 = $summaryFiles[1]
            ch3 = $summaryFiles[2]
        }
        state_current_chapter = if ($state) { [int]$state.progress.current_chapter } else { 0 }
        state_has_volume_plan = if ($state) { [bool]$state.planning.volume_plans.'1' } else { $false }
    }
}

function Test-WebnovelRealE2EDashboardPages {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $playwrightScript = Get-WebnovelRealE2EPlaywrightScript
    if (-not (Test-Path $playwrightScript)) {
        throw "Playwright CLI script not found: $playwrightScript"
    }

    $env:PLAYWRIGHT_CLI_SESSION = 'webnovel-real-e2e'

    try {
        & $playwrightScript close | Out-Null
    } catch {
    }

    $encodedRoot = [uri]::EscapeDataString($ProjectRoot)
    $pages = @(
        @{
            Name = 'control'
            Url = "$BaseUrl/?project_root=$encodedRoot&page=control"
            RequiredPatterns = @([regex]::Escape($Config.Title))
            ForbiddenPatterns = @('PROJECT_NOT_SELECTED', 'Unhandled')
            Open = $true
        },
        @{
            Name = 'tasks'
            Url = "$BaseUrl/?project_root=$encodedRoot&page=tasks"
            RequiredPatterns = @()
            ForbiddenPatterns = @('manual-only', 'approval-gate', 'hard blocking issue', 'Detected audit schema', 'through v2')
            Open = $false
        },
        @{
            Name = 'quality'
            Url = "$BaseUrl/?project_root=$encodedRoot&page=quality"
            RequiredPatterns = @()
            ForbiddenPatterns = @('low-data', 'manual-only', 'approval-gate', 'Detected audit schema', 'through v2')
            Open = $false
        }
    )

    $results = @()
    foreach ($page in $pages) {
        $capture = Invoke-WebnovelRealE2ECapture `
            -Name $page.Name `
            -Url $page.Url `
            -PlaywrightScript $playwrightScript `
            -PlaywrightDir $Config.PlaywrightDir `
            -TranscriptPath $Config.DashboardTranscriptPath `
            -PlaywrightWorkdir $Config.WorkspaceRoot `
            -Open:([bool]$page.Open)
        $pageCheck = Test-WebnovelRealE2ESnapshot -Name $page.Name -SnapshotPath $capture.snapshot -RequiredPatterns $page.RequiredPatterns -ForbiddenPatterns $page.ForbiddenPatterns
        $results += [ordered]@{
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

    $snapshotFiles = @($results | ForEach-Object { $_.snapshot } | Where-Object { $_ })
    $screenshotFiles = @($results | ForEach-Object { $_.screenshot } | Where-Object { $_ })
    Set-Content -Path $Config.DashboardSnapshotIndexPath -Value ($snapshotFiles -join [Environment]::NewLine) -Encoding UTF8
    Set-Content -Path $Config.DashboardScreenshotIndexPath -Value ($screenshotFiles -join [Environment]::NewLine) -Encoding UTF8
    Write-WebnovelRealE2EJson -Path $Config.DashboardPagesPath -Data $results
    return ,$results
}

function Invoke-WebnovelRealE2EReadonlyAudit {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    if (-not (Test-Path $Config.ReadonlyAuditModulePath)) {
        throw "Readonly audit module not found: $($Config.ReadonlyAuditModulePath)"
    }

    Import-Module $Config.ReadonlyAuditModulePath -Force
    $auditConfig = Get-WebnovelReadonlyAuditConfig -WorkspaceRoot $Config.WorkspaceRoot -OutputRoot $Config.ReadonlyAuditArtifactDir -PreferredPort $Config.PreferredPort -ProjectRoot $ProjectRoot
    $auditResult = Invoke-WebnovelReadonlyAudit -Config $auditConfig
    Write-WebnovelRealE2EJson -Path $Config.ReadonlyAuditResultPath -Data $auditResult
    return $auditResult
}

function Invoke-WebnovelRealE2E {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    Initialize-WebnovelRealE2EArtifacts -Config $Config

    $dashboardProcess = $null
    $baseUrl = ''
    $phaseResults = New-Object System.Collections.Generic.List[object]
    $pageResults = @()
    $readonlyAuditResult = $null
    $mainlineFailed = $false
    $pageRegression = $false
    $environmentBlocked = $false
    $minimalRepro = ''

    try {
        $dashboard = Start-WebnovelRealE2EDashboard -Config $Config
        $dashboardProcess = $dashboard.Process
        $baseUrl = $dashboard.BaseUrl

        $environment = Get-WebnovelRealE2EEnvironmentBaseline -Config $Config -BaseUrl $baseUrl
        Write-WebnovelRealE2EJson -Path $Config.EnvironmentPath -Data $environment
        if ($environment.environment_blocked) {
            $environmentBlocked = $true
            $minimalRepro = ($environment.blocking_reasons -join '; ')
            $phaseResults.Add([ordered]@{ name = 'Environment'; conclusion = 'failed'; detail = ('Environment blocked: ' + $minimalRepro) }) | Out-Null
            throw 'environment_blocked'
        }
        $phaseResults.Add([ordered]@{ name = 'Environment'; conclusion = 'pass'; detail = 'Python/Node/LLM/RAG/Playwright baseline is ready.' }) | Out-Null

        $bootstrapResponse = Invoke-WebnovelRealE2EJsonPost -Url ($baseUrl + '/api/project/bootstrap') -Body @{
            project_root = $Config.ProjectRoot
            title = $Config.Title
            genre = $Config.Genre
        }
        Write-WebnovelRealE2EJson -Path $Config.BootstrapResponsePath -Data $bootstrapResponse

        $bootstrapStatePath = Join-Path $Config.ProjectRoot '.webnovel\state.json'
        $planningProfilePath = Join-Path $Config.ProjectRoot '.webnovel\planning-profile.json'
        $outlinePath = Join-Path (Join-Path $Config.ProjectRoot $script:WebnovelOutlineDir) $script:WebnovelMasterOutlineFile
        $bootstrapState = Get-Content -Path $bootstrapStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not (Test-Path $planningProfilePath) -or -not (Test-Path $outlinePath) -or -not $bootstrapState.planning.project_info) {
            throw 'Bootstrap did not create the expected planning files.'
        }

        $apiSettingsResult = Set-WebnovelRealE2EProjectApiSettings -Config $Config -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot
        $projectApiStatus = Get-WebnovelRealE2EProjectApiStatus -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot
        $environment.api_apply = @{
            llm_saved = [bool]$apiSettingsResult.llm.saved
            rag_saved = [bool]$apiSettingsResult.rag.saved
        }
        $environment.project_status_after_apply = $projectApiStatus
        Write-WebnovelRealE2EJson -Path $Config.EnvironmentPath -Data $environment

        $projectLlmStatus = Get-WebnovelRealE2EStatusLabel -Payload $projectApiStatus.llm
        $projectRagStatus = Get-WebnovelRealE2EStatusLabel -Payload $projectApiStatus.rag
        if ($projectLlmStatus -in @('not_configured', 'failed') -or $projectRagStatus -in @('not_configured', 'failed')) {
            $environmentBlocked = $true
            $minimalRepro = ('Project API status is not ready after apply. llm={0}; rag={1}' -f $projectLlmStatus, $projectRagStatus)
            $phaseResults.Add([ordered]@{ name = 'Environment'; conclusion = 'failed'; detail = $minimalRepro }) | Out-Null
            throw 'environment_blocked'
        }

        $planningProfileBefore = Invoke-WebnovelRealE2EJsonGet -Url ($baseUrl + '/api/project/planning-profile' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $Config.ProjectRoot }))
        Write-WebnovelRealE2EJson -Path $Config.PlanningProfileBeforePath -Data $planningProfileBefore
        $planningProfileAfter = Invoke-WebnovelRealE2EJsonPost -Url ($baseUrl + '/api/project/planning-profile' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $Config.ProjectRoot })) -Body $planningProfileBefore.profile
        Write-WebnovelRealE2EJson -Path $Config.PlanningProfileAfterPath -Data $planningProfileAfter
        $phaseResults.Add([ordered]@{ name = 'Bootstrap'; conclusion = 'pass'; detail = 'bootstrap plus planning-profile read/save both succeeded.' }) | Out-Null

        $planTask = Invoke-WebnovelRealE2EJsonPost -Url ($baseUrl + '/api/tasks/plan' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $Config.ProjectRoot })) -Body @{ project_root = $Config.ProjectRoot; volume = '1' }
        $planResult = Wait-WebnovelRealE2ETask -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot -TaskId ([string]$planTask.id) -SummaryPath $Config.PlanSummaryPath
        if (-not $planResult.success) {
            $mainlineFailed = $true
            $minimalRepro = 'plan volume=1 did not reach a completed terminal state.'
        }

        foreach ($chapter in 1..3) {
            if ($mainlineFailed) { break }
            $summaryPath = switch ($chapter) { 1 { $Config.WriteChapter1SummaryPath } 2 { $Config.WriteChapter2SummaryPath } default { $Config.WriteChapter3SummaryPath } }
            $writeTask = Invoke-WebnovelRealE2EJsonPost -Url ($baseUrl + '/api/tasks/write' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $Config.ProjectRoot })) -Body @{ project_root = $Config.ProjectRoot; chapter = $chapter }
            $chapterResult = Wait-WebnovelRealE2ETask -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot -TaskId ([string]$writeTask.id) -SummaryPath $summaryPath -Chapter $chapter -AllowRetryOnce
            if (-not $chapterResult.success) {
                $mainlineFailed = $true
                $minimalRepro = ('write chapter={0} did not reach a completed terminal state.' -f $chapter)
            }
        }

        $reviewSummary = $null
        if (-not $mainlineFailed) {
            $reviewTask = Invoke-WebnovelRealE2EJsonPost -Url ($baseUrl + '/api/tasks/review' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $Config.ProjectRoot })) -Body @{ project_root = $Config.ProjectRoot; chapter_range = '1-3' }
            $reviewResult = Wait-WebnovelRealE2ETask -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot -TaskId ([string]$reviewTask.id) -SummaryPath $Config.ReviewSummaryPath
            $reviewSummary = $reviewResult.detail.task.artifacts.review_summary
            if (-not $reviewResult.success -or -not $reviewSummary -or -not ($reviewSummary.PSObject.Properties.Name -contains 'blocking') -or -not ($reviewSummary.PSObject.Properties.Name -contains 'can_proceed') -or -not ($reviewSummary.PSObject.Properties.Name -contains 'severity_counts')) {
                $mainlineFailed = $true
                $minimalRepro = 'review chapter_range=1-3 did not expose the required structured result.'
            }
        }

        if ($mainlineFailed) {
            $phaseResults.Add([ordered]@{ name = 'Mainline'; conclusion = 'failed'; detail = $minimalRepro }) | Out-Null
            throw 'mainline_failure'
        }
        $phaseResults.Add([ordered]@{ name = 'Mainline'; conclusion = 'pass'; detail = 'plan/write 1-3/review 1-3 all closed successfully.' }) | Out-Null

        $repairRan = $false
        if ($reviewSummary) {
            $repairCandidate = @($reviewSummary.repair_candidates | Where-Object { [bool]($_.auto_rewrite_eligible) -and [int]($_.chapter) -gt 0 } | Select-Object -First 1)
            if ((Get-WebnovelRealE2EItemCount -Items $repairCandidate) -gt 0) {
                $repairRan = $true
                $repairChapter = [int]$repairCandidate[0].chapter
                $repairRequest = New-WebnovelRealE2ERepairRequestBody -ProjectRoot $Config.ProjectRoot -SourceTaskId ([string]$reviewTask.id) -RepairCandidate $repairCandidate[0]
                $repairTask = Invoke-WebnovelRealE2EJsonPost -Url ($baseUrl + '/api/tasks/repair' + (Get-WebnovelRealE2EQueryString -Pairs @{ project_root = $Config.ProjectRoot })) -Body $repairRequest
                $repairResult = Wait-WebnovelRealE2ETask -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot -TaskId ([string]$repairTask.id) -SummaryPath $Config.RepairSummaryPath
                $repairBackupsDir = Join-Path $Config.ProjectRoot '.webnovel\repair-backups'
                $repairReportsDir = Join-Path $Config.ProjectRoot '.webnovel\repair-reports'
                if (-not $repairResult.success -or -not (Test-Path $repairBackupsDir) -or -not (Test-Path $repairReportsDir)) {
                    $mainlineFailed = $true
                    $minimalRepro = ('repair chapter={0} did not close or did not write backup/report artifacts.' -f $repairChapter)
                    $phaseResults.Add([ordered]@{ name = 'Repair'; conclusion = 'failed'; detail = $minimalRepro }) | Out-Null
                    throw 'mainline_failure'
                }
                $phaseResults.Add([ordered]@{ name = 'Repair'; conclusion = 'pass'; detail = ('repair chapter={0} closed successfully and wrote backup/report artifacts.' -f $repairChapter) }) | Out-Null
            }
        }
        if (-not $repairRan) {
            @{ skipped = $true; reason = 'repair stage skipped: review did not expose an eligible repair candidate.' } | ConvertTo-Json -Depth 4 | Set-Content -Path $Config.RepairSummaryPath -Encoding UTF8
            $phaseResults.Add([ordered]@{ name = 'Repair'; conclusion = 'skipped'; detail = 'review did not expose an eligible repair candidate.' }) | Out-Null
        }

        $projectOutputs = Test-WebnovelRealE2EProjectOutputs -ProjectRoot $Config.ProjectRoot
        if (-not $projectOutputs.volume_plan_exists -or -not $projectOutputs.chapter_files.ch1 -or -not $projectOutputs.chapter_files.ch2 -or -not $projectOutputs.chapter_files.ch3 -or -not $projectOutputs.summary_files.ch1 -or -not $projectOutputs.summary_files.ch2 -or -not $projectOutputs.summary_files.ch3 -or $projectOutputs.state_current_chapter -lt 3 -or -not $projectOutputs.state_has_volume_plan) {
            $mainlineFailed = $true
            $minimalRepro = 'Final project outputs are missing chapter files, summary files, or volume-plan state sync.'
            throw 'mainline_failure'
        }

        $pageResults = Test-WebnovelRealE2EDashboardPages -Config $Config -BaseUrl $baseUrl -ProjectRoot $Config.ProjectRoot
        $failedPageResults = @($pageResults | Where-Object { -not $_.passed })
        if ((Get-WebnovelRealE2EItemCount -Items $failedPageResults) -gt 0) {
            $pageRegression = $true
            $phaseResults.Add([ordered]@{ name = 'Dashboard'; conclusion = 'failed'; detail = 'At least one dashboard page exposed a visible regression.' }) | Out-Null
        } else {
            $phaseResults.Add([ordered]@{ name = 'Dashboard'; conclusion = 'pass'; detail = 'control/tasks/quality matched the real project state.' }) | Out-Null
        }

        Stop-WebnovelRealE2EDashboard -Process $dashboardProcess
        $dashboardProcess = $null

        $readonlyAuditResult = Invoke-WebnovelRealE2EReadonlyAudit -Config $Config -ProjectRoot $Config.ProjectRoot
        if ([string]$readonlyAuditResult.classification -ne 'pass') {
            $phaseResults.Add([ordered]@{ name = 'Readonly Audit'; conclusion = 'failed'; detail = ('readonly audit classification = {0}' -f [string]$readonlyAuditResult.classification) }) | Out-Null
        } else {
            $phaseResults.Add([ordered]@{ name = 'Readonly Audit'; conclusion = 'pass'; detail = 'precheck and readonly page verification both passed.' }) | Out-Null
        }
    } catch {
        if (-not $minimalRepro -and $_.Exception.Message -notin @('environment_blocked', 'mainline_failure')) {
            $minimalRepro = $_.Exception.Message
        }
        if (-not $environmentBlocked -and -not $mainlineFailed -and $_.Exception.Message -notin @('environment_blocked')) {
            $mainlineFailed = $true
            $mainlinePhaseResults = @($phaseResults | Where-Object { $_.name -eq 'Mainline' })
            if ((Get-WebnovelRealE2EItemCount -Items $mainlinePhaseResults) -eq 0) {
                $phaseResults.Add([ordered]@{ name = 'Mainline'; conclusion = 'failed'; detail = $minimalRepro }) | Out-Null
            }
        }
    } finally {
        $statePath = Join-Path $Config.ProjectRoot '.webnovel\state.json'
        if (Test-Path $statePath) {
            $statePayload = Get-Content -Path $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-WebnovelRealE2EJson -Path $Config.ProjectStateFinalPath -Data $statePayload
        } elseif (-not (Test-Path $Config.ProjectStateFinalPath)) {
            Write-WebnovelRealE2EJson -Path $Config.ProjectStateFinalPath -Data @{ skipped = $true; reason = 'state.json not available.' }
        }
        Stop-WebnovelRealE2EDashboard -Process $dashboardProcess
    }

    $readonlyClassification = ''
    if ($readonlyAuditResult) {
        $readonlyClassification = [string]$readonlyAuditResult.classification
    }
    $classification = Get-WebnovelRealE2EClassification -EnvironmentBlocked:$environmentBlocked -MainlineFailed:$mainlineFailed -PageRegression:$pageRegression -ReadonlyAuditClassification $readonlyClassification
    $result = @{}
    $result['classification'] = $classification
    $result['passed'] = ($classification -eq 'pass')
    $result['failure_category'] = (Get-WebnovelRealE2EFailureCategory -Classification $classification)
    $result['project_root'] = $Config.ProjectRoot
    $result['title'] = $Config.Title
    $result['genre'] = $Config.Genre
    $result['artifact_dir'] = $Config.ArtifactDir
    $result['minimal_repro'] = $minimalRepro
    $result['dashboard_pages'] = $pageResults
    $result['readonly_audit'] = $readonlyAuditResult
    $result['phases'] = $phaseResults.ToArray()
    $report = New-WebnovelRealE2EAcceptanceReport -Result $result
    Set-Content -Path $Config.AcceptanceReportPath -Value $report -Encoding UTF8
    return [pscustomobject]$result
}

Export-ModuleMember -Function `
    Get-WebnovelRealE2EConfig, `
    Get-WebnovelRealE2EPort, `
    Initialize-WebnovelRealE2EArtifacts, `
    Get-WebnovelRealE2EClassification, `
    New-WebnovelRealE2EAcceptanceReport, `
    Invoke-WebnovelRealE2E
