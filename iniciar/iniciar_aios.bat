@echo off
title BRAINNET - Sistema Operacional Cognitivo
echo ====================================================
echo INICIANDO O ORGANISMO BRAINNET...
echo ====================================================

echo [0/4] Reiniciando o Motor do Ollama (Disco A:)...
taskkill /F /IM ollama.exe >nul 2>&1
taskkill /F /IM "ollama app.exe" >nul 2>&1
start "Ollama Server" /min cmd /c "ollama serve"
echo Aguardando o Ollama carregar os modelos...
timeout /t 3 /nobreak >nul

echo [1/4] Iniciando Vite da GUI Principal (Porta 5173)...
start "Vite GUI 5173" /D "A:\BRAINNET\INTERFACE DE USUARIO\BRAINDET IU\project" cmd /c "npm run dev"

echo [2/4] Iniciando Vite da Hotbar (Porta 5174)...
start "Vite Hotbar 5174" /D "A:\BRAINNET\INTERFACE DE USUARIO\hotbar velha\project" cmd /c "npm run dev"

echo Aguardando os servidores Vite compilarem (10 segundos)...
timeout /t 10 /nobreak >nul

echo [3/4] Iniciando o Kernel (Python)...
cd /d "A:\BRAINNET\BRAIN"
py -3.12 BRAINNET.py

echo.
echo O Kernel encerrou. Pressione qualquer tecla para fechar esta janela.
pause >nul