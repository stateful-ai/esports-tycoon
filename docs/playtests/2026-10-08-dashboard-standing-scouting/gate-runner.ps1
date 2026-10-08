$ErrorActionPreference='Stop'
$env:PYTHONPATH=(Resolve-Path src).Path
$py='C:/Users/aidan/workspace/esports-simulator/ESports Simulator/.venv-win/Scripts/python.exe'
$paths=@('src/esports_sim/web/server.py','src/esports_sim/web/static/app.js','tests/test_web_scout_readiness.py')
$paths | ForEach-Object { [pscustomobject]@{path=$_;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash} } | ConvertTo-Json | Set-Content runs/playtests/gap14/source-freeze.json
& $py -m pytest -q -n 2 2>&1 | Tee-Object runs/playtests/gap14/full-gate.log
$gateExit=$LASTEXITCODE
[pscustomobject]@{exit_code=$gateExit;finished_at_utc=(Get-Date).ToUniversalTime().ToString('o');command='python -m pytest -q -n 2';source=(Get-Content runs/playtests/gap14/source-freeze.json -Raw | ConvertFrom-Json)} | ConvertTo-Json -Depth 6 | Set-Content runs/playtests/gap14/full-gate-result.json
exit $gateExit
