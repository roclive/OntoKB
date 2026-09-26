$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:ONTOKB_LLM_PROVIDER = 'codex'
Write-Host 'OntoKB: http://127.0.0.1:8765 (Ctrl+C to stop)'
python -m ontokb.cli api --host 127.0.0.1 --port 8765
