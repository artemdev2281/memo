#Requires -Version 5.1
<#
.SYNOPSIS
    Запуск memo с нуля: проверка зависимостей, установка пакетов, старт приложения.

.DESCRIPTION
    Скрипт:
      1. Проверяет обязательные внешние программы (Ollama, Python 3.11+, Node.js 18+, Rust/cargo)
      2. Запускает Ollama serve, если не запущена
      3. Загружает нужные модели, если их нет
      4. Создаёт Python venv и устанавливает зависимости backend
      5. Устанавливает npm-зависимости frontend
      6. Запускает приложение через `npm run tauri dev`

    Запуск (при необходимости разрешить скрипты):
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
        .\start.ps1

    Параметры:
        -SkipModelPull   Не скачивать модели Ollama (если уже скачаны)
        -SkipInstall     Не устанавливать/обновлять зависимости Python и npm
#>

param(
    [switch]$SkipModelPull,
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Цвета вывода ─────────────────────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "`n[ОШИБКА] $msg" -ForegroundColor Red }

# ── Пути ─────────────────────────────────────────────────────────────────────
$Root        = $PSScriptRoot
$BackendDir  = Join-Path $Root 'src\backend'
$FrontendDir = Join-Path $Root 'src\frontend'
$VenvDir     = Join-Path $BackendDir '.venv'
$VenvPython  = Join-Path $VenvDir 'Scripts\python.exe'
$VenvPip     = Join-Path $VenvDir 'Scripts\pip.exe'

# ─────────────────────────────────────────────────────────────────────────────
# 1. ПРОВЕРКА ВНЕШНИХ ЗАВИСИМОСТЕЙ
# ─────────────────────────────────────────────────────────────────────────────
Write-Step 'Проверка внешних зависимостей'

$missing = @()

# Ollama
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $missing += 'ollama'
    Write-Warn 'ollama не найдена'
} else {
    Write-Ok 'ollama'
}

# Python 3.11+
$pythonCmd = $null
foreach ($cmd in @('python', 'python3', 'py')) {
    $p = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($p) {
        $ver = & $cmd --version 2>&1
        if ($ver -match 'Python (\d+)\.(\d+)') {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 11) {
                $pythonCmd = $cmd
                Write-Ok "Python ($ver)"
                break
            }
        }
    }
}
if (-not $pythonCmd) {
    $missing += 'python3.11+'
    Write-Warn 'Python 3.11+ не найден'
}

# Node.js 18+
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = (node --version) -replace 'v',''
    $nodeMajor = [int]($nodeVer.Split('.')[0])
    if ($nodeMajor -ge 18) {
        Write-Ok "Node.js v$nodeVer"
    } else {
        $missing += 'nodejs18+'
        Write-Warn "Node.js v$nodeVer — нужна версия 18+"
    }
} else {
    $missing += 'nodejs'
    Write-Warn 'Node.js не найден'
}

# Rust / cargo (нужен для компиляции Tauri)
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    $cargoVer = cargo --version
    Write-Ok "cargo ($cargoVer)"
} else {
    $missing += 'rust'
    Write-Warn 'cargo (Rust) не найден'
}

if ($missing.Count -gt 0) {
    Write-Fail "Не установлены обязательные программы: $($missing -join ', ')"
    Write-Host @'

  Установите их вручную:

  Ollama      — https://ollama.com/download          (кнопка «Download for Windows»)
  Python 3.11 — https://www.python.org/downloads/    (выберите 3.11 или новее)
                При установке отметьте "Add Python to PATH"
  Node.js 18+ — https://nodejs.org/                  (LTS-версия)
  Rust        — https://rustup.rs/                   (запустите rustup-init.exe)
                После установки перезапустите терминал.

  Затем снова запустите .\start.ps1
'@
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. ЗАПУСК OLLAMA SERVE
# ─────────────────────────────────────────────────────────────────────────────
Write-Step 'Ollama serve'

$ollamaRunning = $false
try {
    $resp = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -ErrorAction Stop
    $ollamaRunning = $true
    Write-Ok 'Ollama уже запущена'
} catch {
    Write-Host '    Запускаю ollama serve в фоне...'
    Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden
    # Ждём до 20 секунд пока API станет доступным
    $waited = 0
    while ($waited -lt 20) {
        Start-Sleep -Seconds 2; $waited += 2
        try {
            Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 2 -ErrorAction Stop | Out-Null
            $ollamaRunning = $true
            Write-Ok 'Ollama запущена'
            break
        } catch {}
    }
    if (-not $ollamaRunning) {
        Write-Fail 'Ollama не ответила за 20 секунд. Проверьте установку.'
        exit 1
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. МОДЕЛИ OLLAMA
# ─────────────────────────────────────────────────────────────────────────────
Write-Step 'Модели Ollama'

# Обязательные: bge-m3 (эмбеддинги), qwen3:1.7b (авто-организация)
# Рекомендуемая: qwen3:4b (чат)
$requiredModels = @('bge-m3', 'qwen3:1.7b')
$optionalModels = @('qwen3:4b')

if ($SkipModelPull) {
    Write-Warn 'Пропуск загрузки моделей (-SkipModelPull)'
} else {
    try {
        $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -ErrorAction Stop
        $installedModels = $tags.models | ForEach-Object { $_.name }
    } catch {
        $installedModels = @()
    }

    foreach ($model in $requiredModels) {
        $found = $installedModels | Where-Object { $_ -like "$model*" }
        if ($found) {
            Write-Ok "$model (установлена)"
        } else {
            Write-Host "    Загружаю $model (обязательная)..."
            ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "Не удалось загрузить $model — индексация работать не будет"
                exit 1
            }
            Write-Ok "$model загружена"
        }
    }

    foreach ($model in $optionalModels) {
        $found = $installedModels | Where-Object { $_ -like "$model*" }
        if ($found) {
            Write-Ok "$model (установлена)"
        } else {
            Write-Host "    Загружаю $model (рекомендуемая для чата)..."
            ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Не удалось загрузить $model. Чат будет работать, если выбрать другую модель."
            } else {
                Write-Ok "$model загружена"
            }
        }
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. PYTHON VENV + ЗАВИСИМОСТИ BACKEND
# ─────────────────────────────────────────────────────────────────────────────
Write-Step 'Python backend'

if ($SkipInstall -and (Test-Path $VenvPython)) {
    Write-Warn 'Пропуск установки зависимостей (-SkipInstall)'
} else {
    Push-Location $BackendDir

    if (-not (Test-Path $VenvPython)) {
        Write-Host '    Создаю виртуальное окружение .venv...'
        & $pythonCmd -m venv .venv
        if ($LASTEXITCODE -ne 0) { Write-Fail 'Не удалось создать venv'; Pop-Location; exit 1 }
        Write-Ok '.venv создан'
    } else {
        Write-Ok '.venv уже существует'
    }

    Write-Host '    Устанавливаю/обновляю зависимости (pip install -e .)...'
    & $VenvPip install --upgrade pip --quiet
    & $VenvPip install -e . --quiet
    if ($LASTEXITCODE -ne 0) { Write-Fail 'pip install завершился с ошибкой'; Pop-Location; exit 1 }
    Write-Ok 'Python-зависимости установлены'

    Pop-Location
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. NPM ЗАВИСИМОСТИ FRONTEND
# ─────────────────────────────────────────────────────────────────────────────
Write-Step 'Frontend (npm)'

if ($SkipInstall -and (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-Warn 'Пропуск npm install (-SkipInstall)'
} else {
    Push-Location $FrontendDir
    Write-Host '    npm install...'
    npm install --prefer-offline 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) { Write-Fail 'npm install завершился с ошибкой'; Pop-Location; exit 1 }
    Write-Ok 'npm-зависимости установлены'
    Pop-Location
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. ЗАПУСК ПРИЛОЖЕНИЯ
# ─────────────────────────────────────────────────────────────────────────────
Write-Step 'Запуск memo'
Write-Host ''
Write-Host '  Приложение запускается. Первый запуск компилирует Rust (~2–5 минут).' -ForegroundColor Yellow
Write-Host '  Последующие запуски занимают несколько секунд.' -ForegroundColor Yellow
Write-Host '  Закройте это окно или нажмите Ctrl+C, чтобы остановить.' -ForegroundColor Yellow
Write-Host ''

Push-Location $FrontendDir
npm run tauri dev
Pop-Location
