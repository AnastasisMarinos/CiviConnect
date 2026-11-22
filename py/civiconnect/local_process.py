"""Inspect and stop this project's local Windows Uvicorn server."""

import os
import subprocess

from . import PROJECT_ROOT, PYTHON_ROOT


PROCESS_COMMAND = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$portNumber = [int]$env:CIVICONNECT_LOCAL_PORT
$python = $env:CIVICONNECT_LOCAL_PYTHON
$source = $env:CIVICONNECT_LOCAL_SOURCE
$action = $env:CIVICONNECT_LOCAL_ACTION

$listeners = @(Get-NetTCPConnection -State Listen | Where-Object {
    $_.LocalPort -eq $portNumber -and $_.LocalAddress -in ('127.0.0.1', '0.0.0.0', '::', '::1')
} | Select-Object -ExpandProperty OwningProcess -Unique)
if (!$listeners.Count) {
    Write-Output "No local server is listening on port $portNumber."
    exit 0
}
if ($listeners.Count -ne 1) {
    Write-Output "Multiple processes are listening on port $portNumber (PIDs $($listeners -join ', '))."
    exit 1
}

function Get-Arguments($process) {
    if ($process.ExecutablePath -and $process.CommandLine) {
        $exe = [regex]::Escape($process.ExecutablePath)
        if ($process.CommandLine -match ('^\s*"?{0}"?\s+(?<arguments>.+)$' -f $exe)) {
            return $Matches.arguments.Trim()
        }
    }
}

$ownerId = $listeners[0]
$owner = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerId"
if (!$owner) {
    Write-Output "The listener on port $portNumber changed. Try again."
    exit 1
}

$tail = " --host 127.0.0.1 --port $portNumber --log-level warning"
$command = '-m uvicorn app:app'
$launcher = Join-Path $source 'launch.py'
$arguments = Get-Arguments $owner
$expectedArguments = @(
    "$command$tail",
    "$command --app-dir $source$tail",
    "$command --app-dir `"$source`"$tail",
    "-u $launcher",
    "-u `"$launcher`""
)
$sameProject = $owner.ExecutablePath -eq $python
if (!$sameProject -and $arguments -in $expectedArguments) {
    # The Windows venv launcher can delegate to the base Python executable.
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.ParentProcessId)"
    $sameProject = $parent -and $parent.CreationDate -le $owner.CreationDate -and
        $parent.ExecutablePath -eq $python -and (Get-Arguments $parent) -eq $arguments
}
if (!$sameProject -or $arguments -notin $expectedArguments) {
    Write-Output "Port $portNumber is used by $($owner.Name) (PID $ownerId). It could not be verified as this CiviConnect server."
    if ($action -eq 'stop') { exit 1 }
    exit 0
}

Write-Output "CiviConnect is listening on port $portNumber (PID $ownerId)."
if ($action -ne 'stop') { exit 0 }

$target = Get-Process -Id $ownerId
if ([Math]::Abs(($target.StartTime - $owner.CreationDate).TotalMilliseconds) -ge 1) {
    Write-Output "The listener on port $portNumber changed. Try again."
    exit 1
}
Stop-Process -InputObject $target
if (!$target.WaitForExit(5000)) {
    Write-Output "CiviConnect did not exit. Check PID $ownerId in Task Manager."
    exit 1
}
Write-Output "Stopped CiviConnect on port $portNumber."
""".strip()


def control_server(port, action):
    environment = os.environ.copy()
    environment.update(
        CIVICONNECT_LOCAL_PORT=str(port),
        CIVICONNECT_LOCAL_PYTHON=str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe"),
        CIVICONNECT_LOCAL_SOURCE=str(PYTHON_ROOT),
        CIVICONNECT_LOCAL_ACTION=action,
    )
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROCESS_COMMAND],
        env=environment, capture_output=True, encoding="utf-8", errors="replace",
    )
