# Гаврик — автозапуск с авторестартом
# Убивает дубликаты, ведёт лог, перезапускается при падении

$BOT_DIR = "C:\Users\HP\gavrik"
$LOG = "$BOT_DIR\gavrik.log"
$ERR = "$BOT_DIR\gavrik_err.log"

# Убиваем все дублирующие bot.py процессы
Get-WmiObject Win32_Process | Where-Object {
    $_.Name -like "python*" -and $_.CommandLine -like "*bot.py*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2

# Бесконечный цикл авторестарта
while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content $LOG "[$timestamp] Запуск Гаврика..."

    $proc = Start-Process python -ArgumentList "bot.py" `
        -WorkingDirectory $BOT_DIR `
        -RedirectStandardOutput $LOG `
        -RedirectStandardError $ERR `
        -PassThru -NoNewWindow

    $proc.WaitForExit()
    $exitCode = $proc.ExitCode

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content $LOG "[$timestamp] Гаврик упал (код $exitCode). Перезапуск через 5 сек..."
    Start-Sleep -Seconds 5
}
