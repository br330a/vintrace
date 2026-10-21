@echo off
title VinTrace - Backend FastAPI
echo ==============================================
echo       INICIANDO BACKEND VINTRACE (Porta 8000)
echo ==============================================
cd /d "%~dp0\backend"

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual Python...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo Backend rodando em http://localhost:8000
echo Swagger interativo em http://localhost:8000/docs
echo Pressione Ctrl+C para encerrar.
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
