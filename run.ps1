# Sobe o GameBot sempre com o interpretador da venv do projeto.
# Existe porque o `python` do PATH nesta maquina e o 3.14 sem as dependencias:
# `python main.py` morria no `import discord` sem explicacao.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "venv nao encontrada em .venv" -ForegroundColor Yellow
    Write-Host "Criando com Python 3.12..."
    py -3.12 -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

& $venvPython --version
& $venvPython main.py @args
exit $LASTEXITCODE
