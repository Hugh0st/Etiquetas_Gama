@echo off
REM ===================================================================
REM  Respaldo diario de la base de datos de Esencias Gama.
REM  Lo llama el Programador de tareas de Windows una vez al dia.
REM
REM  Si algun dia mueves el proyecto de carpeta, cambia SOLO esta linea:
REM ===================================================================
set PROYECTO=C:\EsenciasGama

cd /d "%PROYECTO%"
if not exist "logs" mkdir "logs"

echo. >> "logs\respaldos.log"
echo ===== %date% %time% ===== >> "logs\respaldos.log"

"%PROYECTO%\venv\Scripts\python.exe" manage.py respaldar_bd >> "logs\respaldos.log" 2>&1

if errorlevel 1 (
    echo *** EL RESPALDO FALLO - revisa este archivo *** >> "logs\respaldos.log"
    exit /b 1
)
exit /b 0
