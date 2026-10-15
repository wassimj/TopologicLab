$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($env:CONDA_DEFAULT_ENV -eq 'topologicpy-occ8') {
    & python launch.py
} elseif (Get-Command conda -ErrorAction SilentlyContinue) {
    & conda run --no-capture-output --name topologicpy-occ8 python launch.py
} else {
    $taskEnvRoot = Join-Path $env:LOCALAPPDATA 'miniconda3\envs\topologicpy-occ8'
    $taskPython = Join-Path $taskEnvRoot 'python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        throw 'Activate the existing topologicpy-occ8 environment, then run python launch.py from this folder.'
    }
    $env:PATH = "$taskEnvRoot;$taskEnvRoot\Library\bin;$taskEnvRoot\Scripts;$env:PATH"
    & $taskPython launch.py
}
if ($LASTEXITCODE -ne 0) { throw 'TopologicLab could not start. See the error above.' }
