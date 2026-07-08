# Деплой Гаврика на Beget (облачный сервер)

Причина переезда: локальный запуск на Windows падает с `ClientConnectorError:
Cannot connect to host api.telegram.org` — Telegram API недоступен с
домашнего российского IP. Beget тоже датацентр в РФ, поэтому сначала
проверяем доступность напрямую, и только если она заблокирована — включаем
прокси-fallback (уже встроен в `bot.py` через `TELEGRAM_PROXY_URL`).

## 1. Подготовка сервера (облачный сервер Beget, Ubuntu)

```bash
apt update && apt install -y python3 python3-venv git
git clone <URL вашего репозитория gavrik> /root/gavrik
cd /root/gavrik
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## 2. Конфиг

Скопируйте `.env` с локальной машины на сервер (не через git):

```bash
scp .env root@<сервер Beget>:/root/gavrik/.env
```

## 3. Проверка доступности Telegram API с сервера

```bash
curl -I https://api.telegram.org
```

- Если пришёл ответ (HTTP 200/301 и т.п.) — всё в порядке, `TELEGRAM_PROXY_URL`
  оставляем пустым, бот работает напрямую.
- Если таймаут/обрыв соединения — нужен прокси. Пропишите в `.env` на сервере:
  ```
  TELEGRAM_PROXY_URL=http://user:pass@proxy-host:port
  ```
  (можно взять любой рабочий HTTP(S)-прокси с доступом к Telegram; `aiogram`
  подхватит его автоматически при следующем запуске бота).

## 4. Запуск через systemd

```bash
cp deploy/gavrik.service /etc/systemd/system/gavrik.service
systemctl daemon-reload
systemctl enable --now gavrik
```

## 5. Проверка и логи

```bash
systemctl status gavrik
journalctl -u gavrik -f
```

## Обновление после изменений в коде

```bash
cd /root/gavrik && git pull
systemctl restart gavrik
```
