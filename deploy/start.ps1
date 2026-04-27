param(
    [switch]$OpenBrowser,
    [switch]$SkipDependencyCheck
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runDir = Join-Path $root "run"
$logDir = Join-Path $root "logs"
$envFile = Join-Path $root ".env"
$frontendUrl = "http://127.0.0.1:5501/"

function Normalize-ProcessPathEnvironment {
    $pathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
    if (-not $pathValue) {
        $pathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
    }
    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    if ($pathValue) {
        [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")
    }
}

Normalize-ProcessPathEnvironment

if (-not (Test-Path $runDir)) { New-Item -ItemType Directory -Path $runDir | Out-Null }
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) { return }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
        $name, $value = $line.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name -and -not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Test-PythonDependencies {
    python -c "import flask, openai, requests, loguru, bs4, lxml, httpx" *> $null
    return ($LASTEXITCODE -eq 0)
}

Import-DotEnv -Path $envFile

if (-not $env:ADMIN_PASSWORD) {
    $hostValue = if ($env:HOST) { $env:HOST.Trim().ToLowerInvariant() } else { "127.0.0.1" }
    if ($hostValue -notin @("127.0.0.1", "localhost", "::1")) {
        throw "ADMIN_PASSWORD must be set when HOST is not loopback."
    }
    $env:ADMIN_PASSWORD = "local-admin-change-me"
    Write-Host "ADMIN_PASSWORD is not set; using local-only default: local-admin-change-me"
    Write-Host "Set ADMIN_PASSWORD in .env before public deployment."
}

if (-not $SkipDependencyCheck -and -not (Test-PythonDependencies)) {
    Write-Host "Python dependencies are missing. Installing from requirements.txt..."
    python -m pip install -r (Join-Path $root "requirements.txt")
}

$backendPidFile = Join-Path $runDir "backend.pid"
$frontendPidFile = Join-Path $runDir "frontend.pid"

function Start-ServiceProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$PidFile,
        [string]$StdoutLog,
        [string]$StderrLog
    )

    if (Test-Path $PidFile) {
        $existingPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($existingPid) {
            $p = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($p) {
                Write-Host "$Name already running (PID=$existingPid)"
                return
            }
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }

    $proc = Start-Process -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $root `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru

    Set-Content -Path $PidFile -Value $proc.Id -NoNewline
    Write-Host "$Name started (PID=$($proc.Id))"
}

$backendOut = Join-Path $logDir "backend.out.log"
$backendErr = Join-Path $logDir "backend.err.log"
$frontendOut = Join-Path $logDir "frontend.out.log"
$frontendErr = Join-Path $logDir "frontend.err.log"

Start-ServiceProcess `
    -Name "backend" `
    -FilePath "python" `
    -ArgumentList @("local_backend_launcher.py") `
    -PidFile $backendPidFile `
    -StdoutLog $backendOut `
    -StderrLog $backendErr

Start-Sleep -Seconds 1

Start-ServiceProcess `
    -Name "frontend" `
    -FilePath "python" `
    -ArgumentList @("-m", "http.server", "5501", "-d", "frontend") `
    -PidFile $frontendPidFile `
    -StdoutLog $frontendOut `
    -StderrLog $frontendErr

Start-Sleep -Seconds 1
Write-Host "Deployment start command completed."
Write-Host "Backend URL: http://127.0.0.1:8000"
Write-Host "Frontend URL: $frontendUrl"

if ($OpenBrowser) {
    Start-Process $frontendUrl
}
