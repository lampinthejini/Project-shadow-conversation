<#
.SYNOPSIS
    집 PC에서 0단계 LLM 측정(S0-01, S0-03~05)을 한 번에 돌린다.

.DESCRIPTION
    절차서: docs/그림자 대화 0단계 기술 검증 절차서 v0.1.md

    하는 일
      1. Python·Ollama 확인, 환경 기록(S0-01)
      2. 모델이 받아져 있는지 확인 (없으면 안내만 하고 멈춘다. 라이선스 확인 뒤 직접 받는다)
      3. 실행 중인 Ollama(트레이 앱 포함)를 끄고, 병렬 슬롯 1개로 띄워 ctx·prefix·judge 측정
      4. 병렬 슬롯 2개로 다시 띄워 judge 측정
      5. 이 스크립트가 띄운 Ollama를 끈다. 트레이 앱은 다시 켜지 않는다

    손으로 적을 것(S0-02): 작업 관리자의 전용 GPU 메모리, 측정 중 'ollama ps'의 PROCESSOR 열

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\stage0\run_home.ps1
    powershell -ExecutionPolicy Bypass -File tools\stage0\run_home.ps1 -Model exaone3.5:7.8b -Repeats 3
#>
param(
    [string]$Model = "exaone3.5:7.8b",
    [int]$Repeats = 5,
    [int]$JudgeRepeats = 10,
    [int]$NumCtx = 16384,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bench = Join-Path $here "bench_llm.py"
$envInfo = Join-Path $here "env_info.py"
$baseUrl = "http://127.0.0.1:11434"

function Write-Step([string]$text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

function Stop-Ollama {
    foreach ($name in @("ollama app", "ollama")) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
    }
    Start-Sleep -Seconds 2
}

function Start-OllamaServe([int]$numParallel) {
    Stop-Ollama
    $env:OLLAMA_NUM_PARALLEL = "$numParallel"
    $env:OLLAMA_CONTEXT_LENGTH = "$NumCtx"
    $env:OLLAMA_DEBUG = "0"
    $process = Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -PassThru
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Invoke-WebRequest -Uri "$baseUrl/api/version" -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $process
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Ollama가 60초 안에 응답하지 않았다."
}

function Invoke-Bench([string]$experiments, [int]$repeats, [string]$note) {
    & $Python $bench --api ollama --model $Model --experiments $experiments `
        --repeats $repeats --num-ctx $NumCtx --note $note
    if ($LASTEXITCODE -ne 0) { throw "bench_llm.py 실패 ($note)" }
}

Write-Step "1. 도구 확인"
& $Python -c "import sys; assert sys.version_info >= (3, 10), sys.version; print('Python', sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 이상이 필요하다." }
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw "ollama를 찾을 수 없다. 설치 뒤 다시 실행한다." }
ollama --version

Write-Step "S0-01 환경 기록"
& $Python $envInfo
Write-Host "NVIDIA가 아니면 VRAM 총량은 작업 관리자 > 성능 > GPU에서 손으로 적는다." -ForegroundColor Yellow

Write-Step "2. 모델 확인"
$listed = (ollama list) -join "`n"
if ($listed -notmatch [regex]::Escape($Model)) {
    Write-Host "모델 '$Model' 이 없다. 라이선스 원문(S0-13)을 확인한 뒤 아래 명령으로 받고 다시 실행한다." -ForegroundColor Yellow
    Write-Host "    ollama pull $Model"
    exit 1
}

$serve = $null
try {
    Write-Step "3. 병렬 슬롯 1개: S0-03 ctx, S0-04 prefix, S0-05 judge"
    $serve = Start-OllamaServe 1
    Invoke-Bench "ctx,prefix,judge" $Repeats "NUM_PARALLEL=1"
    Write-Host "지금 작업 관리자의 GPU 메모리를 적는다(모델이 5분간 적재된 채로 있다)." -ForegroundColor Yellow
    ollama ps

    Write-Step "4. 병렬 슬롯 2개: S0-05 judge"
    $serve = Start-OllamaServe 2
    Invoke-Bench "judge" $JudgeRepeats "NUM_PARALLEL=2"
    Write-Host "슬롯 2개 설정의 GPU 메모리도 적는다(S0-02)." -ForegroundColor Yellow
    ollama ps
    Read-Host "VRAM을 다 적었으면 Enter (이 스크립트가 띄운 Ollama를 끈다)"
} finally {
    if ($serve) { Stop-Ollama }
    Remove-Item Env:OLLAMA_NUM_PARALLEL, Env:OLLAMA_CONTEXT_LENGTH, Env:OLLAMA_DEBUG -ErrorAction SilentlyContinue
}

Write-Step "끝"
Write-Host "결과: $(Join-Path $here 'results')"
Write-Host "트레이 앱은 꺼진 상태다. 필요하면 시작 메뉴에서 Ollama를 다시 켠다."
Write-Host "S0-06(생성 취소·로깅)과 S0-13(라이선스)은 절차서대로 손으로 한다."
