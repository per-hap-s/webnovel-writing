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

$modulePath = Join-Path $PSScriptRoot '..\Webnovel-MultiAgentTest.psm1'
Import-Module $modulePath -Force

$config = Get-WebnovelMultiAgentTestConfig `
    -WorkspaceRoot $WorkspaceRoot `
    -OutputRoot $OutputRoot `
    -PreferredPort $PreferredPort `
    -ProjectRoot $ProjectRoot `
    -RunId $RunId `
    -Title $Title `
    -Genre $Genre

$result = Invoke-WebnovelMultiAgentTest -Config $config
$result | ConvertTo-Json -Depth 12
