$ErrorActionPreference = "SilentlyContinue"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runDir = Join-Path $root "run"

function Show-ServiceStatus {
    param(
        [string]$Name,
        [string]$PidFile
    )

    if (-not (Test-Path $PidFile)) {
        Write-Host "${Name}: stopped"
        return
    }

    $servicePid = Get-Content $PidFile | Select-Object -First 1
    if (-not $servicePid) {
        Write-Host "${Name}: stopped (empty pid file)"
        return
    }

    $proc = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "${Name}: running (PID=$servicePid)"
    } else {
        Write-Host "${Name}: stopped (stale pid=$servicePid)"
    }
}

Show-ServiceStatus -Name "backend" -PidFile (Join-Path $runDir "backend.pid")
Show-ServiceStatus -Name "frontend" -PidFile (Join-Path $runDir "frontend.pid")
