@echo off
title BRAINNET v7 - Master Launcher
echo ===================================================
echo INICIANDO O BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
echo ===================================================

:: 1. Inicia o frontend Vite React em janela isolada
start "BRAINNET UI - Vite Server" cmd /k "cd /d A:\BRAINNET\INTERFACE DE USUARIO\BRAINDET IU\project && npm run dev"

:: 2. Aguarda 4 segundos para o servidor Vite inicializar a porta 5173
echo Aguardando inicializacao do servidor Vite...
timeout /t 4 /nobreak > nul

:: 3. Ativa o ambiente virtual e lanca o Maestro Integrador Oficial
cd /d A:\BRAINNET\BRAIN
call A:\BRAINNET\VENV\Scripts\activate.bat
python BRAINNET.py

pause