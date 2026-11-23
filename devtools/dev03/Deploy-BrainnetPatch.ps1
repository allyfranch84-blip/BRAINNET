[CmdletBinding(DefaultParameterSetName='Preview')]
param(
    [Parameter(ParameterSetName='Preview')][switch]$Preview,
    [Parameter(Mandatory,ParameterSetName='Apply')][switch]$Apply,
    [Parameter(Mandatory,ParameterSetName='Apply')][string]$PlanHash,
    [Parameter(Mandatory,ParameterSetName='Rollback')][string]$Rollback,
    [Parameter(ParameterSetName='Preview')][Parameter(ParameterSetName='Apply')][string]$Manifest,
    [string]$Source = 'A:\BRAINNET\BRAINNET',
    [string]$Destination = 'A:\BRAINNET',
    [string]$BackupRoot = 'A:\BRAINNET\BRAIN\development_logs\deployments',
    [string]$GitPath,
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'

function Test-NativeCommand([string]$Executable, [string[]]$Arguments) {
    try {
        & $Executable @Arguments 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Resolve-Executable([string]$Value, [string]$Label) {
    if (-not [IO.Path]::IsPathRooted($Value) -or -not (Test-Path -LiteralPath $Value -PathType Leaf)) {
        throw "$Label deve ser um caminho absoluto para um executável existente."
    }
    return (Get-Item -LiteralPath $Value).FullName
}

if ($GitPath) {
    $gitExecutable = Resolve-Executable $GitPath 'GitPath'
} else {
    $gitExecutable = $null
    $desktopRoots = @($env:LOCALAPPDATA)
    if ($env:USERPROFILE) { $desktopRoots += (Join-Path $env:USERPROFILE 'AppData\Local') }
    $desktopRoots = $desktopRoots | Select-Object -Unique
    foreach ($desktopRoot in $desktopRoots) {
        if (-not $desktopRoot) { continue }
        $desktop = Join-Path $desktopRoot 'GitHubDesktop'
        $apps = @(Get-ChildItem -LiteralPath $desktop -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^app-\d+(\.\d+)+$' } |
            Sort-Object { [version]($_.Name.Substring(4)) } -Descending)
        foreach ($app in $apps) {
            $candidate = Join-Path $app.FullName 'resources\app\git\cmd\git.exe'
            if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-NativeCommand $candidate @('--version'))) {
                $gitExecutable = $candidate; break
            }
        }
        if ($gitExecutable) { break }
    }
    if (-not $gitExecutable) {
        $found = Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $gitExecutable = $found.Source }
    }
}
if (-not $gitExecutable -or -not (Test-NativeCommand $gitExecutable @('--version'))) {
    throw 'Git indisponível. Informe -GitPath com o caminho absoluto do git.exe confiável.'
}

$pythonPrefix = @()
if ($PythonPath) {
    $pythonExecutable = Resolve-Executable $PythonPath 'PythonPath'
} else {
    $pythonExecutable = $null
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher -and (Test-NativeCommand $launcher.Source @('-3.12', '-c', 'import sys; assert sys.version_info >= (3, 10)'))) {
        $pythonExecutable = $launcher.Source; $pythonPrefix = @('-3.12')
    }
    if (-not $pythonExecutable -and $env:USERPROFILE) {
        $candidate = Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python312\python.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $pythonExecutable = $candidate }
    }
    if (-not $pythonExecutable) {
        $found = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $pythonExecutable = $found.Source }
    }
}
if (-not $pythonExecutable -or -not (Test-NativeCommand $pythonExecutable ($pythonPrefix + @('-c', 'import sys; assert sys.version_info >= (3, 10)')))) {
    throw 'Python 3.10+ indisponível. Informe -PythonPath com o caminho absoluto de um Python confiável.'
}

$script = Join-Path $PSScriptRoot 'patch_control.py'
$argsList = $pythonPrefix + @($script, '--git-executable', $gitExecutable, '--source', $Source, '--destination', $Destination, '--backup-root', $BackupRoot)
if ($Rollback) { $argsList += @('--rollback', $Rollback) }
else {
    if (-not $Manifest) { throw 'Informe -Manifest para gerar a prévia.' }
    $argsList += @('--manifest', $Manifest)
    if ($Apply) { $argsList += @('--apply', '--plan-hash', $PlanHash) }
}
& $pythonExecutable @argsList
exit $LASTEXITCODE
