$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$project = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $project 'runtime'
$pythonDir = Join-Path $runtime 'python'
$cache = Join-Path $project '.build-cache'
New-Item -ItemType Directory -Force $pythonDir, $cache | Out-Null
$python = Join-Path $pythonDir 'python.exe'
if (!(Test-Path $python)) {
    $archive = Join-Path $cache 'python-3.13.12-embed-amd64.zip'
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.13.12/python-3.13.12-embed-amd64.zip' -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $pythonDir -Force
}
@'
python313.zip
.
Lib/site-packages
../scripts
import site
'@ | Set-Content -Encoding ASCII (Join-Path $pythonDir 'python313._pth')
if (!(Test-Path (Join-Path $pythonDir 'Lib/site-packages/pip'))) {
    $getPip = Join-Path $cache 'get-pip.py'
    Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getPip
    & $python -s $getPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed' }
}
& $python -s -m pip install --disable-pip-version-check --no-warn-script-location -r (Join-Path $PSScriptRoot 'requirements-windows.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
Copy-Item (Join-Path $project 'node_modules/ffmpeg-static/ffmpeg.exe') (Join-Path $runtime 'ffmpeg.exe') -Force
Copy-Item (Join-Path $project 'node_modules/ffprobe-static/bin/win32/x64/ffprobe.exe') (Join-Path $runtime 'ffprobe.exe') -Force
New-Item -ItemType Directory -Force (Join-Path $runtime 'licenses') | Out-Null
Get-ChildItem (Join-Path $project 'node_modules/ffmpeg-static') -File | Where-Object { $_.Name -match 'LICENSE|README' } | Copy-Item -Destination (Join-Path $runtime 'licenses') -Force
Copy-Item (Join-Path $project 'node_modules/ffprobe-static/LICENSE') (Join-Path $runtime 'licenses/ffprobe-LICENSE') -Force
New-Item -ItemType Directory -Force (Join-Path $runtime 'scripts') | Out-Null
Get-ChildItem $project -Filter '*.py' -File | Copy-Item -Destination (Join-Path $runtime 'scripts') -Force
& $python -s -c 'import faster_whisper, common; print(faster_whisper.__version__)'
if ($LASTEXITCODE -ne 0) { throw 'Python runtime verification failed' }
& (Join-Path $runtime 'ffmpeg.exe') -version | Select-Object -First 1
if ($LASTEXITCODE -ne 0) { throw 'FFmpeg verification failed' }
