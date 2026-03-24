[CmdletBinding()]
param(
    [string]$WorkspaceRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [string]$OutputRoot,
    [int]$PreferredPort = 8765,
    [string]$ProjectRoot,
    [string]$RunId,
    [string]$Title = 'Night Rain Rewind',
    [string]$Genre = 'Urban Supernatural'
)

$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-RealE2E.psm1'
Import-Module $modulePath -Force

$config = Get-WebnovelRealE2EConfig `
    -WorkspaceRoot $WorkspaceRoot `
    -OutputRoot $OutputRoot `
    -PreferredPort $PreferredPort `
    -ProjectRoot $ProjectRoot `
    -RunId $RunId `
    -Title $Title `
    -Genre $Genre

$result = Invoke-WebnovelRealE2E -Config $config
$result | ConvertTo-Json -Depth 10
