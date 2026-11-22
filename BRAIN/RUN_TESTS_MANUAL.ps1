
# BRAINNET — Testes manuais com allowlist
# Execute somente apos revisar a lista de testes seguros
# e fechar a BRAINNET e o self_inspector.

$ErrorActionPreference = "Stop"
$root = "A:\BRAINNET\BRAIN"

Set-Location $root

$allowlist = Join-Path $root "development_logs\approved_test_paths.txt"

if (-not (Test-Path -LiteralPath $allowlist)) {
    throw "Allowlist nao encontrada. Solicite ao Codex a auditoria."
}

$testFiles = @(
    Get-Content -LiteralPath $allowlist |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith("#") }
)

if ($testFiles.Count -eq 0) {
    throw "Nenhum teste foi aprovado na allowlist."
}

# Nao aceitar caminhos externos ou diretorios inteiros
foreach ($file in $testFiles) {
    if (
        [IO.Path]::IsPathRooted($file) -or
        $file.Contains("..") -or
        -not $file.EndsWith(".py")
    ) {
        throw "Caminho de teste invalido: $file"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) {
        throw "Arquivo nao encontrado: $file"
    }
}

# Inspecao preventiva de processos; confirme tambem manualmente
$active = @(
    Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and
        $_.CommandLine -match 'BRAINNET|self_inspector'
    }
)

if ($active.Count -gt 0) {
    $active | Select-Object ProcessId, Name, CommandLine | Format-List
    throw "Possivel Kernel ou autoinspecao ativa. Encerre antes de testar."
}

# Reduzir efeitos de plugins e arquivos de cache do pytest
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "development_logs\manual_pytest_$stamp.txt"

Write-Host "Executando $($testFiles.Count) arquivos auditados."
Write-Host "Log: $log"

& py -3.12 -B -m pytest -q `
    -p no:cacheprovider `
    --tb=short `
    --maxfail=1 `
    @testFiles 2>&1 | Tee-Object -FilePath $log

$code = $LASTEXITCODE

"Exit code: $code" |
    Add-Content -LiteralPath $log

Write-Host "Resultado registrado: $log"
Write-Host "Exit code: $code"

if ($code -ne 0) {
    Write-Warning "Houve falha ou erro. Consulte o log."
}
