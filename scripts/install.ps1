param(
  [switch]$DryRun,
  [switch]$JcodeView,
  [string]$ProjectRoot = (Get-Location).Path,
  [string]$Dest = ".agents/skills"
)
$ErrorActionPreference = "Stop"
$Skills = @("aps-plan", "idea-grill", "plan-forge", "plan-rehearsal", "routing-plan", "delegation-graph", "execution-manager")
$SourceRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../skills"))
$DestinationRoot = if ([System.IO.Path]::IsPathRooted($Dest)) { $Dest } else { Join-Path $ProjectRoot $Dest }

function Ensure-Directory([string]$Path) {
  if ($DryRun) { Write-Output "DRY RUN mkdir $Path"; return }
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Copy-Skill([string]$Source, [string]$Target) {
  if (-not (Test-Path -LiteralPath (Join-Path $Source "SKILL.md"))) {
    throw "Invalid skill source: $Source"
  }
  if ($DryRun) { Write-Output "DRY RUN copy $Source -> $Target"; return }
  Ensure-Directory $Target
  Copy-Item -Path (Join-Path $Source "*") -Destination $Target -Recurse -Force
}

Ensure-Directory $DestinationRoot
foreach ($Skill in $Skills) {
  Copy-Skill (Join-Path $SourceRoot $Skill) (Join-Path $DestinationRoot $Skill)
}
if ($JcodeView) {
  $JcodeRoot = Join-Path $ProjectRoot ".jcode/skills"
  Ensure-Directory $JcodeRoot
  foreach ($Skill in $Skills) {
    Copy-Skill (Join-Path $SourceRoot $Skill) (Join-Path $JcodeRoot $Skill)
  }
}
Write-Output "Graph Coder skills installed idempotently for PowerShell 5.1+. No secrets read or written."
