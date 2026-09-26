param([switch]$Install)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = (Get-Command python.exe).Source
@{ projectRoot = $projectRoot; python = $pythonPath } | ConvertTo-Json | Set-Content -Encoding utf8NoBOM (Join-Path $PSScriptRoot 'runtime.json')
Push-Location $PSScriptRoot
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    & npm.cmd run package
    if ($LASTEXITCODE -ne 0) { throw 'Electron packaging failed' }
    if ($Install) {
        $target = Join-Path $env:LOCALAPPDATA 'Programs\OntoKB'
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -Path '.\dist\OntoKB-win32-x64\*' -Destination $target -Recurse -Force
        $shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'OntoKB.lnk'
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $target 'OntoKB.exe'
        $shortcut.WorkingDirectory = $target
        $shortcut.Save()
        Start-Process -FilePath (Join-Path $target 'OntoKB.exe') -WindowStyle Hidden
    }
} finally { Pop-Location }
