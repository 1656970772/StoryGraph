param(
  [string]$Source = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path,
  [string]$Destination = "$env:USERPROFILE\.codex\skills\storygraph",
  [switch]$Clean
)
$ErrorActionPreference = "Stop"
$copyItems = @("SKILL.md", "agents", "references", "scripts", "config\storygraph.default.json")
$cleanItems = @("SKILL.md", "agents", "references", "scripts", "config\storygraph.default.json")
$sourceRoot = (Resolve-Path -LiteralPath $Source).Path
$destinationRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
$expectedRoot = Join-Path $env:USERPROFILE ".codex\skills\storygraph"
$expectedResolved = [IO.Path]::GetFullPath($expectedRoot).TrimEnd('\')
if ($Clean -and $destinationRoot -ne $expectedResolved) {
  throw "Refusing to clean unexpected destination: $destinationRoot"
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
if ($Clean) {
  foreach ($item in $cleanItems) {
    $target = Join-Path $destinationRoot $item
    $resolvedParent = Split-Path -Parent $target
    $resolvedParentFull = [IO.Path]::GetFullPath($resolvedParent).TrimEnd('\')
    if ($resolvedParentFull -ne $destinationRoot -and -not $resolvedParentFull.StartsWith("$destinationRoot\")) {
      throw "Refusing to remove path outside destination: $target"
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
  }
}
foreach ($item in $copyItems) {
  $from = Join-Path $sourceRoot $item
  if (Test-Path -LiteralPath $from) {
    $sourceItem = Get-Item -LiteralPath $from
    if ($sourceItem.PSIsContainer) {
      Copy-Item -LiteralPath $from -Destination $destinationRoot -Recurse -Force
    } else {
      $to = Join-Path $destinationRoot $item
      $toParent = Split-Path -Parent $to
      New-Item -ItemType Directory -Path $toParent -Force | Out-Null
      Copy-Item -LiteralPath $from -Destination $to -Force
    }
  }
}
Write-Output "Synced StoryGraph skill to $destinationRoot"
