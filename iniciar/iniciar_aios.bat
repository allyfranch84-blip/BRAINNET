@echo off
setlocal
title BRAINNET - Integracao P4.4
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "GUI=%ROOT%\INTERFACE DE USUARIO\BRAINDET IU\project"
set "PYTHON=%ROOT%\VENV\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=A:\BRAINNET\VENV\Scripts\python.exe"

set "BRAINNET_MINIMAL=1"
set "BRAINNET_P4_PHYSICAL_PROPOSALS=1"
set "BRAINNET_P4_DIRECT_MOVE=1"
set "BRAINNET_MOTOR_SEMANTIC=1"
set "BRAINNET_PERCEPTUAL_PRESENT=1"
set "BRAINNET_MINIMAL_GUI_PORT=5198"
set "BRAINNET_ADAPTIVE_OBSERVE=0"

echo ====================================================
echo BRAINNET - Perfil minimo P4.4
echo Projeto: "%ROOT%"
echo Python: "%PYTHON%"
echo Interface: http://127.0.0.1:%BRAINNET_MINIMAL_GUI_PORT%
echo ====================================================

if not exist "%ROOT%\BRAIN\BRAINNET.py" goto :missing_kernel
if not exist "%PYTHON%" goto :missing_python
if not exist "%GUI%\node_modules\vite\bin\vite.js" goto :missing_vite
where npm.cmd >nul 2>&1
if errorlevel 1 goto :missing_npm

rem Never reuse an unverified server or terminate another process.
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %BRAINNET_MINIMAL_GUI_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 }; exit 0"
if errorlevel 1 goto :port_busy

start "BRAINNET Vite P4.4" /D "%GUI%" cmd.exe /k "npm.cmd run dev -- --host 127.0.0.1 --port %BRAINNET_MINIMAL_GUI_PORT% --strictPort"
echo Aguardando a interface responder...
powershell.exe -NoProfile -Command "$end=(Get-Date).AddSeconds(30); do { try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%BRAINNET_MINIMAL_GUI_PORT%/' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $end); exit 1"
if errorlevel 1 goto :vite_failed

rem Kernel owns inference startup, cleanup, warmup and recovery. No second supervisor.
set "OLLAMA_HOST=127.0.0.1:11435"
if not defined BRAINNET_INFERENCE_BACKEND set "BRAINNET_INFERENCE_BACKEND=ollama"
set "BRAINNET_MANAGE_INFERENCE=1"
set "BRAINNET_RESET_INFERENCE=1"
echo Backend: %BRAINNET_INFERENCE_BACKEND%
echo O Kernel reiniciara os processos locais de inferencia e testara a geracao.
echo Iniciando Kernel de "%ROOT%\BRAIN"...
pushd "%ROOT%\BRAIN"
"%PYTHON%" "%ROOT%\BRAIN\BRAINNET.py"
set "KERNEL_EXIT=%ERRORLEVEL%"
popd
echo Kernel encerrado. Codigo: %KERNEL_EXIT%
echo Feche o terminal Vite P4.4 quando nao precisar mais da interface.
pause
exit /b %KERNEL_EXIT%

:missing_kernel
echo ERRO: Kernel ausente na pasta do projeto.
goto :failed
:missing_python
echo ERRO: ambiente Python VENV nao encontrado.
goto :failed
:missing_vite
echo ERRO: dependencias Vite ausentes em "%GUI%".
echo Execute npm.cmd install nessa pasta e tente novamente.
goto :failed
:missing_npm
echo ERRO: npm.cmd nao encontrado no PATH.
goto :failed
:port_busy
echo ERRO: porta %BRAINNET_MINIMAL_GUI_PORT% ocupada ou consulta indisponivel.
echo Feche somente a instancia Vite anterior conhecida e tente novamente.
goto :failed
:vite_failed
echo ERRO: interface nao respondeu. Confira o terminal Vite P4.4.
:failed
pause
exit /b 1
