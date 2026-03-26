Set-StrictMode -Version Latest

function Get-WebnovelMultiAgentTestConfig {
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
    $artifactDir = if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        Join-Path $resolvedWorkspaceRoot ("output\verification\multi-agent-test\{0}-{1}" -f $dateStamp, $resolvedRunId)
    } else {
        [System.IO.Path]::GetFullPath($OutputRoot)
    }
    $repoRoot = Join-Path $resolvedWorkspaceRoot 'webnovel-writer'
    $appRoot = Join-Path $repoRoot 'webnovel-writer'
    $frontendRoot = Join-Path $appRoot 'dashboard\frontend'

    [pscustomobject]@{
        WorkspaceRoot = $resolvedWorkspaceRoot
        RepoRoot = $repoRoot
        AppRoot = $appRoot
        FrontendRoot = $frontendRoot
        ArtifactDir = $artifactDir
        PreferredPort = $PreferredPort
        ProjectRoot = $ProjectRoot
        RunId = $resolvedRunId
        Title = $Title
        Genre = $Genre
        LaneLogsDir = Join-Path $artifactDir 'lane-logs'
        PreflightPath = Join-Path $artifactDir 'preflight.json'
        BackendLanePath = Join-Path $artifactDir 'backend-lane.json'
        DataCliLanePath = Join-Path $artifactDir 'data-cli-lane.json'
        FrontendLanePath = Join-Path $artifactDir 'frontend-lane.json'
        ResultPath = Join-Path $artifactDir 'result.json'
        ReportPath = Join-Path $artifactDir 'report.md'
        ProgressPath = Join-Path $artifactDir 'progress.json'
        ControlPath = Join-Path $artifactDir 'control.json'
        ManifestPath = Join-Path $artifactDir 'manifest.json'
        RealE2EOutputRoot = Join-Path $artifactDir 'real-e2e'
        RealE2EResultPath = Join-Path $artifactDir 'real-e2e-result.json'
        RuntimeDir = Join-Path (Join-Path $resolvedWorkspaceRoot 'output\verification\multi-agent-test') '_runtime'
        ActiveExecutionPath = Join-Path (Join-Path (Join-Path $resolvedWorkspaceRoot 'output\verification\multi-agent-test') '_runtime') 'active-execution.json'
        LastKnownExecutionPath = Join-Path (Join-Path (Join-Path $resolvedWorkspaceRoot 'output\verification\multi-agent-test') '_runtime') 'last-known.json'
        RealE2EModulePath = Join-Path $resolvedWorkspaceRoot 'tools\Webnovel-RealE2E.psm1'
        PlaywrightScriptPath = Get-WebnovelMultiAgentPlaywrightScript
        NodeModulesPath = Join-Path $frontendRoot 'node_modules'
    }
}

function Get-WebnovelMultiAgentPlaywrightScript {
    [CmdletBinding()]
    param()

    if (-not $env:CODEX_HOME) {
        $env:CODEX_HOME = Join-Path $HOME '.codex'
    }

    Join-Path $env:CODEX_HOME 'skills\playwright\scripts\playwright_cli.ps1'
}

function Initialize-WebnovelMultiAgentTestArtifacts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    foreach ($path in @(
        $Config.ArtifactDir,
        $Config.LaneLogsDir,
        $Config.RealE2EOutputRoot,
        $Config.RuntimeDir
    )) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }

    Write-WebnovelMultiAgentJson -Path $Config.RealE2EResultPath -Data @{
        skipped = $true
        reason = 'RealE2E skipped: local lanes have not requested it yet.'
    }
    Write-WebnovelMultiAgentJson -Path $Config.ProgressPath -Data @{
        run_id = [string]$Config.RunId
        status = 'starting'
        phase = 'preflight'
        current_lane = ''
        current_step_id = ''
        current_step_name = ''
        completed_steps = 0
        total_steps = 6
        started_at = (Get-Date).ToUniversalTime().ToString('o')
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
        last_completed_step_id = ''
        real_e2e_status = 'pending'
    }
    Write-WebnovelMultiAgentJson -Path $Config.ControlPath -Data @{
        stop_requested = $false
        requested_at = ''
    }
}

function Write-WebnovelMultiAgentJson {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        $Data
    )

    $parentDir = Split-Path -Path $Path -Parent
    if (-not [string]::IsNullOrWhiteSpace($parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    $Data | ConvertTo-Json -Depth 16 | Set-Content -Path $Path -Encoding UTF8
}

function Write-WebnovelMultiAgentProgress {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [Parameter(Mandatory = $true)]
        [string]$Phase,
        [string]$Status = 'running',
        [string]$CurrentLane = '',
        [string]$CurrentStepId = '',
        [string]$CurrentStepName = '',
        [int]$CompletedSteps = 0,
        [int]$TotalSteps = 6,
        [string]$LastCompletedStepId = '',
        [string]$RealE2EStatus = 'pending'
    )

    $existing = if (Test-Path $Config.ProgressPath) {
        try { Get-Content -Path $Config.ProgressPath -Raw | ConvertFrom-Json } catch { $null }
    } else {
        $null
    }
    $startedAt = if ($existing -and $existing.started_at) { [string]$existing.started_at } else { (Get-Date).ToUniversalTime().ToString('o') }
    Write-WebnovelMultiAgentJson -Path $Config.ProgressPath -Data @{
        run_id = [string]$Config.RunId
        status = $Status
        phase = $Phase
        current_lane = $CurrentLane
        current_step_id = $CurrentStepId
        current_step_name = $CurrentStepName
        completed_steps = $CompletedSteps
        total_steps = $TotalSteps
        started_at = $startedAt
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
        last_completed_step_id = $LastCompletedStepId
        real_e2e_status = $RealE2EStatus
    }
}

function Get-WebnovelMultiAgentControlState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    if (-not (Test-Path $Config.ControlPath)) {
        return [pscustomobject]@{ stop_requested = $false; requested_at = '' }
    }
    try {
        return Get-Content -Path $Config.ControlPath -Raw | ConvertFrom-Json
    } catch {
        return [pscustomobject]@{ stop_requested = $false; requested_at = '' }
    }
}

function Test-WebnovelMultiAgentStopRequested {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    $control = Get-WebnovelMultiAgentControlState -Config $Config
    return ($control -and $control.stop_requested -eq $true)
}

function Get-WebnovelMultiAgentFailureFingerprint {
    [CmdletBinding()]
    param(
        [string]$Classification = '',
        [psobject]$Preflight,
        [object[]]$LaneResults = @(),
        [psobject]$RealE2EStatus
    )

    if ($Classification -eq 'cancelled') {
        return 'cancelled'
    }
    if ($Classification -eq 'environment_blocked') {
        $issueNames = @($Preflight.issues | ForEach-Object { [string]$_.name } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        if ($issueNames.Count -gt 0) {
            return ('environment:{0}' -f (($issueNames | Sort-Object -Unique) -join '|'))
        }
    }
    if ($Classification -in @('local_blocker', 'local_regression')) {
        foreach ($lane in @($LaneResults)) {
            foreach ($step in @($lane.steps)) {
                if (-not $step.passed) {
                    return ('{0}:{1}' -f [string]$step.id, [string]$step.failure_kind)
                }
            }
        }
    }
    if ($Classification -in @('mainline_failure', 'page_regression', 'readonly_audit_failure')) {
        $reason = if ($RealE2EStatus) { [string]$RealE2EStatus.reason } else { '' }
        if (-not [string]::IsNullOrWhiteSpace($reason)) {
            return ('{0}:{1}' -f $Classification, $reason)
        }
        return $Classification
    }
    if ($Classification -eq 'pass') {
        return 'pass'
    }
    return $Classification
}

function Write-WebnovelMultiAgentManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,
        [Parameter(Mandatory = $true)]
        [hashtable]$Result
    )

    Write-WebnovelMultiAgentJson -Path $Config.ManifestPath -Data @{
        manifest_version = 1
        run_id = [string]$Config.RunId
        classification = [string]$Result.classification
        next_action = [string]$Result.next_action
        failure_fingerprint = [string]$Result.failure_fingerprint
        rerun_of_run_id = [string]$Result.rerun_of_run_id
        artifact_paths = @{
            result = [string]$Config.ResultPath
            report = [string]$Config.ReportPath
            progress = [string]$Config.ProgressPath
            manifest = [string]$Config.ManifestPath
        }
    }
}

function Invoke-WebnovelMultiAgentProbeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory
    )

    $previousLocation = $null
    $output = ''
    $exitCode = 0

    try {
        if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
            $previousLocation = Get-Location
            Set-Location $WorkingDirectory
        }

        $global:LASTEXITCODE = 0
        $output = ((& $FilePath @Arguments 2>&1) | Out-String)
        $exitCode = if ($null -ne $global:LASTEXITCODE) { [int]$global:LASTEXITCODE } else { 0 }
    } catch {
        $exitCode = -1
        $output = ($_ | Out-String)
    } finally {
        if ($null -ne $previousLocation) {
            Set-Location $previousLocation
        }
    }

    [pscustomobject]@{
        ok = ($exitCode -eq 0)
        exit_code = $exitCode
        output = ($output.Trim())
    }
}

function Test-WebnovelMultiAgentPreflight {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    $checks = @()
    $issues = @()
    $missingPaths = @()
    $failedCommands = @()

    foreach ($toolName in @('python', 'node', 'npm', 'npx')) {
        $command = Get-Command $toolName -ErrorAction SilentlyContinue
        $check = [pscustomobject]@{
            kind = 'command_presence'
            name = $toolName
            status = $(if ($command) { 'pass' } else { 'fail' })
            detail = $(if ($command) { "$toolName is available." } else { "$toolName is not available in the current PowerShell session." })
        }
        $checks += $check
        if (-not $command) {
            $issues += [pscustomobject]@{
                kind = 'missing_tool'
                name = $toolName
                detail = $check.detail
            }
        }
    }

    foreach ($pathCheck in @(
        @{ name = 'real_e2e_module'; path = $Config.RealE2EModulePath },
        @{ name = 'playwright_script'; path = $Config.PlaywrightScriptPath },
        @{ name = 'frontend_node_modules'; path = $Config.NodeModulesPath }
    )) {
        $exists = Test-Path $pathCheck.path
        $check = [pscustomobject]@{
            kind = 'path_presence'
            name = $pathCheck.name
            path = $pathCheck.path
            status = $(if ($exists) { 'pass' } else { 'fail' })
            detail = $(if ($exists) { "Found: $($pathCheck.path)" } else { "Missing required path: $($pathCheck.path)" })
        }
        $checks += $check
        if (-not $exists) {
            $missingRecord = [pscustomobject]@{
                kind = 'missing_path'
                name = $pathCheck.name
                path = $pathCheck.path
                detail = $check.detail
            }
            $missingPaths += $missingRecord
            $issues += $missingRecord
        }
    }

    foreach ($probe in @(
        @{ name = 'python-pytest-version'; file_path = 'python'; arguments = @('-m', 'pytest', '--version') },
        @{ name = 'node-version'; file_path = 'node'; arguments = @('--version') },
        @{ name = 'npm-version'; file_path = 'npm'; arguments = @('--version') },
        @{ name = 'npx-version'; file_path = 'npx'; arguments = @('--version') }
    )) {
        $probeResult = Invoke-WebnovelMultiAgentProbeCommand -FilePath $probe.file_path -Arguments $probe.arguments -WorkingDirectory $Config.WorkspaceRoot
        $check = [pscustomobject]@{
            kind = 'command_probe'
            name = $probe.name
            command = @($probe.file_path) + @($probe.arguments)
            status = $(if ($probeResult.ok) { 'pass' } else { 'fail' })
            exit_code = $probeResult.exit_code
            output = $probeResult.output
            detail = $(if ($probeResult.ok) { 'Probe succeeded.' } else { 'Probe failed.' })
        }
        $checks += $check
        if (-not $probeResult.ok) {
            $failedRecord = [pscustomobject]@{
                kind = 'failed_command'
                name = $probe.name
                command = @($probe.file_path) + @($probe.arguments)
                exit_code = $probeResult.exit_code
                output = $probeResult.output
                detail = 'Probe failed.'
            }
            $failedCommands += $failedRecord
            $issues += $failedRecord
        }
    }

    [pscustomobject]@{
        classification = $(if ($issues.Count -gt 0) { 'environment_blocked' } else { 'pass' })
        ready = ($issues.Count -eq 0)
        checked_at = (Get-Date).ToUniversalTime().ToString('o')
        checks = @($checks)
        issues = @($issues)
        missing_paths = @($missingPaths)
        failed_commands = @($failedCommands)
    }
}

function Get-WebnovelMultiAgentLaneSpecs {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    $scriptRoot = Join-Path $Config.AppRoot 'scripts'
    $frontendRoot = $Config.FrontendRoot

    @(
        [pscustomobject]@{
            name = 'backend'
            artifact_path = $Config.BackendLanePath
            commands = @(
                @{
                    id = 'backend.dashboard-root-contract'
                    name = 'dashboard-root-contract'
                    workdir = $Config.WorkspaceRoot
                    file_path = 'python'
                    arguments = @('-m', 'pytest', 'webnovel-writer\webnovel-writer\dashboard\tests\test_app.py', '-q')
                    environment = @{}
                    blocking_severity = 'blocking'
                    timeout_seconds = 600
                },
                @{
                    id = 'backend.dashboard-package-contract'
                    name = 'dashboard-package-contract'
                    workdir = $Config.AppRoot
                    file_path = 'python'
                    arguments = @('-m', 'pytest', 'dashboard\tests\test_app.py', 'dashboard\tests\test_orchestrator.py', 'dashboard\tests\test_task_store.py', '-q')
                    environment = @{}
                    blocking_severity = 'blocking'
                    timeout_seconds = 900
                }
            )
        },
        [pscustomobject]@{
            name = 'data-cli'
            artifact_path = $Config.DataCliLanePath
            commands = @(
                @{
                    id = 'data-cli.state-and-cli-contracts'
                    name = 'state-and-cli-contracts'
                    workdir = $Config.AppRoot
                    file_path = 'python'
                    arguments = @('-m', 'pytest', 'scripts\data_modules\tests\test_state_file.py', 'scripts\data_modules\tests\test_state_manager_extra.py', 'scripts\data_modules\tests\test_sql_state_manager.py', 'scripts\data_modules\tests\test_webnovel_unified_cli.py', '-q')
                    environment = @{ PYTHONPATH = $scriptRoot }
                    blocking_severity = 'blocking'
                    timeout_seconds = 900
                },
                @{
                    id = 'data-cli.mock-cli-e2e'
                    name = 'mock-cli-e2e'
                    workdir = $Config.AppRoot
                    file_path = 'python'
                    arguments = @('-m', 'pytest', 'scripts\data_modules\tests\test_webnovel_cli_e2e_mock.py', '-q')
                    environment = @{ PYTHONPATH = $scriptRoot }
                    blocking_severity = 'non_blocking'
                    timeout_seconds = 600
                }
            )
        },
        [pscustomobject]@{
            name = 'frontend'
            artifact_path = $Config.FrontendLanePath
            commands = @(
                @{
                    id = 'frontend.frontend-tests'
                    name = 'frontend-tests'
                    workdir = $frontendRoot
                    file_path = 'npm'
                    arguments = @('test')
                    environment = @{}
                    blocking_severity = 'blocking'
                    timeout_seconds = 900
                },
                @{
                    id = 'frontend.frontend-typecheck'
                    name = 'frontend-typecheck'
                    workdir = $frontendRoot
                    file_path = 'npm'
                    arguments = @('run', 'typecheck')
                    environment = @{}
                    blocking_severity = 'non_blocking'
                    timeout_seconds = 600
                }
            )
        }
    )
}

function Invoke-WebnovelMultiAgentLaneCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LaneName,
        [Parameter(Mandatory = $true)]
        [hashtable]$CommandSpec,
        [Parameter(Mandatory = $true)]
        [string]$LaneLogsDir
    )

    New-Item -ItemType Directory -Path $LaneLogsDir -Force | Out-Null

    $stepBaseName = '{0}-{1}' -f $LaneName, [string]$CommandSpec.name
    $stdoutPath = Join-Path $LaneLogsDir ($stepBaseName + '-stdout.log')
    $stderrPath = Join-Path $LaneLogsDir ($stepBaseName + '-stderr.log')
    $combinedPath = Join-Path $LaneLogsDir ($stepBaseName + '-combined.log')
    $timeoutSeconds = [int]$CommandSpec.timeout_seconds
    $startedAt = Get-Date

    $previousValues = @{}
    foreach ($entry in @($CommandSpec.environment.GetEnumerator())) {
        $key = [string]$entry.Key
        $previousValues[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, [string]$entry.Value, 'Process')
    }

    $process = $null
    $timedOut = $false
    $exitCode = 0
    $stdoutText = ''
    $stderrText = ''

    try {
        $process = Start-Process `
            -FilePath $CommandSpec.file_path `
            -ArgumentList @($CommandSpec.arguments) `
            -WorkingDirectory $CommandSpec.workdir `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -NoNewWindow `
            -PassThru

        try {
            Wait-Process -Id $process.Id -Timeout $timeoutSeconds -ErrorAction Stop
        } catch [System.TimeoutException] {
            $timedOut = $true
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }

        if ($timedOut) {
            $exitCode = -1
        } else {
            try {
                $process.Refresh()
            } catch {
            }
            if ($process.PSObject.Properties.Name -contains 'ExitCode') {
                $exitCode = [int]$process.ExitCode
            } else {
                $exitCode = 0
            }
        }
    } catch {
        $exitCode = -1
        $stderrText = ($_ | Out-String)
        Set-Content -Path $stderrPath -Value $stderrText -Encoding UTF8
    } finally {
        foreach ($entry in @($CommandSpec.environment.GetEnumerator())) {
            $key = [string]$entry.Key
            [Environment]::SetEnvironmentVariable($key, $previousValues[$key], 'Process')
        }
    }

    if ((Test-Path $stdoutPath) -and [string]::IsNullOrWhiteSpace($stdoutText)) {
        $stdoutText = (Get-Content -Path $stdoutPath -Raw)
    }
    if ((Test-Path $stderrPath) -and [string]::IsNullOrWhiteSpace($stderrText)) {
        $stderrText = (Get-Content -Path $stderrPath -Raw)
    }

    $combinedText = (@(
        $stdoutText.TrimEnd()
        $stderrText.TrimEnd()
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join [Environment]::NewLine
    Set-Content -Path $combinedPath -Value $combinedText -Encoding UTF8

    $finishedAt = Get-Date
    $failureKind = Get-WebnovelMultiAgentFailureKind `
        -ExitCode $exitCode `
        -TimedOut:$timedOut `
        -StdoutText $stdoutText `
        -StderrText $stderrText

    [pscustomobject]@{
        id = [string]$CommandSpec.id
        name = [string]$CommandSpec.name
        workdir = [string]$CommandSpec.workdir
        file_path = [string]$CommandSpec.file_path
        arguments = @($CommandSpec.arguments)
        exit_code = $exitCode
        passed = ($exitCode -eq 0 -and -not $timedOut)
        started_at = $startedAt.ToUniversalTime().ToString('o')
        finished_at = $finishedAt.ToUniversalTime().ToString('o')
        duration_seconds = [Math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)
        excerpt = Get-WebnovelMultiAgentOutputExcerpt -Text $combinedText
        timeout_seconds = $timeoutSeconds
        timed_out = $timedOut
        failure_kind = $failureKind
        blocking_severity = [string]$CommandSpec.blocking_severity
        stdout_log_path = $stdoutPath
        stderr_log_path = $stderrPath
        combined_log_path = $combinedPath
    }
}

function Get-WebnovelMultiAgentLaneRecommendedAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$LaneResult
    )

    if ($LaneResult.status -eq 'passed') {
        return 'no_action'
    }

    $failedSteps = @($LaneResult.steps | Where-Object { -not $_.passed })
    if (@($failedSteps | Where-Object { $_.failure_kind -eq 'environment' }).Count -gt 0) {
        return 'fix_environment_first'
    }
    if (@($failedSteps | Where-Object { $_.blocking_severity -eq 'blocking' }).Count -gt 0) {
        return ('fix_{0}_first' -f [string]$LaneResult.name.Replace('-', '_'))
    }
    if ($failedSteps.Count -gt 0) {
        return 'fix_non_blocking_failures'
    }

    return 'inspect_lane_logs'
}

function Invoke-WebnovelMultiAgentLocalLanes {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    $modulePath = Join-Path $Config.WorkspaceRoot 'tools\Webnovel-MultiAgentTest.psm1'
    $laneJobs = @()
    foreach ($lane in @(Get-WebnovelMultiAgentLaneSpecs -Config $Config)) {
        $laneJobs += Start-Job -ArgumentList @($modulePath, $lane, $Config.LaneLogsDir) -ScriptBlock {
            param($ModulePath, $Lane, $LaneLogsDir)

            $ErrorActionPreference = 'Stop'
            Import-Module $ModulePath -Force

            $stepResults = @()
            foreach ($commandSpec in @($Lane.commands)) {
                $stepResults += Invoke-WebnovelMultiAgentLaneCommand -LaneName $Lane.name -CommandSpec $commandSpec -LaneLogsDir $LaneLogsDir
            }

            [pscustomobject]@{
                name = [string]$Lane.name
                steps = $stepResults
                artifact_path = [string]$Lane.artifact_path
            }
        }
    }

    $laneResults = @()
    foreach ($job in @($laneJobs)) {
        $laneExecution = Receive-Job -Job (Wait-Job -Job $job) -ErrorAction Stop
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue | Out-Null

        $failedSteps = @($laneExecution.steps | Where-Object { -not $_.passed })
        $laneResult = [pscustomobject]@{
            name = [string]$laneExecution.name
            status = $(if ($failedSteps.Count -eq 0) { 'passed' } else { 'failed' })
            failed_step_count = $failedSteps.Count
            suspected_environment_issue = (@($failedSteps | Where-Object { $_.failure_kind -eq 'environment' }).Count -gt 0)
            failed_step_names = @($failedSteps | ForEach-Object { [string]$_.name })
            blocking_step_names = @($failedSteps | Where-Object { $_.blocking_severity -eq 'blocking' } | ForEach-Object { [string]$_.name })
            steps = @($laneExecution.steps)
            recommended_action = ''
        }
        $laneResult.recommended_action = Get-WebnovelMultiAgentLaneRecommendedAction -LaneResult $laneResult

        Write-WebnovelMultiAgentJson -Path $laneExecution.artifact_path -Data $laneResult
        $laneResults += $laneResult
    }

    return ,$laneResults
}

function Get-WebnovelMultiAgentOutputExcerpt {
    [CmdletBinding()]
    param(
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ''
    }

    $trimmed = $Text.Trim()
    if ($trimmed.Length -le 1200) {
        return $trimmed
    }

    return ($trimmed.Substring(0, 1200) + '...')
}

function Get-WebnovelMultiAgentFailureKind {
    [CmdletBinding()]
    param(
        [int]$ExitCode,
        [bool]$TimedOut,
        [string]$StdoutText,
        [string]$StderrText
    )

    if ($TimedOut) {
        return 'timeout'
    }

    if ($ExitCode -eq 0) {
        return 'pass'
    }

    $combined = @($StdoutText, $StderrText) -join [Environment]::NewLine
    foreach ($pattern in @(
        'ERROR collecting',
        'ModuleNotFoundError',
        'ImportError',
        'Cannot find module',
        'Missing script',
        'ENOENT',
        'not recognized as',
        'No module named',
        'The system cannot find the file specified',
        'could not find',
        'pytest missing'
    )) {
        if ($combined -match $pattern) {
            return 'environment'
        }
    }

    foreach ($pattern in @(
        'AssertionError',
        'FAILED ',
        ' failed',
        'Test Suites: .* failed',
        'Tests: .* failed',
        'Expected:',
        'not ok'
    )) {
        if ($combined -match $pattern) {
            return 'test_failure'
        }
    }

    return 'tooling_failure'
}

function Get-WebnovelMultiAgentLaneDecision {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$LaneResults
    )

    $failedSteps = @()
    foreach ($lane in @($LaneResults)) {
        foreach ($step in @($lane.steps)) {
            if (-not $step.passed) {
                $failedSteps += [pscustomobject]@{
                    lane_name = [string]$lane.name
                    step_id = [string]$step.id
                    step_name = [string]$step.name
                    failure_kind = [string]$step.failure_kind
                    blocking_severity = [string]$step.blocking_severity
                }
            }
        }
    }

    $environmentSteps = @($failedSteps | Where-Object { $_.failure_kind -eq 'environment' })
    if ($environmentSteps.Count -gt 0) {
        return [pscustomobject]@{
            should_run_real_e2e = $false
            classification = 'environment_blocked'
            blocking_lane_names = @($environmentSteps | ForEach-Object { $_.lane_name } | Select-Object -Unique)
            blocking_step_ids = @($environmentSteps | ForEach-Object { $_.step_id } | Select-Object -Unique)
            reason = 'environment_failure_detected'
        }
    }

    $blockingSteps = @($failedSteps | Where-Object { $_.blocking_severity -eq 'blocking' })
    if ($blockingSteps.Count -gt 0) {
        return [pscustomobject]@{
            should_run_real_e2e = $false
            classification = 'local_blocker'
            blocking_lane_names = @($blockingSteps | ForEach-Object { $_.lane_name } | Select-Object -Unique)
            blocking_step_ids = @($blockingSteps | ForEach-Object { $_.step_id } | Select-Object -Unique)
            reason = 'blocking_steps_failed'
        }
    }

    if ($failedSteps.Count -gt 0) {
        return [pscustomobject]@{
            should_run_real_e2e = $true
            classification = 'local_regression'
            blocking_lane_names = @()
            blocking_step_ids = @()
            reason = 'only_non_blocking_steps_failed'
        }
    }

    [pscustomobject]@{
        should_run_real_e2e = $true
        classification = 'pass'
        blocking_lane_names = @()
        blocking_step_ids = @()
        reason = 'all_local_lanes_passed'
    }
}

function Get-WebnovelMultiAgentFinalClassification {
    [CmdletBinding()]
    param(
        [string]$PreflightClassification = 'pass',
        [string]$LocalClassification = 'pass',
        [string]$RealE2EClassification = ''
    )

    if ($PreflightClassification -eq 'environment_blocked') {
        return 'environment_blocked'
    }
    if ($LocalClassification -eq 'cancelled') {
        return 'cancelled'
    }
    if ($LocalClassification -eq 'environment_blocked') {
        return 'environment_blocked'
    }
    if (-not [string]::IsNullOrWhiteSpace($RealE2EClassification) -and $RealE2EClassification -ne 'pass') {
        return $RealE2EClassification
    }
    if ($LocalClassification -eq 'local_blocker') {
        return 'local_blocker'
    }
    if ($LocalClassification -eq 'local_regression') {
        return 'local_regression'
    }
    return 'pass'
}

function Get-WebnovelMultiAgentNextAction {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Classification,
        [string]$RealE2EClassification = ''
    )

    switch ($Classification) {
        'cancelled' { return 'rerun_after_cancel' }
        'environment_blocked' { return 'fix_environment_first' }
        'local_blocker' { return 'fix_local_blocker_and_rerun' }
        'local_regression' {
            if ($RealE2EClassification -eq 'pass') {
                return 'fix_non_blocking_local_regressions'
            }
            return 'inspect_local_regressions'
        }
        'mainline_failure' { return 'repair_mainline_product_flow' }
        'page_regression' { return 'repair_regressed_pages' }
        'readonly_audit_failure' { return 'repair_readonly_audit_failures' }
        default { return 'ready_to_pass' }
    }
}

function Get-WebnovelMultiAgentFailureSummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Classification,
        [psobject]$Preflight,
        [object[]]$LaneResults = @(),
        [string[]]$BlockingStepIds = @()
    )

    switch ($Classification) {
        'cancelled' { return 'Verification was cancelled before completion.' }
        'environment_blocked' {
            $issueNames = @($Preflight.issues | ForEach-Object { [string]$_.name })
            if ($issueNames.Count -gt 0) {
                return ('Environment blocked by: {0}' -f ($issueNames -join ', '))
            }
            return ('Environment blocked by local step(s): {0}' -f (@($BlockingStepIds) -join ', '))
        }
        'local_blocker' {
            return ('Blocking local step(s) failed: {0}' -f (@($BlockingStepIds) -join ', '))
        }
        'local_regression' {
            $failedNames = @()
            foreach ($lane in @($LaneResults)) {
                $failedNames += @($lane.failed_step_names)
            }
            return ('Only non-blocking local regressions remain: {0}' -f ($failedNames -join ', '))
        }
        'mainline_failure' { return 'RealE2E mainline flow failed.' }
        'page_regression' { return 'RealE2E detected a page-level regression.' }
        'readonly_audit_failure' { return 'Readonly audit failed after RealE2E.' }
        default { return 'All preflight, local lane, and RealE2E checks passed.' }
    }
}

function Convert-WebnovelMultiAgentActionText {
    [CmdletBinding()]
    param(
        [string]$ActionCode
    )

    switch ($ActionCode) {
        'rerun_after_cancel' { return 'rerun_after_cancel (本次验证已取消，可直接重跑)' }
        'fix_environment_first' { return 'fix_environment_first (先修环境)' }
        'fix_local_blocker_and_rerun' { return 'fix_local_blocker_and_rerun (先修本地阻断 step，再重跑协调器)' }
        'fix_non_blocking_local_regressions' { return 'fix_non_blocking_local_regressions (局部回归，优先修非阻断 lane)' }
        'repair_mainline_product_flow' { return 'repair_mainline_product_flow (按主链失败进入产品修复)' }
        'repair_regressed_pages' { return 'repair_regressed_pages (按页面回归进入产品修复)' }
        'repair_readonly_audit_failures' { return 'repair_readonly_audit_failures (按只读审计失败进入产品修复)' }
        'ready_to_pass' { return 'ready_to_pass (当前可视为通过)' }
        default { return $ActionCode }
    }
}

function New-WebnovelMultiAgentReport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Result
    )

    $lines = @(
        '# Multi-Agent Test Report',
        '',
        ('- Classification: `{0}`' -f [string]$Result.classification),
        ('- Passed: `{0}`' -f $(if ($Result.passed) { 'yes' } else { 'no' })),
        ('- Workspace Root: `{0}`' -f [string]$Result.workspace_root),
        ('- Artifact Dir: `{0}`' -f [string]$Result.artifact_dir),
        ''
    )

    $preflight = $Result.preflight
    $lines += '## Preflight'
    $lines += ('- Ready: `{0}`' -f $(if ($preflight.ready) { 'yes' } else { 'no' }))
    if (@($preflight.issues).Count -gt 0) {
        foreach ($issue in @($preflight.issues)) {
            $lines += ('- {0}: {1}' -f [string]$issue.name, [string]$issue.detail)
        }
    } else {
        $lines += '- No environment blockers detected before running lanes.'
    }

    $lines += ''
    $lines += '## Local Lanes'
    foreach ($lane in @($Result.lanes)) {
        $lines += ('- {0}: `{1}` ({2} failed step(s))' -f [string]$lane.name, [string]$lane.status, [int]$lane.failed_step_count)
        if ($lane.suspected_environment_issue) {
            $lines += '  suspected environment issue: yes'
        }
        $laneSteps = if ($lane.PSObject -and $lane.PSObject.Properties.Name -contains 'steps') { @($lane.steps) } else { @() }
        $firstFailed = @($laneSteps | Where-Object { -not $_.passed } | Select-Object -First 1)
        if ($firstFailed.Count -gt 0) {
            $step = $firstFailed[0]
            $logPath = if ($step.PSObject.Properties.Name -contains 'combined_log_path') { [string]$step.combined_log_path } elseif ($step.PSObject.Properties.Name -contains 'log_path') { [string]$step.log_path } else { '' }
            $failureKind = if ($step.PSObject.Properties.Name -contains 'failure_kind') { [string]$step.failure_kind } else { 'unknown' }
            $blockingSeverity = if ($step.PSObject.Properties.Name -contains 'blocking_severity') { [string]$step.blocking_severity } else { 'unknown' }
            $lines += ('  first failed step `{0}` kind `{1}` blocking `{2}` log `{3}`' -f [string]$step.name, $failureKind, $blockingSeverity, $logPath)
        }
        if ($lane.PSObject.Properties.Name -contains 'recommended_action' -and -not [string]::IsNullOrWhiteSpace([string]$lane.recommended_action)) {
            $lines += ('  action `{0}`' -f [string]$lane.recommended_action)
        }
    }

    $lines += ''
    $lines += '## RealE2E'
    $realE2E = $Result.real_e2e
    $lines += ('- Status: `{0}`' -f [string]$realE2E.status)
    if (-not [string]::IsNullOrWhiteSpace([string]$realE2E.classification)) {
        $lines += ('- Classification: `{0}`' -f [string]$realE2E.classification)
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$realE2E.artifact_dir)) {
        $lines += ('- Artifact Dir: `{0}`' -f [string]$realE2E.artifact_dir)
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$realE2E.reason)) {
        $lines += ('- Reason: {0}' -f [string]$realE2E.reason)
    }

    $lines += ''
    $lines += '## Verdict'
    $lines += ('- Final status: `{0}`' -f [string]$Result.classification)
    if ($Result.ContainsKey('next_action')) {
        $lines += ('- Next action: `{0}`' -f [string]$Result.next_action)
    }
    if ($Result.ContainsKey('failure_summary')) {
        $lines += ('- Failure summary: {0}' -f [string]$Result.failure_summary)
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$Result.minimal_repro)) {
        $lines += ('- Minimal repro: {0}' -f [string]$Result.minimal_repro)
    }

    return ($lines -join [Environment]::NewLine)
}

function Invoke-WebnovelMultiAgentRealE2E {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    Import-Module $Config.RealE2EModulePath -Force
    $realE2EConfig = Get-WebnovelRealE2EConfig `
        -WorkspaceRoot $Config.WorkspaceRoot `
        -OutputRoot $Config.RealE2EOutputRoot `
        -PreferredPort $Config.PreferredPort `
        -ProjectRoot $Config.ProjectRoot `
        -RunId $Config.RunId `
        -Title $Config.Title `
        -Genre $Config.Genre
    Invoke-WebnovelRealE2E -Config $realE2EConfig
}

function Invoke-WebnovelMultiAgentTest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    Initialize-WebnovelMultiAgentTestArtifacts -Config $Config
    Write-WebnovelMultiAgentProgress -Config $Config -Phase 'preflight' -Status 'running' -CompletedSteps 0 -TotalSteps 6 -RealE2EStatus 'pending'

    $preflight = Test-WebnovelMultiAgentPreflight -Config $Config
    Write-WebnovelMultiAgentJson -Path $Config.PreflightPath -Data $preflight

    $laneResults = @()
    $localDecision = [pscustomobject]@{
        should_run_real_e2e = $false
        classification = 'pass'
        blocking_lane_names = @()
        blocking_step_ids = @()
        reason = 'preflight_not_started'
    }
    $rerunOfRunId = ''
    $requestPath = Join-Path $Config.ArtifactDir 'request.json'
    if (Test-Path $requestPath) {
        try {
            $requestPayload = Get-Content -Path $requestPath -Raw | ConvertFrom-Json
            $rerunOfRunId = [string]$requestPayload.rerun_of_run_id
        } catch {
            $rerunOfRunId = ''
        }
    }
    $realE2EStatus = [pscustomobject]@{
        status = 'skipped'
        classification = ''
        artifact_dir = ''
        reason = ''
    }
    $minimalRepro = ''
    $totalSteps = 6

    if (Test-WebnovelMultiAgentStopRequested -Config $Config) {
        $localDecision = [pscustomobject]@{
            should_run_real_e2e = $false
            classification = 'cancelled'
            blocking_lane_names = @()
            blocking_step_ids = @()
            reason = 'stop_requested_before_lanes'
        }
        $realE2EStatus = [pscustomobject]@{
            status = 'skipped_due_to_cancel'
            classification = ''
            artifact_dir = ''
            reason = 'Verification was cancelled before local lanes started.'
        }
        $minimalRepro = 'Rerun the coordinator after cancellation.'
    } elseif ($preflight.ready) {
        Write-WebnovelMultiAgentProgress -Config $Config -Phase 'local_lanes' -Status 'running' -CurrentLane 'parallel' -CompletedSteps 0 -TotalSteps $totalSteps -RealE2EStatus 'pending'
        $laneResults = @(Invoke-WebnovelMultiAgentLocalLanes -Config $Config)
        if (Test-WebnovelMultiAgentStopRequested -Config $Config) {
            $localDecision = [pscustomobject]@{
                should_run_real_e2e = $false
                classification = 'cancelled'
                blocking_lane_names = @()
                blocking_step_ids = @()
                reason = 'stop_requested_after_local_lanes'
            }
            $realE2EStatus = [pscustomobject]@{
                status = 'skipped_due_to_cancel'
                classification = ''
                artifact_dir = ''
                reason = 'Verification was cancelled after local lanes completed.'
            }
            $minimalRepro = 'Rerun the coordinator after cancellation.'
        } else {
            $localDecision = Get-WebnovelMultiAgentLaneDecision -LaneResults $laneResults
        }
    } else {
        $localDecision = [pscustomobject]@{
            should_run_real_e2e = $false
            classification = 'environment_blocked'
            blocking_lane_names = @()
            blocking_step_ids = @()
            reason = 'preflight_failed'
        }
        $minimalRepro = 'Preflight did not pass; see preflight.json for missing tools or paths.'
    }

    if ($localDecision.should_run_real_e2e) {
        Write-WebnovelMultiAgentProgress -Config $Config -Phase 'real_e2e' -Status 'running' -CompletedSteps $totalSteps -TotalSteps $totalSteps -RealE2EStatus 'running'
        $realE2EResult = Invoke-WebnovelMultiAgentRealE2E -Config $Config
        Write-WebnovelMultiAgentJson -Path $Config.RealE2EResultPath -Data $realE2EResult
        $realE2EStatus = @{
            status = 'executed'
            classification = [string]$realE2EResult.classification
            artifact_dir = [string]$realE2EResult.artifact_dir
            reason = ''
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$realE2EResult.minimal_repro)) {
            $minimalRepro = [string]$realE2EResult.minimal_repro
        }
    } else {
        $skipReason = switch ($localDecision.classification) {
            'cancelled' { 'Verification was cancelled before RealE2E started.' }
            'environment_blocked' { 'Local preflight or lane execution exposed an environment blocker.' }
            'local_blocker' { 'Blocking local steps failed, so RealE2E was skipped.' }
            default { 'RealE2E was skipped by coordinator policy.' }
        }
        Write-WebnovelMultiAgentJson -Path $Config.RealE2EResultPath -Data @{
            skipped = $true
            reason = $skipReason
        }
        if ($localDecision.classification -eq 'cancelled') {
            $realE2EStatus = @{
                status = 'skipped_due_to_cancel'
                classification = ''
                artifact_dir = ''
                reason = $skipReason
            }
        } else {
            $realE2EStatus.reason = $skipReason
        }
        if ([string]::IsNullOrWhiteSpace($minimalRepro)) {
            $minimalRepro = $skipReason
        }
    }

    $realE2EClassification = if ($realE2EStatus.status -eq 'executed') { [string]$realE2EStatus.classification } else { '' }
    $classification = Get-WebnovelMultiAgentFinalClassification `
        -PreflightClassification ([string]$preflight.classification) `
        -LocalClassification ([string]$localDecision.classification) `
        -RealE2EClassification $realE2EClassification

    $nextAction = Get-WebnovelMultiAgentNextAction `
        -Classification $classification `
        -RealE2EClassification $realE2EClassification
    $failureSummary = Get-WebnovelMultiAgentFailureSummary `
        -Classification $classification `
        -Preflight $preflight `
        -LaneResults $laneResults `
        -BlockingStepIds @($localDecision.blocking_step_ids)

    if ([string]::IsNullOrWhiteSpace($minimalRepro) -and $classification -eq 'local_regression') {
        $minimalRepro = 'At least one local verification lane failed, but RealE2E remained eligible and did not report a broader blocker.'
    }
    if ([string]::IsNullOrWhiteSpace($minimalRepro) -and $classification -eq 'cancelled') {
        $minimalRepro = 'Rerun the coordinator after cancellation.'
    }

    $failureFingerprint = Get-WebnovelMultiAgentFailureFingerprint `
        -Classification $classification `
        -Preflight $preflight `
        -LaneResults $laneResults `
        -RealE2EStatus $realE2EStatus

    $result = @{
        classification = $classification
        passed = ($classification -eq 'pass')
        workspace_root = $Config.WorkspaceRoot
        artifact_dir = $Config.ArtifactDir
        preflight = $preflight
        lanes = $laneResults
        local_decision = $localDecision
        real_e2e = $realE2EStatus
        blocking_step_ids = @($localDecision.blocking_step_ids)
        next_action = $nextAction
        failure_summary = $failureSummary
        minimal_repro = $minimalRepro
        failure_fingerprint = $failureFingerprint
        rerun_of_run_id = $rerunOfRunId
    }
    Write-WebnovelMultiAgentJson -Path $Config.ResultPath -Data $result
    Write-WebnovelMultiAgentProgress -Config $Config -Phase 'finalizing' -Status 'completed' -CompletedSteps $totalSteps -TotalSteps $totalSteps -LastCompletedStepId '' -RealE2EStatus ([string]$realE2EStatus.status)
    Write-WebnovelMultiAgentManifest -Config $Config -Result $result
    $report = New-WebnovelMultiAgentReport -Result $result
    Set-Content -Path $Config.ReportPath -Value $report -Encoding UTF8

    return [pscustomobject]$result
}

Export-ModuleMember -Function `
    Get-WebnovelMultiAgentTestConfig, `
    Initialize-WebnovelMultiAgentTestArtifacts, `
    Write-WebnovelMultiAgentProgress, `
    Get-WebnovelMultiAgentControlState, `
    Test-WebnovelMultiAgentStopRequested, `
    Get-WebnovelMultiAgentFailureFingerprint, `
    Write-WebnovelMultiAgentManifest, `
    Invoke-WebnovelMultiAgentProbeCommand, `
    Test-WebnovelMultiAgentPreflight, `
    Get-WebnovelMultiAgentLaneSpecs, `
    Invoke-WebnovelMultiAgentLaneCommand, `
    Invoke-WebnovelMultiAgentLocalLanes, `
    Get-WebnovelMultiAgentFailureKind, `
    Get-WebnovelMultiAgentLaneDecision, `
    Get-WebnovelMultiAgentFinalClassification, `
    Invoke-WebnovelMultiAgentRealE2E, `
    Invoke-WebnovelMultiAgentTest
