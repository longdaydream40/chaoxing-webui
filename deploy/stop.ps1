$ErrorActionPreference = "SilentlyContinue"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runDir = Join-Path $root "run"

function Stop-ServiceProcess {
    param(
        [string]$Name,
        [string]$PidFile
    )

    if (-not (Test-Path $PidFile)) {
        Write-Host "$Name not running (no pid file)"
        return
    }

    $servicePid = Get-Content $PidFile | Select-Object -First 1
    if (-not $servicePid) {
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Write-Host "$Name pid file empty and removed"
        return
    }

    $proc = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $servicePid -Force
        Write-Host "$Name stopped (PID=$servicePid)"
    } else {
        Write-Host "$Name process not found (PID=$servicePid)"
    }

    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

Stop-ServiceProcess -Name "backend" -PidFile (Join-Path $runDir "backend.pid")
Stop-ServiceProcess -Name "frontend" -PidFile (Join-Path $runDir "frontend.pid")
