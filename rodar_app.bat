@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo Ambiente virtual nao encontrado. Criando com uv...
    "%USERPROFILE%\.local\bin\uv.exe" venv .venv
    "%USERPROFILE%\.local\bin\uv.exe" pip install -p .venv -r requirements.txt
)

.venv\Scripts\streamlit.exe run app.py
pause
