# Script de inicializacao do sistema Juris (API + Frontend React)
Param(
    [int]$PortaApi = 8000,
    [int]$PortaFront = 3000
)

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Juris - Pesquisa e RAG Juridico Nacional" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Verifica ambiente virtual
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Ambiente virtual nao encontrado em .venv."
    exit 1
}

# 1. Inicia API FastAPI em segundo plano
Write-Host "[1/2] Iniciando Backend FastAPI (porta $PortaApi)..." -ForegroundColor Yellow
$jobApi = Start-Process -FilePath $python -ArgumentList "-m", "scraping_tjsp.api_cli", "--porta", "$PortaApi", "--reload" -PassThru -NoNewWindow

Start-Sleep -Seconds 2

# 2. Inicia Frontend Vite
Write-Host "[2/2] Iniciando Frontend React (porta $PortaFront)..." -ForegroundColor Green
Write-Host "App disponivel em: http://localhost:$PortaFront" -ForegroundColor Cyan
Write-Host "Pressione Ctrl+C para encerrar." -ForegroundColor Gray

Set-Location (Join-Path $raiz "frontend")
try {
    npm run dev
} finally {
    Write-Host "Encerrando Backend..." -ForegroundColor Yellow
    if ($jobApi) {
        Stop-Process -Id $jobApi.Id -Force -ErrorAction SilentlyContinue
    }
}
