@echo off
cd /d C:\Users\HP\gavrik

:kill_dups
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq bot*" >nul 2>&1
timeout /t 2 /nobreak >nul

:loop
echo [%date% %time%] Запуск Гаврика... >> gavrik.log
python bot.py >> gavrik.log 2>> gavrik_err.log
echo [%date% %time%] Упал. Перезапуск через 5 сек... >> gavrik.log
timeout /t 5 /nobreak >nul
goto loop
