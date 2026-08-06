param(
  [switch]$DryRun,
  [switch]$JcodeView,
  [switch]$RemoveRetired,
  [string]$ProjectRoot = (Get-Location).Path,
  [string]$Dest = ".agents/skills"
)
$ErrorActionPreference = "Stop"
$Skills = @("graph-coder", "concept-grill", "technical-research", "plan-forge", "plan-rehearsal", "delegation-graph", "routing-plan", "execution-manager")
# Skills this lifecycle replaced. Copying never removes them, so a destination
# that predates the rename keeps offering the old phase under the old name and
# a run can select it instead of its replacement.
$Retired = @{ "aps-plan" = "graph-coder"; "idea-grill" = "concept-grill" }
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

function Report-Retired([string]$Root) {
  foreach ($Name in $Retired.Keys) {
    $Path = Join-Path $Root $Name
    if (-not (Test-Path -LiteralPath (Join-Path $Path "SKILL.md"))) { continue }
    if ($RemoveRetired) {
      if ($DryRun) { Write-Output "DRY RUN remove retired skill $Path" }
      else {
        Remove-Item -LiteralPath $Path -Recurse -Force
        Write-Output "REMOVED retired skill $Path"
      }
    }
    else {
      Write-Warning "Retired skill still installed: $Path. It shadows $($Retired[$Name]) and a run can select it instead. Re-run with -RemoveRetired, or delete the directory."
    }
  }
}

Ensure-Directory $DestinationRoot
foreach ($Skill in $Skills) {
  Copy-Skill (Join-Path $SourceRoot $Skill) (Join-Path $DestinationRoot $Skill)
}
Report-Retired $DestinationRoot
if ($JcodeView) {
  $JcodeRoot = Join-Path $ProjectRoot ".jcode/skills"
  Ensure-Directory $JcodeRoot
  foreach ($Skill in $Skills) {
    Copy-Skill (Join-Path $SourceRoot $Skill) (Join-Path $JcodeRoot $Skill)
  }
  Report-Retired $JcodeRoot
}
Write-Output "Graph Coder skills installed idempotently for PowerShell 5.1+. No secrets read or written."
