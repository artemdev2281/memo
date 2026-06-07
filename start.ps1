#Requires -Version 5.1
<#
.SYNOPSIS
    Zapusk memo s nulya: proverka zavisimostey, ustanovka paketov, start prilozheniya.
.DESCRIPTION
    Skript:
      1. Proveryaet obyazatelnyye vneshniye programmy (Ollama, Python 3.11+, Node.js 18+, Rust/cargo)
      2. Zapuskayet Ollama serve, esli ne zapushchena
      3. Zagruzhayet nuzhnyye modeli, esli ikh net
      4. Sozdayot Python venv i ustanavlivayet zavisimosti backend
      5. Ustanavlivayet npm-zavisimosti frontend
      6. Zapuskayet prilozheniye cherez npm run tauri dev

    Zapusk (pri neobkhodimosti razreshit skripty):
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
        .\start.ps1

    Parametry:
        -SkipModelPull   Ne skachivat modeli Ollama (esli uzhe skachany)
        -SkipInstall     Ne ustanavlivat/obnovlyat zavisimosti Python i npm
#>

param(
    [switch]$SkipModelPull,
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Output helpers ----------------------------------------------------------
function Write-Step { param($msg) Write-Host "" ; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    [OK] $msg"    -ForegroundColor Green  }
function Write-Warn { param($msg) Write-Host "    [!]  $msg"    -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "" ; Write-Host "[ERROR] $msg" -ForegroundColor Red }

# --- Paths -------------------------------------------------------------------
$Root        = $PSScriptRoot
$BackendDir  = Join-Path $Root 'src\backend'
$FrontendDir = Join-Path $Root 'src\frontend'
$VenvDir     = Join-Path $BackendDir '.venv'
$VenvPython  = Join-Path $VenvDir 'Scripts\python.exe'

# =============================================================================
# 1. CHECK PREREQUISITES
# =============================================================================
Write-Step 'Checking prerequisites...'

$missing = @()

# Ollama
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Ok 'ollama found'
} else {
    $missing += 'Ollama'
    Write-Warn 'ollama NOT found'
}

# Python 3.11+
$pythonCmd = $null
foreach ($cmd in @('python', 'python3', 'py')) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $ver = & $cmd --version 2>&1
        if ($ver -match 'Python (\d+)\.(\d+)') {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -eq 3 -and $min -ge 11) {
                $pythonCmd = $cmd
                Write-Ok "Python found ($ver)"
                break
            }
        }
    }
}
if (-not $pythonCmd) {
    $missing += 'Python 3.11+'
    Write-Warn 'Python 3.11+ NOT found'
}

# Node.js 18+
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer   = (node --version) -replace 'v',''
    $nodeMajor = [int]($nodeVer.Split('.')[0])
    if ($nodeMajor -ge 18) {
        Write-Ok "Node.js v$nodeVer found"
    } else {
        $missing += 'Node.js 18+'
        Write-Warn "Node.js v$nodeVer is too old (need 18+)"
    }
} else {
    $missing += 'Node.js'
    Write-Warn 'Node.js NOT found'
}

# Rust / cargo
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    Write-Ok "cargo found ($(cargo --version))"
} else {
    $missing += 'Rust (cargo)'
    Write-Warn 'cargo NOT found'
}

if ($missing.Count -gt 0) {
    Write-Fail "Missing required programs: $($missing -join ', ')"
    Write-Host ""
    Write-Host "  Install them manually, then re-run .\start.ps1 :" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Ollama      : https://ollama.com/download"
    Write-Host "  Python 3.11+: https://www.python.org/downloads/"
    Write-Host "                (check 'Add Python to PATH' during install)"
    Write-Host "  Node.js 18+ : https://nodejs.org/  (choose LTS)"
    Write-Host "  Rust        : https://rustup.rs/   (run rustup-init.exe)"
    Write-Host "                (restart the terminal after Rust installation)"
    Write-Host ""
    exit 1
}

# =============================================================================
# 2. START OLLAMA SERVE
# =============================================================================
Write-Step 'Ollama serve...'

$ollamaRunning = $false
try {
    Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -ErrorAction Stop | Out-Null
    $ollamaRunning = $true
    Write-Ok 'Ollama is already running'
} catch {
    Write-Host '    Starting ollama serve in background...'
    Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden
    $waited = 0
    while ($waited -lt 30) {
        Start-Sleep -Seconds 2 ; $waited += 2
        try {
            Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 2 -ErrorAction Stop | Out-Null
            $ollamaRunning = $true
            Write-Ok 'Ollama started'
            break
        } catch {}
    }
}

if (-not $ollamaRunning) {
    Write-Fail 'Ollama did not respond within 30 seconds. Check installation.'
    exit 1
}

# =============================================================================
# 3. OLLAMA MODELS
# =============================================================================
Write-Step 'Ollama models...'

$requiredModels = @('bge-m3', 'qwen3:1.7b')
$optionalModels = @('qwen3:4b')

if ($SkipModelPull) {
    Write-Warn 'Skipping model pull (-SkipModelPull)'
} else {
    try {
        $tags      = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -ErrorAction Stop
        $installed = $tags.models | ForEach-Object { $_.name }
    } catch {
        $installed = @()
    }

    foreach ($model in $requiredModels) {
        $found = $installed | Where-Object { $_ -like "$($model)*" }
        if ($found) {
            Write-Ok "$model already installed"
        } else {
            Write-Host "    Pulling $model (required for indexing)..."
            ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "Failed to pull $model - indexing will not work"
                exit 1
            }
            Write-Ok "$model pulled"
        }
    }

    foreach ($model in $optionalModels) {
        $found = $installed | Where-Object { $_ -like "$($model)*" }
        if ($found) {
            Write-Ok "$model already installed"
        } else {
            Write-Host "    Pulling $model (recommended chat model)..."
            ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Failed to pull $model. Chat will work if you select another model."
            } else {
                Write-Ok "$model pulled"
            }
        }
    }
}

# =============================================================================
# 4. PYTHON VENV + BACKEND DEPENDENCIES
# =============================================================================
Write-Step 'Python backend...'

if ($SkipInstall -and (Test-Path $VenvPython)) {
    Write-Warn 'Skipping dependency install (-SkipInstall)'
} else {
    Push-Location $BackendDir

    if (-not (Test-Path $VenvPython)) {
        Write-Host '    Creating virtual environment (.venv)...'
        & $pythonCmd -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            Write-Fail 'Failed to create venv'
            Pop-Location ; exit 1
        }
        Write-Ok '.venv created'
    } else {
        Write-Ok '.venv already exists'
    }

    Write-Host '    Installing Python dependencies...'
    # Upgrade pip via python -m pip (pip.exe cannot upgrade itself on Windows)
    & $VenvPython -m pip install --upgrade pip -q 2>&1 | Out-Null

    & $VenvPython -m pip install -e . -q
    if ($LASTEXITCODE -ne 0) {
        Write-Fail 'pip install failed'
        Pop-Location ; exit 1
    }
    Write-Ok 'Python dependencies installed'

    Pop-Location
}

# =============================================================================
# 5. NPM FRONTEND DEPENDENCIES
# =============================================================================
Write-Step 'Frontend npm dependencies...'

if ($SkipInstall -and (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-Warn 'Skipping npm install (-SkipInstall)'
} else {
    Push-Location $FrontendDir
    Write-Host '    Running npm install...'
    npm install --prefer-offline 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail 'npm install failed'
        Pop-Location ; exit 1
    }
    Write-Ok 'npm dependencies installed'
    Pop-Location
}

# =============================================================================
# 6. LAUNCH APP
# =============================================================================
Write-Step 'Launching memo...'
Write-Host ""
Write-Host "  First run compiles Rust code (~2-5 min). Subsequent runs take seconds." -ForegroundColor Yellow
Write-Host "  Press Ctrl+C or close this window to stop the app." -ForegroundColor Yellow
Write-Host ""

Push-Location $FrontendDir
npm run tauri dev
Pop-Location
