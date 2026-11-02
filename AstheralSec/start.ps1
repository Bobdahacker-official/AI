$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create the Python environment using the README first.'
}
& $taskPython (Join-Path $PSScriptRoot 'verify_artifacts.py')
if ($LASTEXITCODE -ne 0) { throw 'Artifact verification failed.' }
& $taskPython (Join-Path $PSScriptRoot 'chat.py') --device cuda
if ($LASTEXITCODE -ne 0) { throw 'Chat exited with an error.' }
