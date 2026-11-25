@echo off
:: Configura o terminal para UTF-8 (para os emojis e acentos aparecerem corretamente)
chcp 65001 >nul

:: Vai para o diretório onde este arquivo .bat está salvo
cd /d "%~dp0"

echo ====================================================
echo INICIANDO TESTE E2E - FASE P52 (COUNCIL)
echo ====================================================
echo.

:: Executa o script Python
python run_p52_slice.py

echo.
echo ====================================================
echo TESTE CONCLUIDO.
echo ====================================================

:: Mantém a janela aberta para você ler o resultado
pause