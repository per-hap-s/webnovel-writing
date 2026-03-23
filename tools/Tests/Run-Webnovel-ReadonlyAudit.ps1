[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [string]$OutputRoot,
    [int]$PreferredPort = 8765,
    [string]$ProjectRoot,
    [switch]$SkipBrowser
)

$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-ReadonlyAudit.psm1'
Import-Module $modulePath -Force

$config = Get-WebnovelReadonlyAuditConfig `
    -WorkspaceRoot $WorkspaceRoot `
    -OutputRoot $OutputRoot `
    -PreferredPort $PreferredPort `
    -ProjectRoot $ProjectRoot

$result = Invoke-WebnovelReadonlyAudit -Config $config -SkipBrowser:$SkipBrowser
$result | ConvertTo-Json -Depth 8
