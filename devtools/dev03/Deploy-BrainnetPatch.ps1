[CmdletBinding(DefaultParameterSetName='Preview')]
param(
    [Parameter(ParameterSetName='Preview')][switch]$Preview,
    [Parameter(Mandatory,ParameterSetName='Apply')][switch]$Apply,
    [Parameter(Mandatory,ParameterSetName='Apply')][string]$PlanHash,
    [Parameter(Mandatory,ParameterSetName='Rollback')][string]$Rollback,
    [Parameter(ParameterSetName='Preview')][Parameter(ParameterSetName='Apply')][string]$Manifest,
    [string]$Source = 'A:\BRAINNET\BRAINNET',
    [string]$Destination = 'A:\BRAINNET',
    [string]$BackupRoot = 'A:\BRAINNET\BRAIN\development_logs\deployments'
)
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'patch_control.py'
$argsList = @($script, '--source', $Source, '--destination', $Destination, '--backup-root', $BackupRoot)
if ($Rollback) { $argsList += @('--rollback', $Rollback) }
else {
    if (-not $Manifest) { throw 'Informe -Manifest para gerar a prévia.' }
    $argsList += @('--manifest', $Manifest)
    if ($Apply) { $argsList += @('--apply', '--plan-hash', $PlanHash) }
}
& python @argsList
exit $LASTEXITCODE
