@echo off
REM ===================================================================
REM  Arranca el servidor de Esencias Gama.
REM  Lo llama el Programador de tareas de Windows al encender la PC.
REM
REM  Si algun dia mueves el proyecto de carpeta, cambia SOLO esta linea:
REM ===================================================================
set PROYECTO=C:\EsenciasGama

cd /d "%PROYECTO%"
if not exist "logs" mkdir "logs"

echo. >> "logs\servidor.log"
echo ===== Arranque %date% %time% ===== >> "logs\servidor.log"

REM  0.0.0.0:8000  -> acepta conexiones de las otras computadoras, no solo local
REM  --noreload    -> un solo proceso; mas facil de detener y no se reinicia solo
REM  --insecure    -> sirve los archivos de estilo/logo aun con DEBUG = False
"%PROYECTO%\venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8000 --noreload --insecure >> "logs\servidor.log" 2>&1

echo ===== Se detuvo %date% %time% ===== >> "logs\servidor.log"
