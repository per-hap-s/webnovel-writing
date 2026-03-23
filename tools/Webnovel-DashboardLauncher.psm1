Set-StrictMode -Version Latest

function Normalize-WebnovelPath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ''
    }

    return (($Path.Trim() -replace '/', '\').TrimEnd('\')).ToLowerInvariant()
}

function Normalize-WebnovelText {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ''
    }

    return ($Text.Trim() -replace '/', '\').ToLowerInvariant()
}

function Get-WebnovelDashboardBaseUrl {
    param(
        [string]$Host = '127.0.0.1',
        [int]$Port = 8765
    )

    return ('http://{0}:{1}' -f $Host, $Port)
}

function Get-WebnovelDashboardBrowserUrl {
    param(
        [string]$Host = '127.0.0.1',
        [int]$Port = 8765
    )

    $browserHost = if ($Host -eq '0.0.0.0') { '127.0.0.1' } else { $Host }
    return ('http://{0}:{1}' -f $browserHost, $Port)
}

function Get-WebnovelDashboardHealthProbeSpec {
    param(
        [string]$BaseUrl,
        [string]$ProjectRoot = ''
    )

    $base = $BaseUrl.TrimEnd('/')
    if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
        return [pscustomobject]@{
            Path = '/api/workbench/hub'
            Label = 'workbench-hub'
            Uri = ($base + '/api/workbench/hub')
        }
    }

    $encodedProjectRoot = [uri]::EscapeDataString($ProjectRoot)
    return [pscustomobject]@{
        Path = '/api/project/director-hub'
        Label = 'director-hub'
        Uri = ('{0}/api/project/director-hub?project_root={1}' -f $base, $encodedProjectRoot)
    }
}

function Get-WebnovelDashboardListener {
    param([int]$Port)

    try {
        return Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    } catch {
        return $null
    }
}

function Get-WebnovelDashboardProcessInfo {
    param([int]$ProcessId)

    if (-not $ProcessId) {
        return $null
    }

    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
    } catch {
        return $null
    }

    $commandLine = ''
    $executablePath = ''
    try {
        $cim = Get-CimInstance -ClassName Win32_Process -Filter ("ProcessId = {0}" -f $ProcessId) -ErrorAction Stop | Select-Object -First 1
        if ($cim) {
            $commandLine = [string]$cim.CommandLine
            $executablePath = [string]$cim.ExecutablePath
        }
    } catch {
        $commandLine = ''
        $executablePath = ''
    }

    return [pscustomobject]@{
        Id = $process.Id
        ProcessName = $process.ProcessName
        Path = $process.Path
        CommandLine = $commandLine
        ExecutablePath = $executablePath
    }
}

function Test-WebnovelDashboardProcessMatch {
    param(
        [pscustomobject]$ProcessInfo,
        [string]$WorkspaceRoot
    )

    if (-not $ProcessInfo) {
        return $false
    }

    $commandLine = Normalize-WebnovelText ([string]$ProcessInfo.CommandLine)
    if ($commandLine -notmatch 'dashboard\.server') {
        return $false
    }

    $workspaceRootText = Normalize-WebnovelPath $WorkspaceRoot
    if (-not $workspaceRootText) {
        return $true
    }

    $normalizedCommandLine = Normalize-WebnovelText ([string]$ProcessInfo.CommandLine)
    return $normalizedCommandLine -match ([regex]::Escape($workspaceRootText))
}

function Read-WebnovelHttpResponseBody {
    param($Response)

    if (-not $Response) {
        return ''
    }

    $stream = $null
    $reader = $null
    if ($Response.PSObject.Properties.Name -contains 'Content' -and $null -ne $Response.Content) {
        return [string]$Response.Content
    }

    try {
        $stream = $Response.GetResponseStream()
        if (-not $stream) {
            return ''
        }

        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8, $true, 1024, $true)
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } catch {
        return ''
    } finally {
        if ($stream) {
            $stream.Dispose()
        }
    }
}

function Convert-WebnovelDashboardProbeResult {
    param(
        [pscustomobject]$ProbeSpec,
        [string]$Uri,
        [int]$StatusCode,
        [string]$ContentType,
        [string]$Body,
        [string]$Source = 'response'
    )

    $contentTypeText = Normalize-WebnovelText $ContentType
    $bodyText = [string]$Body
    $trimmedBody = $bodyText.Trim()
    $looksLikeJson = $contentTypeText -match 'application/json' -or $contentTypeText -match '\+json' -or $trimmedBody -match '^[\{\[]'

    if (-not $looksLikeJson) {
        return [pscustomobject]@{
            Healthy = $false
            Reason = 'html_response'
            Uri = $Uri
            StatusCode = $StatusCode
            ContentType = $ContentType
            RawBody = $bodyText
            Source = $Source
            Message = ('{0} 返回了页面内容而不是 JSON 接口数据。' -f $ProbeSpec.Label)
        }
    }

    try {
        $payload = $trimmedBody | ConvertFrom-Json -ErrorAction Stop
        return [pscustomobject]@{
            Healthy = $true
            Reason = 'json_response'
            Uri = $Uri
            StatusCode = $StatusCode
            ContentType = $ContentType
            RawBody = $bodyText
            Source = $Source
            Payload = $payload
        }
    } catch {
        return [pscustomobject]@{
            Healthy = $false
            Reason = 'invalid_json'
            Uri = $Uri
            StatusCode = $StatusCode
            ContentType = $ContentType
            RawBody = $bodyText
            Source = $Source
            Message = ('{0} 未返回可解析的 JSON 数据。' -f $ProbeSpec.Label)
        }
    }
}

function Invoke-WebnovelDashboardProbeRequest {
    param([string]$Uri)

    $request = [System.Net.HttpWebRequest]::Create($Uri)
    $request.Method = 'GET'
    $request.Accept = 'application/json'
    $request.Timeout = 10000
    $request.ReadWriteTimeout = 10000
    $request.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
    try {
        $response = $request.GetResponse()
        try {
            return [pscustomobject]@{
                StatusCode = [int]$response.StatusCode
                ContentType = [string]$response.ContentType
                Body = Read-WebnovelHttpResponseBody $response
                Source = 'success'
                Message = ''
            }
        } finally {
            $response.Dispose()
        }
    } catch [System.Net.WebException] {
        $exception = $_.Exception
        $response = $exception.Response
        if ($response) {
            try {
                return [pscustomobject]@{
                    StatusCode = [int]$response.StatusCode
                    ContentType = [string]$response.ContentType
                    Body = Read-WebnovelHttpResponseBody $response
                    Source = 'error-response'
                    Message = [string]$exception.Message
                }
            } finally {
                $response.Dispose()
            }
        }
        return [pscustomobject]@{
            StatusCode = $null
            ContentType = ''
            Body = ''
            Source = 'exception'
            Message = [string]$exception.Message
        }
    } catch {
        return [pscustomobject]@{
            StatusCode = $null
            ContentType = ''
            Body = ''
            Source = 'exception'
            Message = [string]$_.Exception.Message
        }
    }
}

function Invoke-WebnovelDashboardHealthProbe {
    param(
        [string]$BaseUrl,
        [string]$ProjectRoot = ''
    )

    $probeSpec = Get-WebnovelDashboardHealthProbeSpec -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot
    $httpResult = Invoke-WebnovelDashboardProbeRequest -Uri $probeSpec.Uri

    if ($httpResult.StatusCode -eq $null) {
        return [pscustomobject]@{
            Healthy = $false
            Reason = 'request_failed'
            Uri = $probeSpec.Uri
            StatusCode = $null
            ContentType = ''
            RawBody = ''
            Source = $httpResult.Source
            Message = $httpResult.Message
            Path = $probeSpec.Path
            Label = $probeSpec.Label
        }
    }

    if ($httpResult.StatusCode -lt 200 -or $httpResult.StatusCode -ge 300) {
        return [pscustomobject]@{
            Healthy = $false
            Reason = 'unexpected_status'
            Uri = $probeSpec.Uri
            StatusCode = $httpResult.StatusCode
            ContentType = $httpResult.ContentType
            RawBody = $httpResult.Body
            Source = $httpResult.Source
            Message = ('{0} 返回了非成功状态：{1}。' -f $probeSpec.Label, $httpResult.StatusCode)
            Path = $probeSpec.Path
            Label = $probeSpec.Label
        }
    }

    $probeResult = Convert-WebnovelDashboardProbeResult -ProbeSpec $probeSpec -Uri $probeSpec.Uri -StatusCode $httpResult.StatusCode -ContentType $httpResult.ContentType -Body $httpResult.Body -Source $httpResult.Source
    $probeResult | Add-Member -NotePropertyName Path -NotePropertyValue $probeSpec.Path -Force
    $probeResult | Add-Member -NotePropertyName Label -NotePropertyValue $probeSpec.Label -Force
    return $probeResult
}

function Test-WebnovelDashboardWorkspaceProbeMatch {
    param(
        [string]$BaseUrl,
        [string]$WorkspaceRoot
    )

    $probe = Invoke-WebnovelDashboardHealthProbe -BaseUrl $BaseUrl
    $payload = $null
    if ($probe -and ($probe.PSObject.Properties.Name -contains 'Payload')) {
        $payload = $probe.Payload
    }
    $probeWorkspaceRoot = ''
    if ($payload -and $payload.workspace_root) {
        $probeWorkspaceRoot = Normalize-WebnovelPath ([string]$payload.workspace_root)
    }
    $expectedWorkspaceRoot = Normalize-WebnovelPath $WorkspaceRoot

    return [pscustomobject]@{
        Matches = ($probe.Healthy -and $probeWorkspaceRoot -and $expectedWorkspaceRoot -and ($probeWorkspaceRoot -eq $expectedWorkspaceRoot))
        Probe = $probe
    }
}

function Invoke-WebnovelDashboardDirectorHubProbe {
    param(
        [string]$BaseUrl,
        [string]$ProjectRoot
    )

    if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
        throw 'Invoke-WebnovelDashboardDirectorHubProbe 需要有效的 ProjectRoot。'
    }

    return Invoke-WebnovelDashboardHealthProbe -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot
}

function Resolve-WebnovelDashboardPortAction {
    param(
        [int]$Port,
        [string]$BaseUrl,
        [string]$WorkspaceRoot,
        [string]$ProjectRoot = ''
    )

    $listener = Get-WebnovelDashboardListener -Port $Port
    if (-not $listener) {
        return [pscustomobject]@{
            Action = 'start_new'
            Port = $Port
            BaseUrl = $BaseUrl
            BrowserUrl = Get-WebnovelDashboardBrowserUrl -Host ([System.Uri]$BaseUrl).Host -Port $Port
            ListenerProcessId = $null
            ListenerProcessName = ''
            ListenerCommandLine = ''
            SameService = $false
            Probe = $null
            Reason = 'port_free'
        }
    }

    $processInfo = Get-WebnovelDashboardProcessInfo -ProcessId $listener.OwningProcess
    if (-not $processInfo) {
        return [pscustomobject]@{
            Action = 'abort_port_in_use'
            Port = $Port
            BaseUrl = $BaseUrl
            BrowserUrl = Get-WebnovelDashboardBrowserUrl -Host ([System.Uri]$BaseUrl).Host -Port $Port
            ListenerProcessId = $listener.OwningProcess
            ListenerProcessName = ''
            ListenerCommandLine = ''
            SameService = $false
            Probe = $null
            Reason = 'port_in_use_unknown_owner'
        }
    }

    $sameService = Test-WebnovelDashboardProcessMatch -ProcessInfo $processInfo -WorkspaceRoot $WorkspaceRoot
    $probe = $null
    if (-not $sameService) {
        $workspaceProbe = Test-WebnovelDashboardWorkspaceProbeMatch -BaseUrl $BaseUrl -WorkspaceRoot $WorkspaceRoot
        if ($workspaceProbe.Matches) {
            $sameService = $true
            if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
                $probe = $workspaceProbe.Probe
            }
        }
    }

    if (-not $sameService) {
        return [pscustomobject]@{
            Action = 'abort_port_in_use'
            Port = $Port
            BaseUrl = $BaseUrl
            BrowserUrl = Get-WebnovelDashboardBrowserUrl -Host ([System.Uri]$BaseUrl).Host -Port $Port
            ListenerProcessId = $processInfo.Id
            ListenerProcessName = $processInfo.ProcessName
            ListenerCommandLine = $processInfo.CommandLine
            SameService = $false
            Probe = $null
            Reason = 'port_in_use_by_other_process'
        }
    }

    if (-not $probe) {
        $probe = Invoke-WebnovelDashboardHealthProbe -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot
    }
    $action = if ($probe.Healthy) { 'reuse_existing' } else { 'restart_existing' }

    return [pscustomobject]@{
        Action = $action
        Port = $Port
        BaseUrl = $BaseUrl
        BrowserUrl = Get-WebnovelDashboardBrowserUrl -Host ([System.Uri]$BaseUrl).Host -Port $Port
        ListenerProcessId = $processInfo.Id
        ListenerProcessName = $processInfo.ProcessName
        ListenerCommandLine = $processInfo.CommandLine
        SameService = $true
        Probe = $probe
        Reason = $probe.Reason
    }
}

function Stop-WebnovelDashboardProcess {
    param([int]$ProcessId)

    if (-not $ProcessId) {
        return
    }

    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    } catch {
        return
    }

    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        try {
            Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
            Start-Sleep -Milliseconds 200
        } catch {
            return
        }
    }
}

function Start-WebnovelDashboardServer {
    param(
        [string]$PythonExe,
        [string]$AppRoot,
        [string]$WorkspaceRoot,
        [string]$ProjectRoot,
        [string]$ListenHost = '127.0.0.1',
        [int]$Port = 8765
    )

    $argumentList = @(
        '-m',
        'dashboard.server',
        '--workspace-root',
        $WorkspaceRoot,
        '--host',
        $ListenHost,
        '--port',
        "$Port",
        '--no-browser'
    )

    if ($ProjectRoot) {
        $argumentList += @('--project-root', $ProjectRoot)
    }

    return Start-Process -FilePath $PythonExe -WorkingDirectory $AppRoot -ArgumentList $argumentList -PassThru -NoNewWindow
}

function Wait-WebnovelDashboardHealthy {
    param(
        [string]$BaseUrl,
        [string]$ProjectRoot = '',
        [int]$ProcessId = 0,
        [int]$TimeoutSeconds = 45,
        [int]$PollIntervalMilliseconds = 500
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastProbe = $null

    while ((Get-Date) -lt $deadline) {
        if ($ProcessId) {
            try {
                Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
            } catch {
                throw ('Dashboard 进程在健康检查完成前已退出（PID {0}）。请检查启动日志后重试。' -f $ProcessId)
            }
        }
        $lastProbe = Invoke-WebnovelDashboardHealthProbe -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot
        if ($lastProbe.Healthy) {
            return $lastProbe
        }

        Start-Sleep -Milliseconds $PollIntervalMilliseconds
    }

    $reason = if ($lastProbe) { $lastProbe.Reason } else { 'request_failed' }
    $message = if ($lastProbe -and $lastProbe.Message) {
        $lastProbe.Message
    } else {
        '健康检查未通过。'
    }

    if ($ProcessId) {
        try {
            Get-Process -Id $ProcessId -ErrorAction Stop | Out-Null
        } catch {
            throw ('Dashboard 进程在健康检查超时前已退出（PID {0}）。最后一次探测结果：{1}' -f $ProcessId, $message)
        }
    }

    $probePath = if ($lastProbe -and $lastProbe.Path) { $lastProbe.Path } else { (Get-WebnovelDashboardHealthProbeSpec -BaseUrl $BaseUrl -ProjectRoot $ProjectRoot).Path }
    throw ('Dashboard 启动后未通过 {0} 健康检查（{1}）：{2}' -f $probePath, $reason, $message)
}

Export-ModuleMember -Function `
    Get-WebnovelDashboardHealthProbeSpec, `
    Get-WebnovelDashboardBaseUrl, `
    Get-WebnovelDashboardBrowserUrl, `
    Resolve-WebnovelDashboardPortAction, `
    Start-WebnovelDashboardServer, `
    Stop-WebnovelDashboardProcess, `
    Wait-WebnovelDashboardHealthy
