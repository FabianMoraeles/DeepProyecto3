$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Instala Python 3.13 y el lanzador py." }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Falló la instalación." }
    & .\.venv\Scripts\python.exe tasks.py test
    if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas." }
} finally {
    Pop-Location
}
