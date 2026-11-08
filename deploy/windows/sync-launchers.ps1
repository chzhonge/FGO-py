$ErrorActionPreference = 'Stop'

$portableRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$python = Join-Path $portableRoot 'Python311/python.exe'
$entryPoint = Join-Path $portableRoot 'FGO-py/FGO-py/fgo.py'
if (!(Test-Path -LiteralPath $python -PathType Leaf) -or
    !(Test-Path -LiteralPath $entryPoint -PathType Leaf)) {
    throw 'Run this script from the Git checkout inside the FGO-py portable folder.'
}

$launchers = 'FGO-py.bat', 'FGO-py-auto.bat'
foreach ($name in $launchers) {
    if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot $name) -PathType Leaf)) {
        throw "Missing launcher source: $name"
    }
}

foreach ($name in $launchers) {
    $source = Join-Path $PSScriptRoot $name
    $target = Join-Path $portableRoot $name
    if ((Test-Path -LiteralPath $target -PathType Leaf) -and
        (Get-FileHash -LiteralPath $source).Hash -eq (Get-FileHash -LiteralPath $target).Hash) {
        Write-Output "Up to date: $target"
        continue
    }
    Copy-Item -LiteralPath $source -Destination $target
    Write-Output "Updated: $target"
}
