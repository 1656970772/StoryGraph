param(
  [string]$Source = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path,
  [string]$Destination = "$env:USERPROFILE\.codex\skills\storygraph",
  [switch]$Clean
)
$ErrorActionPreference = "Stop"
$items = @("SKILL.md", "agents", "references", "scripts", "config")
$sourceRoot = (Resolve-Path -LiteralPath $Source).Path
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$destinationRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
$expectedRoot = Join-Path $env:USERPROFILE ".codex\skills\storygraph"
$expectedResolved = [IO.Path]::GetFullPath($expectedRoot).TrimEnd('\')
if ($Clean -and $destinationRoot -ne $expectedResolved) {
  throw "Refusing to clean unexpected destination: $destinationRoot"
}
if ($Clean) {
  foreach ($item in $items) {
    $target = Join-Path $destinationRoot $item
    $resolvedParent = Split-Path -Parent $target
    $resolvedParentFull = [IO.Path]::GetFullPath($resolvedParent).TrimEnd('\')
    if ($resolvedParentFull -ne $destinationRoot) {
      throw "Refusing to remove path outside destination: $target"
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
  }
}
foreach ($item in $items) {
  $from = Join-Path $sourceRoot $item
  if (Test-Path -LiteralPath $from) {
    Copy-Item -LiteralPath $from -Destination $destinationRoot -Recurse -Force
  }
}
Write-Output "Synced StoryGraph skill to $destinationRoot"
