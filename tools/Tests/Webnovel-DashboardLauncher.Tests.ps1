Import-Module Pester

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-DashboardLauncher.psm1'

Describe 'Resolve-WebnovelDashboardPortAction' {
    BeforeAll {
        $script:launcherModule = Import-Module $modulePath -Force -PassThru
    }

    It 'reuses an existing healthy dashboard listener' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 4242 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 4242; ProcessName = 'python'; Path = 'C:\Python311\python.exe' }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 4242
                CommandLine = 'python -m dashboard.server --workspace-root D:\CodexProjects\Project1'
                ExecutablePath = 'C:\Python311\python.exe'
            }
        }
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            [pscustomobject]@{
                Healthy = $true
                Reason = 'json_response'
                Uri = 'http://127.0.0.1:8765/api/workbench/hub'
                Path = '/api/workbench/hub'
                Label = 'workbench-hub'
                Message = ''
            }
        }

        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1'

        $result.Action | Should Be 'reuse_existing'
    }

    It 'passes workbench mode into the shared health probe when no project root is selected' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 4242 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 4242; ProcessName = 'python'; Path = 'C:\Python311\python.exe' }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 4242
                CommandLine = 'python -m dashboard.server --workspace-root D:\CodexProjects\Project1'
                ExecutablePath = 'C:\Python311\python.exe'
            }
        }
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            [pscustomobject]@{
                Healthy = $true
                Reason = 'json_response'
                Uri = 'http://127.0.0.1:8765/api/workbench/hub'
                Path = '/api/workbench/hub'
                Label = 'workbench-hub'
                Message = ''
            }
        }

        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1'

        $result.Action | Should Be 'reuse_existing'
        $result.Probe.Uri | Should Match '/api/workbench/hub$'
        Assert-MockCalled Invoke-WebnovelDashboardHealthProbe -ModuleName $launcherModule.Name -Times 1 -Exactly -Scope It -ParameterFilter {
            $BaseUrl -eq 'http://127.0.0.1:8765' -and [string]::IsNullOrWhiteSpace($ProjectRoot)
        }
    }

    It 'restarts a stale dashboard listener when the health probe is unhealthy' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 4242 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 4242; ProcessName = 'python'; Path = 'C:\Python311\python.exe' }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 4242
                CommandLine = 'python -m dashboard.server --workspace-root D:\CodexProjects\Project1'
                ExecutablePath = 'C:\Python311\python.exe'
            }
        }
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            [pscustomobject]@{
                Healthy = $false
                Reason = 'html_response'
                Uri = 'http://127.0.0.1:8765/api/workbench/hub'
                Path = '/api/workbench/hub'
                Label = 'workbench-hub'
                Message = 'workbench-hub returned HTML instead of JSON.'
            }
        }

        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1'

        $result.Action | Should Be 'restart_existing'
        $result.Reason | Should Be 'html_response'
    }

    It 'passes project mode into the shared health probe when a project is selected' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 4242 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 4242; ProcessName = 'python'; Path = 'C:\Python311\python.exe' }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 4242
                CommandLine = 'python -m dashboard.server --workspace-root D:\CodexProjects\Project1'
                ExecutablePath = 'C:\Python311\python.exe'
            }
        }

        $projectRoot = 'D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260322-062539\smoke-project'
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            [pscustomobject]@{
                Healthy = $true
                Reason = 'json_response'
                Uri = 'http://127.0.0.1:8765/api/project/director-hub?project_root=D%3A%5CCodexProjects%5CProject1%5Cwebnovel-writer%5C.tmp-playwright-20260322-062539%5Csmoke-project'
                Path = '/api/project/director-hub'
                Label = 'director-hub'
                Message = ''
            }
        }

        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1' -ProjectRoot $projectRoot

        $result.Action | Should Be 'reuse_existing'
        $result.Probe.Uri | Should Match '/api/project/director-hub'
        $result.Probe.Uri | Should Match 'project_root='
        Assert-MockCalled Invoke-WebnovelDashboardHealthProbe -ModuleName $launcherModule.Name -Times 1 -Exactly -Scope It -ParameterFilter {
            $BaseUrl -eq 'http://127.0.0.1:8765' -and $ProjectRoot -eq 'D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260322-062539\smoke-project'
        }
    }

    It 'surfaces request_failed cleanly when the probe cannot reach the service' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 4242 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 4242; ProcessName = 'python'; Path = 'C:\Python311\python.exe' }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 4242
                CommandLine = 'python -m dashboard.server --workspace-root D:\CodexProjects\Project1'
                ExecutablePath = 'C:\Python311\python.exe'
            }
        }

        $projectRoot = 'D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260322-062539\smoke-project'
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            [pscustomobject]@{
                Healthy = $false
                Reason = 'request_failed'
                Uri = 'http://127.0.0.1:8765/api/project/director-hub?project_root=D%3A%5CCodexProjects%5CProject1%5Cwebnovel-writer%5C.tmp-playwright-20260322-062539%5Csmoke-project'
                Path = '/api/project/director-hub'
                Label = 'director-hub'
                Message = 'Object reference not set to an instance of an object.'
            }
        }

        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1' -ProjectRoot $projectRoot

        $result.Action | Should Be 'restart_existing'
        $result.Reason | Should Be 'request_failed'
        $result.Probe.Message | Should Match 'Object reference'
    }

    It 'reuses an existing listener when process metadata is missing but workbench probe confirms the workspace' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 4242 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 4242; ProcessName = 'python'; Path = $null }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 4242
                CommandLine = ''
                ExecutablePath = ''
            }
        }
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            param([string]$BaseUrl, [string]$ProjectRoot)
            if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
                return [pscustomobject]@{
                    Healthy = $true
                    Reason = 'json_response'
                    Uri = 'http://127.0.0.1:8765/api/workbench/hub'
                    Path = '/api/workbench/hub'
                    Label = 'workbench-hub'
                    Payload = [pscustomobject]@{ workspace_root = 'D:\CodexProjects\Project1' }
                    Message = ''
                }
            }
            return [pscustomobject]@{
                Healthy = $true
                Reason = 'json_response'
                Uri = 'http://127.0.0.1:8765/api/project/director-hub?project_root=D%3A%5CCodexProjects%5CProject1%5Cwebnovel-writer%5C.tmp-playwright-20260322-062539%5Csmoke-project'
                Path = '/api/project/director-hub'
                Label = 'director-hub'
                Payload = [pscustomobject]@{ current_chapter = 2 }
                Message = ''
            }
        }

        $projectRoot = 'D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260322-062539\smoke-project'
        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1' -ProjectRoot $projectRoot

        $result.Action | Should Be 'reuse_existing'
        Assert-MockCalled Invoke-WebnovelDashboardHealthProbe -ModuleName $launcherModule.Name -Times 2 -Exactly -Scope It
        $result.Probe.Uri | Should Match '/api/project/director-hub'
    }

    It 'refuses to kill an unrelated process that only happens to occupy the port' {
        Mock -ModuleName $launcherModule.Name Get-NetTCPConnection {
            [pscustomobject]@{ OwningProcess = 9999 }
        }
        Mock -ModuleName $launcherModule.Name Get-Process {
            [pscustomobject]@{ Id = 9999; ProcessName = 'nginx'; Path = 'C:\nginx\nginx.exe' }
        }
        Mock -ModuleName $launcherModule.Name Get-CimInstance {
            [pscustomobject]@{
                ProcessId = 9999
                CommandLine = 'nginx.exe'
                ExecutablePath = 'C:\nginx\nginx.exe'
            }
        }
        Mock -ModuleName $launcherModule.Name Invoke-WebnovelDashboardHealthProbe {
            [pscustomobject]@{
                Healthy = $false
                Reason = 'request_failed'
                Uri = 'http://127.0.0.1:8765/api/workbench/hub'
                Path = '/api/workbench/hub'
                Label = 'workbench-hub'
                Message = 'Unable to connect'
            }
        }

        $result = Resolve-WebnovelDashboardPortAction -Port 8765 -BaseUrl 'http://127.0.0.1:8765' -WorkspaceRoot 'D:\CodexProjects\Project1'

        $result.Action | Should Be 'abort_port_in_use'
    }
}

Describe 'Get-WebnovelDashboardHealthProbeSpec' {
    BeforeAll {
        $script:launcherModule = Import-Module $modulePath -Force -PassThru
    }

    It 'uses the workbench hub probe in workbench mode' {
        $probe = Get-WebnovelDashboardHealthProbeSpec -BaseUrl 'http://127.0.0.1:8765'

        $probe.Path | Should Be '/api/workbench/hub'
        $probe.Label | Should Be 'workbench-hub'
        $probe.Uri | Should Be 'http://127.0.0.1:8765/api/workbench/hub'
    }

    It 'uses the director hub probe with encoded project_root in project mode' {
        $projectRoot = 'D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260322-062539\smoke-project'

        $probe = Get-WebnovelDashboardHealthProbeSpec -BaseUrl 'http://127.0.0.1:8765' -ProjectRoot $projectRoot

        $probe.Path | Should Be '/api/project/director-hub'
        $probe.Label | Should Be 'director-hub'
        $probe.Uri | Should Match '/api/project/director-hub\?project_root='
        $probe.Uri | Should Match 'project_root=D%3A%5CCodexProjects%5CProject1'
    }
}
