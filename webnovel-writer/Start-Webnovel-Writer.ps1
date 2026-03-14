param(
    [ValidateSet('menu', 'dashboard', 'dashboard-lan', 'login', 'shell', 'readme', 'help')]
    [string]$Action = 'menu',
    [string]$ProjectRoot,
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$repoRoot = $PSScriptRoot
$dashboardLauncher = Join-Path $repoRoot 'Launch-Webnovel-Dashboard.ps1'
$loginLauncher = Join-Path $repoRoot 'Login-Codex-CLI.ps1'
$guideSourcePath = Join-Path $repoRoot 'Quick-Start-CN.txt'
$guidePath = Join-Path $env:TEMP 'webnovel-writer-quick-start-cn.txt'
$guideTemplateBase64 = 'V2Vibm92ZWwgV3JpdGVyIOWQr+WKqOivtOaYjg0KPT09PT09PT09PT09PT09PT09PT09PT09DQoNCuS4gOOAgeS4u+iPnOWNleaAjuS5iOeUqA0KDQoxLiDlkK/liqggRGFzaGJvYXJkDQogICDlnKjmnKzmnLrmiZPlvIAgV2ViIOmdouadv+OAgg0KICAg6YCC5ZCI77ya5Y+q5Zyo5b2T5YmN55S16ISR5LiK5L2/55So44CCDQogICDmiZPlvIDlkI7lnLDlnYDpgJrluLjmmK8gaHR0cDovLzEyNy4wLjAuMTo4NzY1DQoNCjIuIOWQr+WKqCBEYXNoYm9hcmTvvIjlsYDln5/nvZHorr/pl67vvIkNCiAgIOWcqOacrOacuuWQr+WKqOmdouadv++8jOWQjOaXtuWFgeiuuOaJi+acuuWSjOWQjOS4gOWxgOWfn+e9keiuvuWkh+iuv+mXruOAgg0KICAg6YCC5ZCI77ya5oOz55So5omL5py65p+l55yL77yM5oiW6ICF5Zyo5ZCM5LiA572R57uc6YeM55qE5YW25LuW6K6+5aSH5LiK5omT5byA44CCDQogICDmiZPlvIDlkI7pmaTkuobmnKzmnLrlnLDlnYDvvIzov5jkvJrmmL7npLrkuIDkuKrlsYDln5/nvZHlnLDlnYDvvIzkvovlpoIgaHR0cDovLzE5Mi4xNjgueC54Ojg3NjUNCiAgIOaPkOmGku+8mumcgOimgeeUteiEkeWSjOaJi+acuuWcqOWQjOS4gOWxgOWfn+e9ke+8jOS4lOmYsueBq+WimeWFgeiuuOivpeerr+WPo+OAgg0KDQozLiDnmbvlvZUgQ29kZXggQ0xJDQogICDmiZPlvIDnmbvlvZXnqpflj6PvvIzmiafooYwgQ29kZXggQ0xJIOeZu+W9le+8jOW5tuajgOafpeW9k+WJjeeZu+W9leeKtuaAgeOAgg0KICAg6YCC5ZCI77ya56ys5LiA5qyh5L2/55So77yM5oiW55m75b2V5aSx5pWI5ZCO6YeN5paw55m75b2V44CCDQoNCjQuIOaJk+W8gOe7iOerrw0KICAg5omT5byA5LiA5Liq5bey57uP5a6a5L2N5Yiw6aG555uu55uu5b2V55qEIFBvd2VyU2hlbGwg56qX5Y+j44CCDQogICDpgILlkIjvvJrmiYvliqjov5DooYzlkb3ku6TjgIHmn6XnnIvml6Xlv5fjgIHmjpLmn6Xpl67popjjgIINCg0KNS4g5omT5byA5ZCv5Yqo6K+05piODQogICDnlKjorrDkuovmnKzmiZPlvIDov5nku73kuK3mlofor7TmmI7jgIINCiAgIOi/memHjOS4jeS8muWGjeaJk+W8gCBSRUFETUUubWTjgIINCg0K5LqM44CB5o6o6I2Q5L2/55So6aG65bqPDQoNCjEuIOWmguaenOi/mOayoeeZu+W9le+8jOWFiOmAiSAzIOeZu+W9lSBDb2RleCBDTEnjgIINCjIuIOeEtuWQjumAiSAxIOaIliAyIOWQr+WKqCBEYXNoYm9hcmTjgIINCjMuIOWcqOa1j+iniOWZqOmHjOaJk+W8gOmdouadv+WQju+8jOWFiOeci+KAnOaAu+iniOKAnemhteehruiupOmhueebruOAgeWGmeS9nOaooeWei+WSjCBSQUcg54q25oCB44CCDQo0LiDlho3ljrvigJzku7vliqHigJ3pobXlj5HotbfmiJbot5/ouKrku7vliqHjgIINCg0K5LiJ44CBV2ViIOmdouadv+aAjuS5iOeUqA0KDQoxLiDmgLvop4gNCiAgIOafpeeci+mhueebruWQjeensOOAgemimOadkOOAgeaAu+Wtl+aVsOOAgeW9k+WJjeeroOiKguOAgeWGmeS9nOaooeWei+WSjCBSQUcg54q25oCB44CCDQogICDov5nph4zkuZ/og73liJvlu7rpobnnm67vvIzmiJblj5HotbfigJzliIbmnpDnjrDmnInpobnnm67igJ3jgIHigJzop4TliJLljbfigJ3jgIHigJzmkrDlhpnnq6DoioLigJ3jgIHigJzmiafooYzlrqHmn6XigJ3jgIHigJzmgaLlpI3mtYHnqIvigJ3ku7vliqHjgIINCg0KMi4g5Lu75YqhDQogICDlt6bkvqfmmK/ku7vliqHliJfooajvvIzlj7PkvqfmmK/ku7vliqHor6bmg4XjgIINCiAgIOWPr+S7peafpeeci+eKtuaAgeOAgeW9k+WJjeatpemqpOOAgeWuoeaJueeKtuaAgeOAgeatpemqpOi+k+WHuuWSjOS6i+S7tua1geOAgg0KICAg5aaC5p6c5Lu75Yqh6L+b5YWl4oCc562J5b6F5Zue5YaZ5a6h5om54oCd77yM5bCx5Zyo6L+Z6YeM5om55YeG5oiW5ouS57ud44CCDQoNCjMuIOaVsOaNrg0KICAg5p+l55yL5a6e5L2T44CB5YWz57O744CB56ug6IqC562J57uT5p6E5YyW5pWw5o2u44CCDQogICDpgILlkIjmo4Dmn6XkurrnianjgIHkuJbnlYzop4Llkoznq6DoioLmlbDmja7mmK/lkKblkIzmraXjgIINCg0KNC4g5paH5Lu2DQogICDmtY/op4jpobnnm67mlofmoaPmoJHvvIzlubbmn6XnnIvmlofku7blhoXlrrnjgIINCiAgIOmAguWQiOW/q+mAn+aguOWvueeroOiKguOAgemFjee9ruWSjOS7u+WKoei+k+WHuuOAgg0KDQo1LiDotKjph48NCiAgIOafpeeci+WkseaViOS6i+WunuWuoeaJueOAgeWuoeafpeaMh+agh+OAgea4heWNleivhOWIhuOAgVJBRyDmn6Xor6LorrDlvZXlkozlt6Xlhbfnu5/orqHjgIINCiAgIOmAguWQiOaOkuafpei0qOmHj+mXrumimOOAgeWbnueci+ajgOe0ouaDheWGteWSjOehruiupOW8guW4uOOAgg0KDQrlm5vjgIHluLjop4Hmg4XlhrUNCg0KLSDpgInmi6kgMSDliLAgNSDlkI7vvIzlvZPliY3oj5zljZXnqpflj6PkvJrkv53nlZnvvJvmjInlm57ovabkvJrlm57liLDkuLvoj5zljZXjgIINCi0gUkVBRE1FLm1kIOS5i+WJjeS8muiiqyBUcmFlQ04g5omT5byA77yM5piv5Zug5Li6IFdpbmRvd3Mg5oqKIC5tZCDpu5jorqTlhbPogZTliLDkuoYgVHJhZUNO77yM5LiN5piv5pys6aG555uu5by65Yi25oyH5a6a55qE44CCDQotIOWmguaenOivtOaYjuWGjeasoeWHuueOsOS5seegge+8jOWFiOWFs+aOieaXp+eahOiusOS6i+acrOeql+WPo++8jOWGjeS7juiPnOWNlemHjeaWsOaJk+W8gOOAgg0K'

function T([string]$Codes) {
    return -join (($Codes -split ' ') | ForEach-Object { [char][Convert]::ToInt32($_, 16) })
}

$textNotFound = T '672A 627E 5230'
$textDashboardScript = 'Dashboard ' + (T '542F 52A8 811A 672C')
$textLoginScript = 'Codex CLI ' + (T '767B 5F55 811A 672C')
$textLauncherTitle = 'Webnovel Writer ' + (T '542F 52A8 5668')
$textStartDashboard = (T '542F 52A8') + ' Dashboard'
$textStartDashboardLan = (T '542F 52A8') + ' Dashboard' + [char]0xFF08 + (T '5C40 57DF 7F51 8BBF 95EE') + [char]0xFF09
$textLoginCodex = (T '767B 5F55') + ' Codex CLI'
$textOpenShell = T '6253 5F00 7EC8 7AEF'
$textOpenGuide = (T '6253 5F00') + (T '542F 52A8 8BF4 660E')
$textQuit = T '9000 51FA'
$textPrompt = (T '8BF7 9009 62E9 64CD 4F5C') + ' [1]'
$textInvalidChoice = (T '65E0 6548 9009 62E9') + [char]0xFF0C + (T '6309 56DE 8F66 540E 91CD 8BD5') + [char]0x3002
$textPressEnterReturn = (T '6309 56DE 8F66 8FD4 56DE 4E3B 83DC 5355') + [char]0x3002
$textDashboardStarted = 'Dashboard ' + (T '5DF2 542F 52A8') + [char]0xFF0C + $textPressEnterReturn
$textDashboardLanStarted = 'Dashboard' + [char]0xFF08 + (T '5C40 57DF 7F51') + [char]0xFF09 + (T '5DF2 542F 52A8') + [char]0xFF0C + $textPressEnterReturn
$textLoginStarted = 'Codex CLI ' + (T '767B 5F55 7A97 53E3 5DF2 542F 52A8') + [char]0xFF0C + $textPressEnterReturn
$textShellStarted = (T '7EC8 7AEF 7A97 53E3 5DF2 6253 5F00') + [char]0xFF0C + $textPressEnterReturn
$textGuideOpened = (T '542F 52A8 8BF4 660E') + (T '5DF2 5728 8BB0 4E8B 672C 4E2D 6253 5F00') + [char]0xFF0C + $textPressEnterReturn
$textUsage = (T '7528 6CD5') + [char]0xFF1A
$textUnsupportedAction = (T '4E0D 652F 6301 7684 52A8 4F5C') + [char]0xFF1A

function Test-LauncherExists([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path)) {
        throw ($textNotFound + $Label + [char]0xFF1A + $Path)
    }
}

function Start-DashboardWindow([switch]$LanMode) {
    Test-LauncherExists $dashboardLauncher $textDashboardScript

    $argList = @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-File', "`"$dashboardLauncher`"",
        '-Port', $Port
    )

    if ($ProjectRoot) {
        $argList += @('-ProjectRoot', "`"$ProjectRoot`"")
    }
    if ($NoBrowser) {
        $argList += '-NoBrowser'
    }
    if ($LanMode) {
        $argList += '-Lan'
    }

    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList $argList | Out-Null
}

function Start-LoginWindow {
    Test-LauncherExists $loginLauncher $textLoginScript
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-File', "`"$loginLauncher`""
    ) | Out-Null
}

function Start-ProjectShell {
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $repoRoot -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command', "Set-Location -LiteralPath '$repoRoot'"
    ) | Out-Null
}

function Get-GuideContent {
    if (Test-Path $guideSourcePath) {
        return Get-Content -LiteralPath $guideSourcePath -Raw -Encoding UTF8
    }
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($guideTemplateBase64))
}

function Open-Guide {
    $content = Get-GuideContent
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($guidePath, $content, $utf8Bom)
    Start-Process -FilePath 'notepad.exe' -ArgumentList "`"$guidePath`"" | Out-Null
}

function Pause-ForReturn([string]$Message) {
    Write-Host
    [void](Read-Host $Message)
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host $textLauncherTitle
        Write-Host '======================'
        Write-Host ('1. ' + $textStartDashboard)
        Write-Host ('   ' + (T '5728 672C 673A 542F 52A8 9762 677F'))
        Write-Host ('2. ' + $textStartDashboardLan)
        Write-Host ('   ' + (T '5141 8BB8 624B 673A 6216 5C40 57DF 7F51 8BBF 95EE'))
        Write-Host ('3. ' + $textLoginCodex)
        Write-Host ('   ' + (T '6267 884C 767B 5F55 5E76 68C0 67E5 72B6 6001'))
        Write-Host ('4. ' + $textOpenShell)
        Write-Host ('   ' + (T '6253 5F00 5B9A 4F4D 5230 9879 76EE 76EE 5F55 7684 7EC8 7AEF'))
        Write-Host ('5. ' + $textOpenGuide)
        Write-Host ('   ' + (T '7528 8BB0 4E8B 672C 6253 5F00 8BE6 7EC6 4E2D 6587 8BF4 660E'))
        Write-Host ('Q. ' + $textQuit)
        Write-Host

        $choice = (Read-Host $textPrompt).Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($choice)) {
            $choice = '1'
        }

        switch ($choice) {
            '1' { Start-DashboardWindow; Pause-ForReturn $textDashboardStarted; continue }
            '2' { Start-DashboardWindow -LanMode; Pause-ForReturn $textDashboardLanStarted; continue }
            '3' { Start-LoginWindow; Pause-ForReturn $textLoginStarted; continue }
            '4' { Start-ProjectShell; Pause-ForReturn $textShellStarted; continue }
            '5' { Open-Guide; Pause-ForReturn $textGuideOpened; continue }
            'q' { return }
            default {
                Write-Host
                Write-Host $textInvalidChoice
                [void](Read-Host)
            }
        }
    }
}

function Show-Help {
    Write-Host $textUsage
    Write-Host '  Start-Webnovel-Writer.bat'
    Write-Host '  Start-Webnovel-Writer.bat dashboard'
    Write-Host '  Start-Webnovel-Writer.bat dashboard-lan'
    Write-Host '  Start-Webnovel-Writer.bat login'
    Write-Host '  Start-Webnovel-Writer.bat shell'
    Write-Host '  Start-Webnovel-Writer.bat readme'
}

switch ($Action) {
    'menu' { Show-Menu }
    'dashboard' { Start-DashboardWindow }
    'dashboard-lan' { Start-DashboardWindow -LanMode }
    'login' { Start-LoginWindow }
    'shell' { Start-ProjectShell }
    'readme' { Open-Guide }
    'help' { Show-Help }
    default { throw ($textUnsupportedAction + $Action) }
}

