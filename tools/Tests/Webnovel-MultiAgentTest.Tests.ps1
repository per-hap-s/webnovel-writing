Import-Module Pester

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-MultiAgentTest.psm1'

Describe 'Get-WebnovelMultiAgentTestConfig' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'builds the standard artifact paths and nested RealE2E output root' {
        $config = Get-WebnovelMultiAgentTestConfig `
            -WorkspaceRoot 'D:\CodexProjects\Project1' `
            -OutputRoot 'D:\CodexProjects\Project1\output\verification\multi-agent-test\manual-run' `
            -PreferredPort 8765 `
            -RunId 'manual01'

        $config.WorkspaceRoot | Should Be 'D:\CodexProjects\Project1'
        $config.ArtifactDir | Should Be 'D:\CodexProjects\Project1\output\verification\multi-agent-test\manual-run'
        $config.PreflightPath | Should Be (Join-Path $config.ArtifactDir 'preflight.json')
        $config.BackendLanePath | Should Be (Join-Path $config.ArtifactDir 'backend-lane.json')
        $config.DataCliLanePath | Should Be (Join-Path $config.ArtifactDir 'data-cli-lane.json')
        $config.FrontendLanePath | Should Be (Join-Path $config.ArtifactDir 'frontend-lane.json')
        $config.ResultPath | Should Be (Join-Path $config.ArtifactDir 'result.json')
        $config.ReportPath | Should Be (Join-Path $config.ArtifactDir 'report.md')
        $config.LaneLogsDir | Should Be (Join-Path $config.ArtifactDir 'lane-logs')
        $config.RealE2EOutputRoot | Should Be (Join-Path $config.ArtifactDir 'real-e2e')
        $config.RealE2EResultPath | Should Be (Join-Path $config.ArtifactDir 'real-e2e-result.json')
        $config.ProgressPath | Should Be (Join-Path $config.ArtifactDir 'progress.json')
        $config.ControlPath | Should Be (Join-Path $config.ArtifactDir 'control.json')
        $config.ManifestPath | Should Be (Join-Path $config.ArtifactDir 'manifest.json')
        $config.RuntimeDir | Should Be 'D:\CodexProjects\Project1\output\verification\multi-agent-test\_runtime'
        $config.ActiveExecutionPath | Should Be 'D:\CodexProjects\Project1\output\verification\multi-agent-test\_runtime\active-execution.json'
        $config.LastKnownExecutionPath | Should Be 'D:\CodexProjects\Project1\output\verification\multi-agent-test\_runtime\last-known.json'
        $config.RealE2EModulePath | Should Be 'D:\CodexProjects\Project1\tools\Webnovel-RealE2E.psm1'
        $config.NodeModulesPath | Should Be 'D:\CodexProjects\Project1\webnovel-writer\webnovel-writer\dashboard\frontend\node_modules'
    }
}

Describe 'Initialize-WebnovelMultiAgentTestArtifacts' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'creates the standard artifact directories and clears the report placeholders' {
        $config = Get-WebnovelMultiAgentTestConfig `
            -WorkspaceRoot 'D:\CodexProjects\Project1' `
            -OutputRoot (Join-Path $TestDrive 'multi-agent-test') `
            -PreferredPort 8765 `
            -RunId 'testrun'

        Initialize-WebnovelMultiAgentTestArtifacts -Config $config

        foreach ($path in @(
            $config.ArtifactDir,
            $config.LaneLogsDir,
            $config.RealE2EOutputRoot,
            $config.RuntimeDir
        )) {
            Test-Path $path | Should Be $true
        }

        $realE2EPlaceholder = Get-Content -Path $config.RealE2EResultPath -Raw | ConvertFrom-Json
        $realE2EPlaceholder.skipped | Should Be $true
        $progressPlaceholder = Get-Content -Path $config.ProgressPath -Raw | ConvertFrom-Json
        $progressPlaceholder.phase | Should Be 'preflight'
        $progressPlaceholder.completed_steps | Should Be 0
        $controlPlaceholder = Get-Content -Path $config.ControlPath -Raw | ConvertFrom-Json
        $controlPlaceholder.stop_requested | Should Be $false
    }
}

Describe 'Get-WebnovelMultiAgentLaneDecision' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'stops before RealE2E when a blocking step fails' {
        InModuleScope $multiAgentModule.Name {
            $decision = Get-WebnovelMultiAgentLaneDecision -LaneResults @(
                [pscustomobject]@{
                    name = 'backend'
                    status = 'failed'
                    suspected_environment_issue = $false
                    steps = @(
                        [pscustomobject]@{
                            id = 'backend.dashboard-package-contract'
                            name = 'dashboard-package-contract'
                            passed = $false
                            failure_kind = 'test_failure'
                            blocking_severity = 'blocking'
                        }
                    )
                },
                [pscustomobject]@{ name = 'data-cli'; status = 'passed'; suspected_environment_issue = $false; steps = @() },
                [pscustomobject]@{ name = 'frontend'; status = 'passed'; suspected_environment_issue = $false; steps = @() }
            )

            $decision.should_run_real_e2e | Should Be $false
            $decision.classification | Should Be 'local_blocker'
            $decision.blocking_lane_names | Should Be @('backend')
            $decision.blocking_step_ids | Should Be @('backend.dashboard-package-contract')
            $decision.reason | Should Match 'blocking'
        }
    }

    It 'continues to RealE2E when only a non-blocking step failed' {
        InModuleScope $multiAgentModule.Name {
            $decision = Get-WebnovelMultiAgentLaneDecision -LaneResults @(
                [pscustomobject]@{
                    name = 'frontend'
                    status = 'failed'
                    suspected_environment_issue = $false
                    steps = @(
                        [pscustomobject]@{
                            id = 'frontend.frontend-typecheck'
                            name = 'frontend-typecheck'
                            passed = $false
                            failure_kind = 'test_failure'
                            blocking_severity = 'non_blocking'
                        }
                    )
                },
                [pscustomobject]@{ name = 'backend'; status = 'passed'; suspected_environment_issue = $false; steps = @() },
                [pscustomobject]@{ name = 'data-cli'; status = 'passed'; suspected_environment_issue = $false; steps = @() }
            )

            $decision.should_run_real_e2e | Should Be $true
            $decision.classification | Should Be 'local_regression'
            @($decision.blocking_lane_names).Count | Should Be 0
            @($decision.blocking_step_ids).Count | Should Be 0
        }
    }

    It 'stops before RealE2E when any failed step is an environment failure' {
        InModuleScope $multiAgentModule.Name {
            $decision = Get-WebnovelMultiAgentLaneDecision -LaneResults @(
                [pscustomobject]@{
                    name = 'frontend'
                    status = 'failed'
                    suspected_environment_issue = $true
                    steps = @(
                        [pscustomobject]@{
                            id = 'frontend.frontend-tests'
                            name = 'frontend-tests'
                            passed = $false
                            failure_kind = 'environment'
                            blocking_severity = 'blocking'
                        }
                    )
                }
            )

            $decision.should_run_real_e2e | Should Be $false
            $decision.classification | Should Be 'environment_blocked'
            $decision.blocking_step_ids | Should Be @('frontend.frontend-tests')
            $decision.reason | Should Match 'environment'
        }
    }
}

Describe 'Get-WebnovelMultiAgentFailureKind' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'classifies missing module output as environment' {
        InModuleScope $multiAgentModule.Name {
            $kind = Get-WebnovelMultiAgentFailureKind -ExitCode 1 -TimedOut:$false -StdoutText '' -StderrText 'ModuleNotFoundError: No module named x'
            $kind | Should Be 'environment'
        }
    }

    It 'classifies timed out commands as timeout' {
        InModuleScope $multiAgentModule.Name {
            $kind = Get-WebnovelMultiAgentFailureKind -ExitCode 1 -TimedOut:$true -StdoutText '' -StderrText ''
            $kind | Should Be 'timeout'
        }
    }

    It 'classifies assertion failures as test_failure' {
        InModuleScope $multiAgentModule.Name {
            $kind = Get-WebnovelMultiAgentFailureKind -ExitCode 1 -TimedOut:$false -StdoutText 'FAILED test_example.py::test_x - AssertionError' -StderrText ''
            $kind | Should Be 'test_failure'
        }
    }

    It 'classifies non-environment framework failures as tooling_failure' {
        InModuleScope $multiAgentModule.Name {
            $kind = Get-WebnovelMultiAgentFailureKind -ExitCode 1 -TimedOut:$false -StdoutText 'npm ERR! code ELIFECYCLE' -StderrText 'process exited unexpectedly'
            $kind | Should Be 'tooling_failure'
        }
    }
}

Describe 'Test-WebnovelMultiAgentPreflight' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'blocks when npm is missing from the current PowerShell session' {
        InModuleScope $multiAgentModule.Name {
            Mock Get-Command {
                param($Name)
                if ($Name -eq 'npm') { return $null }
                [pscustomobject]@{ Source = $Name }
            }
            Mock Test-Path { $true }
            Mock Invoke-WebnovelMultiAgentProbeCommand { [pscustomobject]@{ ok = $true; exit_code = 0; output = 'ok' } }

            $config = Get-WebnovelMultiAgentTestConfig -WorkspaceRoot 'D:\CodexProjects\Project1' -OutputRoot (Join-Path $TestDrive 'preflight-a')
            $result = Test-WebnovelMultiAgentPreflight -Config $config

            $result.classification | Should Be 'environment_blocked'
            @($result.issues | Where-Object { $_.name -eq 'npm' }).Count | Should Be 1
        }
    }

    It 'blocks when playwright script path is missing' {
        InModuleScope $multiAgentModule.Name {
            Mock Get-Command { [pscustomobject]@{ Source = 'tool' } }
            Mock Test-Path {
                param($Path)
                if ($Path -like '*playwright_cli.ps1') { return $false }
                $true
            }
            Mock Invoke-WebnovelMultiAgentProbeCommand { [pscustomobject]@{ ok = $true; exit_code = 0; output = 'ok' } }

            $config = Get-WebnovelMultiAgentTestConfig -WorkspaceRoot 'D:\CodexProjects\Project1' -OutputRoot (Join-Path $TestDrive 'preflight-b')
            $result = Test-WebnovelMultiAgentPreflight -Config $config

            $result.classification | Should Be 'environment_blocked'
            @($result.missing_paths | Where-Object { $_.name -eq 'playwright_script' }).Count | Should Be 1
        }
    }

    It 'blocks when python pytest version probe fails' {
        InModuleScope $multiAgentModule.Name {
            Mock Get-Command { [pscustomobject]@{ Source = 'tool' } }
            Mock Test-Path { $true }
            Mock Invoke-WebnovelMultiAgentProbeCommand {
                param([string]$FilePath)
                if ($FilePath -eq 'python') {
                    return [pscustomobject]@{ ok = $false; exit_code = 2; output = 'pytest missing' }
                }
                [pscustomobject]@{ ok = $true; exit_code = 0; output = 'ok' }
            }

            $config = Get-WebnovelMultiAgentTestConfig -WorkspaceRoot 'D:\CodexProjects\Project1' -OutputRoot (Join-Path $TestDrive 'preflight-c')
            $result = Test-WebnovelMultiAgentPreflight -Config $config

            $result.classification | Should Be 'environment_blocked'
            @($result.failed_commands | Where-Object { $_.name -eq 'python-pytest-version' }).Count | Should Be 1
        }
    }

    It 'blocks when frontend node_modules is missing' {
        InModuleScope $multiAgentModule.Name {
            Mock Get-Command { [pscustomobject]@{ Source = 'tool' } }
            Mock Test-Path {
                param($Path)
                if ($Path -like '*dashboard\frontend\node_modules') { return $false }
                $true
            }
            Mock Invoke-WebnovelMultiAgentProbeCommand { [pscustomobject]@{ ok = $true; exit_code = 0; output = 'ok' } }

            $config = Get-WebnovelMultiAgentTestConfig -WorkspaceRoot 'D:\CodexProjects\Project1' -OutputRoot (Join-Path $TestDrive 'preflight-d')
            $result = Test-WebnovelMultiAgentPreflight -Config $config

            $result.classification | Should Be 'environment_blocked'
            @($result.missing_paths | Where-Object { $_.name -eq 'frontend_node_modules' }).Count | Should Be 1
        }
    }
}

Describe 'Invoke-WebnovelMultiAgentLaneCommand' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'marks timed out commands and records separate log paths' {
        InModuleScope $multiAgentModule.Name {
            Mock Start-Process { [pscustomobject]@{ Id = 4242; HasExited = $false } }
            Mock Wait-Process { throw [System.TimeoutException]::new('timeout') }
            Mock Stop-Process {}
            Mock Test-Path { $true }
            Mock Get-Content {
                param([string]$Path)
                if ($Path -like '*stdout*') { return 'partial stdout' }
                if ($Path -like '*stderr*') { return 'partial stderr' }
                return ''
            }

            $result = Invoke-WebnovelMultiAgentLaneCommand -LaneName 'backend' -CommandSpec @{
                id = 'backend.dashboard-root-contract'
                name = 'dashboard-root-contract'
                workdir = 'D:\CodexProjects\Project1'
                file_path = 'python'
                arguments = @('-m', 'pytest')
                environment = @{}
                blocking_severity = 'blocking'
                timeout_seconds = 10
            } -LaneLogsDir (Join-Path $TestDrive 'lane-logs')

            $result.timed_out | Should Be $true
            $result.failure_kind | Should Be 'timeout'
            $result.blocking_severity | Should Be 'blocking'
            $result.timeout_seconds | Should Be 10
            $result.stdout_log_path | Should Match 'stdout'
            $result.stderr_log_path | Should Match 'stderr'
            $result.combined_log_path | Should Match 'combined'
        }
    }
}

Describe 'Get-WebnovelMultiAgentFinalClassification' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'prefers environment blockers over all other outcomes' {
        InModuleScope $multiAgentModule.Name {
            $classification = Get-WebnovelMultiAgentFinalClassification `
                -PreflightClassification 'environment_blocked' `
                -LocalClassification 'local_blocker' `
                -RealE2EClassification 'mainline_failure'

            $classification | Should Be 'environment_blocked'
        }
    }

    It 'surfaces RealE2E failures ahead of local regressions when RealE2E ran' {
        InModuleScope $multiAgentModule.Name {
            $classification = Get-WebnovelMultiAgentFinalClassification `
                -PreflightClassification 'pass' `
                -LocalClassification 'local_regression' `
                -RealE2EClassification 'mainline_failure'

            $classification | Should Be 'mainline_failure'
        }
    }

    It 'returns cancelled when the coordinator stop path won' {
        InModuleScope $multiAgentModule.Name {
            $classification = Get-WebnovelMultiAgentFinalClassification `
                -PreflightClassification 'pass' `
                -LocalClassification 'cancelled' `
                -RealE2EClassification ''

            $classification | Should Be 'cancelled'
        }
    }
}

Describe 'Get-WebnovelMultiAgentNextAction' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'maps cancelled to rerun_after_cancel' {
        InModuleScope $multiAgentModule.Name {
            $action = Get-WebnovelMultiAgentNextAction -Classification 'cancelled'
            $action | Should Be 'rerun_after_cancel'
        }
    }
}

Describe 'Invoke-WebnovelMultiAgentTest' {
    BeforeAll {
        $script:multiAgentModule = Import-Module $modulePath -Force -PassThru
    }

    It 'runs RealE2E when local lanes do not produce a blocker' {
        InModuleScope $multiAgentModule.Name {
            Mock Initialize-WebnovelMultiAgentTestArtifacts {}
            Mock Test-WebnovelMultiAgentPreflight {
                [pscustomobject]@{
                    classification = 'pass'
                    ready = $true
                    issues = @()
                    missing_paths = @()
                    failed_commands = @()
                }
            }
            Mock Invoke-WebnovelMultiAgentLocalLanes {
                @(
                    [pscustomobject]@{ name = 'backend'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' },
                    [pscustomobject]@{ name = 'data-cli'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' },
                    [pscustomobject]@{ name = 'frontend'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' }
                )
            }
            Mock Invoke-WebnovelMultiAgentRealE2E {
                [pscustomobject]@{
                    classification = 'pass'
                    artifact_dir = 'D:\fake-real-e2e'
                    minimal_repro = ''
                    phases = @()
                }
            }

            $config = Get-WebnovelMultiAgentTestConfig `
                -WorkspaceRoot 'D:\CodexProjects\Project1' `
                -OutputRoot (Join-Path $TestDrive 'multi-agent-test') `
                -PreferredPort 8765 `
                -RunId 'invoke-pass'

            $result = Invoke-WebnovelMultiAgentTest -Config $config

            Assert-MockCalled Invoke-WebnovelMultiAgentRealE2E -Times 1 -Exactly -Scope It
            $result.classification | Should Be 'pass'
            $result.real_e2e.status | Should Be 'executed'
            $result.next_action | Should Be 'ready_to_pass'
            (Test-Path $config.ProgressPath) | Should Be $true
            (Test-Path $config.ManifestPath) | Should Be $true
        }
    }

    It 'skips RealE2E when local lanes produce a blocker classification' {
        InModuleScope $multiAgentModule.Name {
            Mock Initialize-WebnovelMultiAgentTestArtifacts {}
            Mock Test-WebnovelMultiAgentPreflight {
                [pscustomobject]@{
                    classification = 'pass'
                    ready = $true
                    issues = @()
                    missing_paths = @()
                    failed_commands = @()
                }
            }
            Mock Invoke-WebnovelMultiAgentLocalLanes {
                @(
                    [pscustomobject]@{
                        name = 'backend'
                        status = 'failed'
                        failed_step_count = 1
                        suspected_environment_issue = $false
                        failed_step_names = @('dashboard-package-contract')
                        blocking_step_names = @('dashboard-package-contract')
                        recommended_action = 'fix_backend_first'
                        steps = @(
                            [pscustomobject]@{
                                id = 'backend.dashboard-package-contract'
                                name = 'dashboard-package-contract'
                                passed = $false
                                failure_kind = 'test_failure'
                                blocking_severity = 'blocking'
                            }
                        )
                    },
                    [pscustomobject]@{ name = 'data-cli'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' },
                    [pscustomobject]@{ name = 'frontend'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' }
                )
            }
            Mock Invoke-WebnovelMultiAgentRealE2E { throw 'RealE2E should not be executed' }

            $config = Get-WebnovelMultiAgentTestConfig `
                -WorkspaceRoot 'D:\CodexProjects\Project1' `
                -OutputRoot (Join-Path $TestDrive 'multi-agent-test') `
                -PreferredPort 8765 `
                -RunId 'invoke-blocked'

            $result = Invoke-WebnovelMultiAgentTest -Config $config

            Assert-MockCalled Invoke-WebnovelMultiAgentRealE2E -Times 0 -Exactly -Scope It
            $result.classification | Should Be 'local_blocker'
            $result.real_e2e.status | Should Be 'skipped'
            $result.next_action | Should Be 'fix_local_blocker_and_rerun'
            $result.blocking_step_ids | Should Be @('backend.dashboard-package-contract')
            $result.failure_fingerprint | Should Be 'backend.dashboard-package-contract:test_failure'
            $manifest = Get-Content -Path $config.ManifestPath -Raw | ConvertFrom-Json
            $manifest.failure_fingerprint | Should Be 'backend.dashboard-package-contract:test_failure'
        }
    }

    It 'returns cancelled and skips RealE2E when stop was requested before RealE2E' {
        InModuleScope $multiAgentModule.Name {
            Mock Initialize-WebnovelMultiAgentTestArtifacts {}
            Mock Test-WebnovelMultiAgentPreflight {
                [pscustomobject]@{
                    classification = 'pass'
                    ready = $true
                    issues = @()
                    missing_paths = @()
                    failed_commands = @()
                }
            }
            Mock Invoke-WebnovelMultiAgentLocalLanes {
                @(
                    [pscustomobject]@{ name = 'backend'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' },
                    [pscustomobject]@{ name = 'data-cli'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' },
                    [pscustomobject]@{ name = 'frontend'; status = 'passed'; failed_step_count = 0; suspected_environment_issue = $false; steps = @(); failed_step_names = @(); blocking_step_names = @(); recommended_action = '' }
                )
            }
            Mock Test-WebnovelMultiAgentStopRequested { $true }
            Mock Invoke-WebnovelMultiAgentRealE2E { throw 'RealE2E should not be executed after stop request' }

            $config = Get-WebnovelMultiAgentTestConfig `
                -WorkspaceRoot 'D:\CodexProjects\Project1' `
                -OutputRoot (Join-Path $TestDrive 'multi-agent-test') `
                -PreferredPort 8765 `
                -RunId 'invoke-cancelled'

            $result = Invoke-WebnovelMultiAgentTest -Config $config

            Assert-MockCalled Invoke-WebnovelMultiAgentRealE2E -Times 0 -Exactly -Scope It
            $result.classification | Should Be 'cancelled'
            $result.next_action | Should Be 'rerun_after_cancel'
            $result.real_e2e.status | Should Be 'skipped_due_to_cancel'
        }
    }
}
