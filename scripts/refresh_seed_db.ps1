# Copy the live shared cape.db into Resources\seed\cape.db so the next
# installer build (CAPEView_setup.iss) can bundle it. Run on a LAN-connected
# machine before invoking ISCC. CI runners cannot reach the share, so they
# rely on Resources\seed\cape.db being present from a prior local refresh.

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path "$PSScriptRoot\.."
$source = '\\192.168.115.99\scans\Dev\CAPEView\Database\cape.db'
$targetDir = Join-Path $repoRoot 'Resources\seed'
$target = Join-Path $targetDir 'cape.db'

if (-not (Test-Path $source)) {
    throw "Source DB not reachable: $source. Are you on the office LAN?"
}

if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir | Out-Null
}

Copy-Item -Path $source -Destination $target -Force

$size = (Get-Item $target).Length / 1MB
Write-Output ("Seeded {0} ({1:N1} MB) from {2}" -f $target, $size, $source)
