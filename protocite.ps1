<#
.SYNOPSIS
  ProtoCite on native Windows: one script to set up, start, stop, test and evaluate.

.EXAMPLE
  .\protocite.ps1 setup      # first time: Postgres+pgvector+Tesseract runtime, Python and web dependencies
  .\protocite.ps1 start      # database, migrations, demo data, API + web app on http://localhost:8001
  .\protocite.ps1 dev        # API with auto-reload + Vite dev server on http://localhost:5173
  .\protocite.ps1 stop       # stop the API and the database
  .\protocite.ps1 status     # what is running, and the /health report
  .\protocite.ps1 test       # backend + frontend checks and tests
  .\protocite.ps1 e2e        # browser tests against the running app (uses installed Edge)
  .\protocite.ps1 eval       # retrieval / citation / abstention evaluation with thresholds
  .\protocite.ps1 audit-verify
  .\protocite.ps1 reset      # DEV ONLY: wipe the database and reload the sample corpus

.NOTES
  Runs without Docker (Docker Desktop needs Windows virtualization, which may be disabled).
  Settings come from .env (copy .env.example). The API key stays in .env and is never printed.
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet("setup", "start", "dev", "stop", "status", "test", "e2e", "eval", "audit-verify", "reset", "build", "help")]
  [string]$Command = "help",
  [switch]$Rebuild,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Runtime = Join-Path $Root ".runtime"
$EnvDir = Join-Path $Runtime "env"
$PgBin = Join-Path $EnvDir "Library\bin"
$PgData = Join-Path $Runtime "pgdata"
$PgLog = Join-Path $Runtime "pg.log"
$PgPort = 5433
$ApiPort = 8001
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
$ApiPid = Join-Path $Runtime "api.pid"
$ApiLog = Join-Path $Runtime "api.log"
$ApiErr = Join-Path $Runtime "api.err.log"

function Say([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Warn([string]$Text) { Write-Host "!!  $Text" -ForegroundColor Yellow }
function Fail([string]$Text) { Write-Host "xx  $Text" -ForegroundColor Red; exit 1 }

function Test-Port([int]$Port) {
  $c = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  return [bool]$c
}

function Wait-Port([int]$Port, [int]$Seconds) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Port $Port) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Invoke-Checked([string]$File, [string[]]$Arguments, [string]$Where) {
  Push-Location $Where
  try {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { Fail "$File $($Arguments -join ' ') failed (exit $LASTEXITCODE)" }
  } finally {
    Pop-Location
  }
}

function Require-Runtime {
  if (-not (Test-Path (Join-Path $PgBin "pg_ctl.exe"))) { Fail "Postgres runtime missing. Run: .\protocite.ps1 setup" }
  if (-not (Test-Path $Py)) { Fail "Python environment missing. Run: .\protocite.ps1 setup" }
  if (-not (Test-Path (Join-Path $Root ".env"))) { Fail "No .env file. Copy .env.example to .env and add your GEMINI_API_KEY (or set LLM_PROVIDER=none)." }
}

function Start-Db {
  if (Test-Port $PgPort) { Say "PostgreSQL already running on port $PgPort"; return }
  Say "Starting PostgreSQL (port $PgPort)"
  # Start-Process (not &): pg_ctl's server must not inherit this console's handles.
  Start-Process -FilePath (Join-Path $PgBin "pg_ctl.exe") -ArgumentList @("-D", "`"$PgData`"", "-l", "`"$PgLog`"", "-o", "`"-p $PgPort`"", "start") -WindowStyle Hidden | Out-Null
  if (-not (Wait-Port $PgPort 30)) { Fail "PostgreSQL did not start; see $PgLog" }
  $ready = Join-Path $PgBin "pg_isready.exe"
  if (Test-Path $ready) {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
      & $ready -p $PgPort -q
      if ($LASTEXITCODE -eq 0) { break }
      Start-Sleep -Milliseconds 500
    }
  } else {
    Start-Sleep -Seconds 2
  }
}

function Stop-Db {
  if (-not (Test-Port $PgPort)) { Say "PostgreSQL is not running"; return }
  Say "Stopping PostgreSQL"
  Start-Process -FilePath (Join-Path $PgBin "pg_ctl.exe") -ArgumentList @("-D", "`"$PgData`"", "-m", "fast", "stop") -WindowStyle Hidden -Wait | Out-Null
}

function Stop-Api {
  $stopped = $false
  if (Test-Path $ApiPid) {
    $id = Get-Content $ApiPid -ErrorAction SilentlyContinue
    if ($id) {
      try { Stop-Process -Id ([int]$id) -Force -ErrorAction Stop; $stopped = $true } catch { }
    }
    Remove-Item $ApiPid -ErrorAction SilentlyContinue
  }
  $owner = Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($owner) {
    $proc = Get-Process -Id $owner.OwningProcess -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -like "python*") {
      try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop; $stopped = $true } catch { }
    }
  }
  if ($stopped) { Say "API stopped" } else { Say "API was not running" }
}

function Build-Web {
  $index = Join-Path $Frontend "dist\index.html"
  if ((Test-Path $index) -and -not $Rebuild) { return }
  Say "Building the web app"
  Invoke-Checked "pnpm" @("build") $Frontend
}

function Get-Health {
  try {
    return Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 15
  } catch {
    return $null
  }
}

switch ($Command) {
  "setup" {
    $mamba = Join-Path $Runtime "bin\micromamba.exe"
    if (-not (Test-Path (Join-Path $PgBin "pg_ctl.exe"))) {
      if (-not (Test-Path $mamba)) {
        Fail "Download micromamba.exe (https://mamba.readthedocs.io) into $Runtime\bin, then re-run setup."
      }
      Say "Creating the native runtime (PostgreSQL 16 + pgvector + Tesseract) from conda-forge"
      $env:MAMBA_ROOT_PREFIX = Join-Path $Runtime "mamba"
      Invoke-Checked $mamba @("create", "-y", "-p", $EnvDir, "-c", "conda-forge", "postgresql=16", "pgvector", "tesseract") $Root
    }
    if (-not (Test-Path (Join-Path $PgData "PG_VERSION"))) {
      Say "Initialising the database cluster"
      Invoke-Checked (Join-Path $PgBin "initdb.exe") @("-D", $PgData, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--locale=C") $Root
      Add-Content -Path (Join-Path $PgData "postgresql.conf") -Value "port = $PgPort"
      Start-Db
      $psql = Join-Path $PgBin "psql.exe"
      Invoke-Checked $psql @("-p", "$PgPort", "-U", "postgres", "-h", "127.0.0.1", "-c", "CREATE ROLE protocite LOGIN PASSWORD 'protocite'") $Root
      Invoke-Checked $psql @("-p", "$PgPort", "-U", "postgres", "-h", "127.0.0.1", "-c", "CREATE DATABASE protocite OWNER protocite") $Root
      Invoke-Checked $psql @("-p", "$PgPort", "-U", "postgres", "-h", "127.0.0.1", "-d", "protocite", "-c", "CREATE EXTENSION IF NOT EXISTS vector") $Root
    }
    Say "Installing Python dependencies (uv)"
    Invoke-Checked "uv" @("sync") $Backend
    Say "Installing web dependencies (pnpm)"
    Invoke-Checked "pnpm" @("install") $Frontend
    if (-not (Test-Path (Join-Path $Root ".env"))) {
      Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
      Warn "Created .env from .env.example. Open it and paste your GEMINI_API_KEY (or set LLM_PROVIDER=none)."
    }
    Say "Setup complete. Next: .\protocite.ps1 start"
  }

  "start" {
    Require-Runtime
    Start-Db
    Say "Migrating, seeding and loading the sample corpus if empty"
    Invoke-Checked $Py @("-m", "scripts.bootstrap") $Backend
    Build-Web
    if (Test-Port $ApiPort) { Warn "Port $ApiPort is busy - restarting the API"; Stop-Api; Start-Sleep -Seconds 1 }
    Say "Starting the API + web app on http://localhost:$ApiPort (models load in ~20-40 s)"
    $proc = Start-Process -FilePath $Py -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
      -WorkingDirectory $Backend -WindowStyle Hidden -RedirectStandardOutput $ApiLog -RedirectStandardError $ApiErr -PassThru
    Set-Content -Path $ApiPid -Value $proc.Id -Encoding ascii
    if (-not (Wait-Port $ApiPort 120)) { Fail "The API did not start; see $ApiErr" }
    $health = Get-Health
    if ($health) {
      Say ("Ready. Answer model: {0} ({1}); indexed clauses: {2}" -f $health.checks.llm.provider, $health.checks.llm.model, $health.checks.db.chunks)
    }
    if (-not $NoBrowser) { Start-Process "http://localhost:$ApiPort" }
    Say "Logs: $ApiLog  |  Stop with: .\protocite.ps1 stop"
  }

  "dev" {
    Require-Runtime
    Start-Db
    Invoke-Checked $Py @("-m", "scripts.bootstrap") $Backend
    if (Test-Port $ApiPort) { Stop-Api; Start-Sleep -Seconds 1 }
    Say "API with auto-reload on :$ApiPort and Vite on :5173 (two new windows)"
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", "Set-Location '$Backend'; & '$Py' -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --reload --reload-dir app") | Out-Null
    Start-Process powershell -ArgumentList @("-NoExit", "-Command", "Set-Location '$Frontend'; pnpm dev") | Out-Null
    if (-not $NoBrowser) { if (Wait-Port 5173 60) { Start-Process "http://localhost:5173" } }
  }

  "stop" {
    Stop-Api
    Stop-Db
  }

  "status" {
    Write-Host ("PostgreSQL :{0}  {1}" -f $PgPort, $(if (Test-Port $PgPort) { "running" } else { "stopped" }))
    Write-Host ("API        :{0}  {1}" -f $ApiPort, $(if (Test-Port $ApiPort) { "running" } else { "stopped" }))
    Write-Host ("Vite dev   :5173  {0}" -f $(if (Test-Port 5173) { "running" } else { "stopped" }))
    $health = Get-Health
    if ($health) { $health | ConvertTo-Json -Depth 5 }
  }

  "build" { $Rebuild = $true; Build-Web }

  "test" {
    Require-Runtime
    Start-Db
    Say "Backend: ruff, mypy, pytest"
    Invoke-Checked $Py @("-m", "ruff", "check", "app", "tests", "scripts") $Backend
    Invoke-Checked $Py @("-m", "mypy", "app") $Backend
    Invoke-Checked $Py @("-m", "pytest", "-q") $Backend
    Say "Frontend: typecheck, lint, unit tests"
    Invoke-Checked "pnpm" @("typecheck") $Frontend
    Invoke-Checked "pnpm" @("lint") $Frontend
    Invoke-Checked "pnpm" @("test") $Frontend
    Say "All checks passed"
  }

  "e2e" {
    if (-not (Test-Port $ApiPort)) { Fail "Start the app first: .\protocite.ps1 start" }
    $env:E2E_BASE_URL = "http://localhost:$ApiPort"
    Invoke-Checked "pnpm" @("e2e") $Frontend
  }

  "eval" {
    Require-Runtime
    Start-Db
    Invoke-Checked $Py @("-m", "eval.run_eval") $Root
  }

  "audit-verify" {
    Require-Runtime
    Start-Db
    Invoke-Checked $Py @("-m", "scripts.audit_verify") $Backend
  }

  "reset" {
    Require-Runtime
    Start-Db
    Warn "This deletes every document, answer log and audit event in the LOCAL database."
    $answer = Read-Host "Type RESET to continue"
    if ($answer -ne "RESET") { Fail "Cancelled" }
    Stop-Api
    Invoke-Checked $Py @("-m", "scripts.reset_db", "--yes") $Backend
    Invoke-Checked $Py @("-m", "scripts.bootstrap") $Backend
    Say "Database reset and sample corpus reloaded. Start with: .\protocite.ps1 start"
  }

  default { Get-Help $MyInvocation.MyCommand.Path -Detailed | Out-Host }
}
