param([string]$ElectronZipDir)
$ErrorActionPreference = 'Stop'
$version = (Get-Content (Join-Path $PSScriptRoot 'package.json') -Raw | ConvertFrom-Json).version
$staging = Join-Path $PSScriptRoot 'dist/release-app'
New-Item -ItemType Directory -Force -Path $staging | Out-Null
if (Get-ChildItem -LiteralPath $staging -Force | Where-Object { $_.Name -notin @('main.cjs', 'package.json') }) { throw 'Unexpected files in release staging; use a clean staging directory.' }
# Explicit allowlist: never copy runtime config, repository data, or user records.
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'main.cjs') -Destination $staging -Force
@{ name = 'ontokb-desktop'; productName = 'OntoKB'; version = $version; main = 'main.cjs'; private = $true } | ConvertTo-Json | Set-Content -Encoding utf8NoBOM (Join-Path $staging 'package.json')
Push-Location $PSScriptRoot
try {
    $options = @($staging, 'OntoKB', '--platform=win32', '--arch=x64', '--out=dist/release', '--overwrite', '--asar', '--electron-version=44.4.5')
    if ($ElectronZipDir) { $options += "--electron-zip-dir=$ElectronZipDir" }
    & './node_modules/.bin/electron-packager.cmd' @options
    if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed' }
    $appDir = Join-Path $PSScriptRoot 'dist/release/OntoKB-win32-x64'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'RELEASE.md') -Destination (Join-Path $appDir 'README.md') -Force
    $zip = Join-Path $PSScriptRoot "dist/OntoKB-$version-win32-x64.zip"
    Compress-Archive -Path (Join-Path $appDir '*') -DestinationPath $zip -Force
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $([IO.Path]::GetFileName($zip))" | Set-Content -Encoding ascii (Join-Path $PSScriptRoot "dist/OntoKB-$version-SHA256SUMS.txt")
    Write-Output "Release archive: $zip"
    Write-Output "SHA256: $hash"
} finally { Pop-Location }
