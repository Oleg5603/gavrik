@echo off
cd /d C:\Users\HP\gavrik

:kill_dups
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq bot*" >nul 2>&1
ping -n 3 127.0.0.1 >nul

:loop
echo [%date% %time%] Запуск Гаврика... >> gavrik.log
python bot.py >> gavrik.log 2>> gavrik_err.log
echo [%date% %time%] Упал. Перезапуск через 5 сек... >> gavrik.log
ping -n 6 127.0.0.1 >nul
goto loop
