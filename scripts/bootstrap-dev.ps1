[CmdletBinding()]
param(
    [switch]$SemTestes
)

$ErrorActionPreference = "Stop"
$raizProjeto = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $raizProjeto ".venv"
$pythonVenv = Join-Path $venv "Scripts\python.exe"

Push-Location $raizProjeto
try {
    if (-not (Test-Path -LiteralPath $pythonVenv)) {
        python -m venv $venv
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao criar .venv com o Python disponível no PATH."
        }
    }

    & $pythonVenv -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao atualizar pip."
    }

    & $pythonVenv -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar dependências. Encerre tjsp-api antes de repetir."
    }

    & $pythonVenv -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "Ambiente contém dependências incompatíveis."
    }

    if (-not $SemTestes) {
        & $pythonVenv -m ruff check .
        if ($LASTEXITCODE -ne 0) {
            throw "Ruff encontrou problemas."
        }
        & $pythonVenv -m pytest
        if ($LASTEXITCODE -ne 0) {
            throw "Testes falharam."
        }
    }

    Write-Host "Ambiente pronto: $pythonVenv"
}
finally {
    Pop-Location
}
