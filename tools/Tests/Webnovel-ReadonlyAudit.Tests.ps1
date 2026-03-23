Import-Module Pester

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-ReadonlyAudit.psm1'

Describe 'Get-WebnovelReadonlyAuditConfig' {
    BeforeAll {
        $script:readonlyAuditModule = Import-Module $modulePath -Force -PassThru
    }

    It 'builds the standard artifact paths under the requested output root' {
        $config = Get-WebnovelReadonlyAuditConfig `
            -WorkspaceRoot 'D:\CodexProjects\Project1' `
            -OutputRoot 'D:\CodexProjects\Project1\output\verification\readonly-audit-test' `
            -PreferredPort 8765

        $config.WorkspaceRoot | Should Be 'D:\CodexProjects\Project1'
        $config.PreferredPort | Should Be 8765
        $config.ArtifactDir | Should Be 'D:\CodexProjects\Project1\output\verification\readonly-audit-test'
        $config.FixtureResultPath | Should Be (Join-Path $config.ArtifactDir 'fixture-result.json')
        $config.PrecheckPath | Should Be (Join-Path $config.ArtifactDir 'precheck.json')
        $config.TranscriptPath | Should Be (Join-Path $config.ArtifactDir 'playwright-transcript.txt')
        $config.SnapshotIndexPath | Should Be (Join-Path $config.ArtifactDir 'snapshot-index.txt')
        $config.ScreenshotIndexPath | Should Be (Join-Path $config.ArtifactDir 'screenshot-index.txt')
        $config.ResultPath | Should Be (Join-Path $config.ArtifactDir 'result.json')
    }
}

Describe 'Get-WebnovelReadonlyAuditPort' {
    BeforeAll {
        $script:readonlyAuditModule = Import-Module $modulePath -Force -PassThru
    }

    It 'returns the preferred port when it is free' {
        Mock -ModuleName $readonlyAuditModule.Name Get-NetTCPConnection { $null }

        $port = Get-WebnovelReadonlyAuditPort -PreferredPort 8765

        $port | Should Be 8765
    }

    It 'falls back to the first isolated port when the preferred port is occupied' {
        Mock -ModuleName $readonlyAuditModule.Name Get-NetTCPConnection {
            param($LocalPort)
            $port = @($LocalPort)[0]
            if ($port -eq 8765) {
                return [pscustomobject]@{ OwningProcess = 4242 }
            }
            return $null
        }

        $port = Get-WebnovelReadonlyAuditPort -PreferredPort 8765

        $port | Should Be 8876
    }
}

Describe 'Initialize-WebnovelReadonlyAuditArtifacts' {
    BeforeAll {
        $script:readonlyAuditModule = Import-Module $modulePath -Force -PassThru
    }

    It 'creates the standard artifact files and clears prior transcript indexes' {
        $artifactDir = Join-Path $TestDrive 'readonly-audit'
        $config = Get-WebnovelReadonlyAuditConfig `
            -WorkspaceRoot 'D:\CodexProjects\Project1' `
            -OutputRoot $artifactDir `
            -PreferredPort 8765

        Initialize-WebnovelReadonlyAuditArtifacts -Config $config

        foreach ($path in @(
            $config.TranscriptPath,
            $config.SnapshotIndexPath,
            $config.ScreenshotIndexPath
        )) {
            Test-Path $path | Should Be $true
            ((Get-Content -Path $path -Raw).Trim()) | Should Be ''
        }
    }
}
