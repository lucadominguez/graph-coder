param([switch]$DryRun, [string]$Command = "aps status --state .aps/state.json")
$ErrorActionPreference = "Stop"
$Wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if (-not $Wt) { throw "wt.exe not found. Open a normal terminal and run: $Command" }
if ($DryRun) { Write-Host "DRY RUN wt.exe new-tab powershell -NoExit -Command $Command"; exit 0 }
& wt.exe new-tab powershell -NoExit -Command $Command
# Intentionally no Komorebi dependency.
