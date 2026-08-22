#!/bin/bash
# Скрипт безопасной ротации токенов

echo "=== Ротация токенов Гаврика ==="
echo ""
echo "⚠️  ИНСТРУКЦИЯ:"
echo "1. Получи новый TELEGRAM_TOKEN от @BotFather"
echo "2. Получи новый VK_TOKEN из VK settings"
echo "3. Измени пароль root на VPS 159.194.200.172"
echo ""
echo "Введи новые значения (или Enter чтобы пропустить):"
echo ""

# Backup текущего .env
cp .env .env.backup.$(date +%s)
echo "✓ Бэкап создан: .env.backup.*"

# Telegram
read -p "Новый TELEGRAM_TOKEN: " NEW_TELEGRAM
if [ ! -z "$NEW_TELEGRAM" ]; then
    sed -i "s|TELEGRAM_TOKEN=.*|TELEGRAM_TOKEN=$NEW_TELEGRAM|" .env
    echo "✓ TELEGRAM_TOKEN обновлён"
fi

# VK
read -p "Новый VK_TOKEN: " NEW_VK
if [ ! -z "$NEW_VK" ]; then
    sed -i "s|VK_TOKEN=.*|VK_TOKEN=$NEW_VK|" .env
    echo "✓ VK_TOKEN обновлён"
fi

# VPS Password
read -p "Новый VPS_PASSWORD: " NEW_VPS_PASS
if [ ! -z "$NEW_VPS_PASS" ]; then
    sed -i "s|VPS_PASSWORD=.*|VPS_PASSWORD=$NEW_VPS_PASS|" .env
    echo "✓ VPS_PASSWORD обновлён"
fi

echo ""
echo "=== Ротация завершена ==="
echo "Старый .env сохранён как .env.backup.*"
echo "Перезапусти бота: python bot.py"
