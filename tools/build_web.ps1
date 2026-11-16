$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    uv sync --extra dev
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    & '.\.venv\Scripts\python.exe' 'tools\export_web_api.py'
    if ($LASTEXITCODE -ne 0) { throw 'OpenAPI export failed' }
    npm.cmd --prefix sau_frontend ci --loglevel=error
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    npm.cmd --prefix sau_frontend run api:types
    if ($LASTEXITCODE -ne 0) { throw 'API type generation failed' }
    npm.cmd --prefix sau_frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    uv build
    if ($LASTEXITCODE -ne 0) { throw 'Python package build failed' }
} finally { Pop-Location }
