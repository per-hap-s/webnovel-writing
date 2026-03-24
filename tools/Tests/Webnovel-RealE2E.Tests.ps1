Import-Module Pester

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-RealE2E.psm1'

Describe 'Get-WebnovelRealE2EConfig' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'builds the standard artifact paths and default temporary project root' {
        $dateStamp = Get-Date -Format 'yyyyMMdd'
        $config = Get-WebnovelRealE2EConfig `
            -WorkspaceRoot 'D:\CodexProjects\Project1' `
            -OutputRoot 'D:\CodexProjects\Project1\output\verification\real-e2e\20260323-abc123' `
            -PreferredPort 8765 `
            -RunId 'abc123'

        $config.WorkspaceRoot | Should Be 'D:\CodexProjects\Project1'
        $config.ArtifactDir | Should Be 'D:\CodexProjects\Project1\output\verification\real-e2e\20260323-abc123'
        $config.ProjectRoot | Should Be ("D:\CodexProjects\Project1\webnovel-writer\.tmp-real-e2e-{0}-abc123" -f $dateStamp)
        $config.BootstrapResponsePath | Should Be (Join-Path $config.ArtifactDir 'bootstrap-response.json')
        $config.PlanningProfileBeforePath | Should Be (Join-Path $config.ArtifactDir 'planning-profile-before.json')
        $config.PlanningProfileAfterPath | Should Be (Join-Path $config.ArtifactDir 'planning-profile-after.json')
        $config.PlanSummaryPath | Should Be (Join-Path $config.ArtifactDir 'task-summary-plan.json')
        $config.WriteChapter1SummaryPath | Should Be (Join-Path $config.ArtifactDir 'task-summary-write-ch1.json')
        $config.WriteChapter2SummaryPath | Should Be (Join-Path $config.ArtifactDir 'task-summary-write-ch2.json')
        $config.WriteChapter3SummaryPath | Should Be (Join-Path $config.ArtifactDir 'task-summary-write-ch3.json')
        $config.ReviewSummaryPath | Should Be (Join-Path $config.ArtifactDir 'task-summary-review-1-3.json')
        $config.RepairSummaryPath | Should Be (Join-Path $config.ArtifactDir 'task-summary-repair.json')
        $config.ProjectStateFinalPath | Should Be (Join-Path $config.ArtifactDir 'project-state-final.json')
        $config.ReadonlyAuditResultPath | Should Be (Join-Path $config.ArtifactDir 'readonly-audit-result.json')
        $config.AcceptanceReportPath | Should Be (Join-Path $config.ArtifactDir 'acceptance-report.md')
        $config.PlaywrightDir | Should Be 'D:\CodexProjects\Project1\.playwright-cli'
    }
}

Describe 'Get-WebnovelRealE2EPort' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'returns the preferred port when it is free' {
        Mock -ModuleName $realE2EModule.Name Get-NetTCPConnection { $null }

        $port = Get-WebnovelRealE2EPort -PreferredPort 8765

        $port | Should Be 8765
    }

    It 'falls back to the first isolated port when the preferred port is occupied' {
        Mock -ModuleName $realE2EModule.Name Get-NetTCPConnection {
            param($LocalPort)
            $port = @($LocalPort)[0]
            if ($port -eq 8765) {
                return [pscustomobject]@{ OwningProcess = 4242 }
            }
            return $null
        }

        $port = Get-WebnovelRealE2EPort -PreferredPort 8765

        $port | Should Be 8876
    }
}

Describe 'Initialize-WebnovelRealE2EArtifacts' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'creates the artifact directory and seeds skipped placeholders' {
        $artifactDir = Join-Path $TestDrive 'real-e2e'
        $config = Get-WebnovelRealE2EConfig `
            -WorkspaceRoot 'D:\CodexProjects\Project1' `
            -OutputRoot $artifactDir `
            -PreferredPort 8765 `
            -RunId 'testrun'

        Initialize-WebnovelRealE2EArtifacts -Config $config

        Test-Path $config.ArtifactDir | Should Be $true
        Test-Path $config.RepairSummaryPath | Should Be $true
        Test-Path $config.ReadonlyAuditResultPath | Should Be $true

        $repairPlaceholder = Get-Content -Path $config.RepairSummaryPath -Raw | ConvertFrom-Json
        $repairPlaceholder.skipped | Should Be $true
        $repairPlaceholder.reason | Should Match 'skipped'

        $readonlyPlaceholder = Get-Content -Path $config.ReadonlyAuditResultPath -Raw | ConvertFrom-Json
        $readonlyPlaceholder.skipped | Should Be $true
    }
}

Describe 'Invoke-WebnovelRealE2ECapture' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'uses the current playwright-cli commands and page artifact filters' {
        InModuleScope $realE2EModule.Name {
            $transcriptPath = Join-Path $TestDrive 'capture-transcript.txt'
            $playwrightDir = Join-Path $TestDrive '.playwright-cli'
            New-Item -ItemType Directory -Path $playwrightDir -Force | Out-Null

            $script:playwrightCalls = @()
            function script:FakePlaywright {
                param(
                    [Parameter(ValueFromRemainingArguments = $true)]
                    [string[]]$ArgsList
                )

                $script:playwrightCalls += ,@($ArgsList)
            }

            Mock Start-Sleep {}
            Mock Get-WebnovelRealE2ENewPlaywrightFile {
                param($Directory, $Filter)

                if ($Filter -eq 'page-*.yml') {
                    return 'D:\snapshots\page-control.yml'
                }

                return 'D:\snapshots\page-control.png'
            }

            $capture = Invoke-WebnovelRealE2ECapture `
                -Name 'control' `
                -Url 'http://127.0.0.1:8877/?page=control' `
                -PlaywrightScript 'FakePlaywright' `
                -PlaywrightDir $playwrightDir `
                -TranscriptPath $transcriptPath `
                -PlaywrightWorkdir $TestDrive `
                -Open

            $capture.snapshot | Should Be 'D:\snapshots\page-control.yml'
            $capture.screenshot | Should Be 'D:\snapshots\page-control.png'
            $script:playwrightCalls.Count | Should Be 3
            $script:playwrightCalls[0] | Should Be @('open', 'http://127.0.0.1:8877/?page=control', '--browser', 'msedge', '--headed')
            $script:playwrightCalls[1] | Should Be @('snapshot')
            $script:playwrightCalls[2] | Should Be @('screenshot')

            $transcript = Get-Content -Path $transcriptPath -Raw
            $transcript | Should Match 'control'
            $transcript | Should Match 'http://127.0.0.1:8877/\?page=control'
        }
    }

    It 'uses goto for follow-up page captures in the same browser session' {
        InModuleScope $realE2EModule.Name {
            $transcriptPath = Join-Path $TestDrive 'capture-transcript.txt'
            $playwrightDir = Join-Path $TestDrive '.playwright-cli'
            New-Item -ItemType Directory -Path $playwrightDir -Force | Out-Null

            $script:playwrightCalls = @()
            function script:FakePlaywright {
                param(
                    [Parameter(ValueFromRemainingArguments = $true)]
                    [string[]]$ArgsList
                )

                $script:playwrightCalls += ,@($ArgsList)
            }

            Mock Start-Sleep {}
            Mock Get-WebnovelRealE2ENewPlaywrightFile {
                param($Directory, $Filter)

                if ($Filter -eq 'page-*.yml') {
                    return 'D:\snapshots\page-tasks.yml'
                }

                return 'D:\snapshots\page-tasks.png'
            }

            $null = Invoke-WebnovelRealE2ECapture `
                -Name 'tasks' `
                -Url 'http://127.0.0.1:8877/?page=tasks' `
                -PlaywrightScript 'FakePlaywright' `
                -PlaywrightDir $playwrightDir `
                -TranscriptPath $transcriptPath `
                -PlaywrightWorkdir $TestDrive

            $script:playwrightCalls.Count | Should Be 3
            $script:playwrightCalls[0] | Should Be @('goto', 'http://127.0.0.1:8877/?page=tasks')
            $script:playwrightCalls[1] | Should Be @('snapshot')
            $script:playwrightCalls[2] | Should Be @('screenshot')
        }
    }
}

Describe 'Get-WebnovelRealE2EObjectProperty' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'returns the default value for empty objects under strict mode' {
        InModuleScope $realE2EModule.Name {
            $payload = [pscustomobject]@{}

            Get-WebnovelRealE2EObjectProperty -Payload $payload -Name 'recoverability' -Default 'terminal' | Should Be 'terminal'
        }
    }

    It 'reads keys from dictionary-style payloads' {
        InModuleScope $realE2EModule.Name {
            $payload = @{ recoverability = 'retriable' }

            Get-WebnovelRealE2EObjectProperty -Payload $payload -Name 'recoverability' -Default 'terminal' | Should Be 'retriable'
        }
    }
}

Describe 'New-WebnovelRealE2ERepairRequestBody' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'maps a repair candidate into the repair task request contract' {
        InModuleScope $realE2EModule.Name {
            $candidate = [pscustomobject]@{
                chapter = 2
                issue_type = 'TRANSITION_CLARITY'
                issue_title = 'Tighten the movement transition'
                rewrite_goal = 'Clarify the movement path with one local rewrite.'
                guardrails = @('Keep the change inside the current chapter only.')
            }

            $request = New-WebnovelRealE2ERepairRequestBody `
                -ProjectRoot 'D:\CodexProjects\Project1\webnovel-writer\.tmp-real-e2e-20260324-fixture' `
                -SourceTaskId 'task-review-1' `
                -RepairCandidate $candidate

            $request.project_root | Should Be 'D:\CodexProjects\Project1\webnovel-writer\.tmp-real-e2e-20260324-fixture'
            $request.chapter | Should Be 2
            $request.mode | Should Be 'standard'
            $request.require_manual_approval | Should Be $false
            $request.options.source_task_id | Should Be 'task-review-1'
            $request.options.issue_type | Should Be 'TRANSITION_CLARITY'
            $request.options.issue_title | Should Be 'Tighten the movement transition'
            $request.options.rewrite_goal | Should Be 'Clarify the movement path with one local rewrite.'
            $request.options.guardrails | Should Be @('Keep the change inside the current chapter only.')
        }
    }
}

Describe 'Get-WebnovelRealE2EClassification' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'classifies environment blockers before other failures' {
        $classification = Get-WebnovelRealE2EClassification `
            -EnvironmentBlocked `
            -MainlineFailed `
            -PageRegression `
            -ReadonlyAuditClassification 'ui_defect_reproduced'

        $classification | Should Be 'environment_blocked'
    }

    It 'classifies a mainline failure before page or readonly audit regressions' {
        $classification = Get-WebnovelRealE2EClassification `
            -MainlineFailed `
            -PageRegression `
            -ReadonlyAuditClassification 'ui_defect_reproduced'

        $classification | Should Be 'mainline_failure'
    }

    It 'classifies dashboard page mismatches as page regression' {
        $classification = Get-WebnovelRealE2EClassification `
            -PageRegression `
            -ReadonlyAuditClassification 'pass'

        $classification | Should Be 'page_regression'
    }

    It 'classifies readonly audit failures when prior phases passed' {
        $classification = Get-WebnovelRealE2EClassification -ReadonlyAuditClassification 'fixture_failure'

        $classification | Should Be 'readonly_audit_failure'
    }

    It 'returns pass when every phase succeeds' {
        $classification = Get-WebnovelRealE2EClassification -ReadonlyAuditClassification 'pass'

        $classification | Should Be 'pass'
    }
}

Describe 'New-WebnovelRealE2EAcceptanceReport' {
    BeforeAll {
        $script:realE2EModule = Import-Module $modulePath -Force -PassThru
    }

    It 'renders the required sections for a passing run with skipped repair' {
        $report = New-WebnovelRealE2EAcceptanceReport -Result @{
            classification = 'pass'
            passed = $true
            project_root = 'D:\CodexProjects\Project1\webnovel-writer\.tmp-real-e2e-20260323-abc123'
            title = 'Night Rain Rewind'
            genre = 'Urban Supernatural'
            failure_category = ''
            minimal_repro = ''
            phases = @(
                @{ name = 'Environment'; conclusion = 'pass'; detail = 'Model config is available.' },
                @{ name = 'Bootstrap'; conclusion = 'pass'; detail = 'Bootstrap and planning profile save both succeeded.' },
                @{ name = 'Mainline'; conclusion = 'pass'; detail = 'plan/write/review all closed successfully.' },
                @{ name = 'Repair'; conclusion = 'skipped'; detail = 'review did not produce a repair candidate.' },
                @{ name = 'Dashboard'; conclusion = 'pass'; detail = 'control/tasks/quality matched backend state.' },
                @{ name = 'Readonly Audit'; conclusion = 'pass'; detail = 'classification = pass.' }
            )
        }

        $report | Should Match 'D:\\CodexProjects\\Project1\\webnovel-writer\\\.tmp-real-e2e-20260323-abc123'
        $report | Should Match 'Night Rain Rewind'
        $report | Should Match 'pass'
        $report | Should Match 'Repair'
        $report | Should Match 'skipped'
        $report | Should Match 'Readonly Audit'
    }

    It 'renders failure attribution and minimal repro for failing runs' {
        $report = New-WebnovelRealE2EAcceptanceReport -Result @{
            classification = 'mainline_failure'
            passed = $false
            project_root = 'D:\CodexProjects\Project1\webnovel-writer\.tmp-real-e2e-20260323-def456'
            title = 'Night Rain Rewind'
            genre = 'Urban Supernatural'
            failure_category = 'mainline failure'
            minimal_repro = 'write chapter=2 failed after review-summary and stopped in interrupted.'
            phases = @(
                @{ name = 'Mainline'; conclusion = 'failed'; detail = 'write chapter=2 did not close.' }
            )
        }

        $report | Should Match 'Night Rain Rewind'
        $report | Should Match 'mainline failure'
        $report | Should Match 'write chapter=2'
    }
}
