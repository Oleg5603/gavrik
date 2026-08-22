# PC Bridge

Надёжный канал ПК ↔ Гаврик: Windows-агент сам подключается к VPS, посылает heartbeat и переподключается с backoff. По умолчанию доступны только `status`, `read`, `write`; пути разрешены только внутри `PC_AGENT_ROOTS`, а размер файла ограничен `PC_AGENT_MAX_FILE_BYTES` (50 МиБ). `exec` по умолчанию отключён.

## Запуск агента на ПК

```powershell
$env:PC_AGENT_URL = "wss://<vps-host>/pc/ws"
$env:PC_AGENT_TOKEN = "длинный-случайный-токен"
$env:PC_AGENT_ROOTS = "C:\Users\HP\Downloads\Gavrik"
$env:PC_AGENT_MAX_FILE_BYTES = "52428800"
$env:PC_AGENT_ALLOW_EXEC = "0"
python -m pc_bridge.client
```

Запускать агент нужно через Task Scheduler или NSSM с автоматическим стартом и рестартом. Внешний порт шлюза должен быть доступен только через Tailscale/WireGuard; не публиковать его в открытый интернет.

Для установки Task Scheduler из PowerShell (от администратора):

```powershell
.\pc_bridge\install_windows.ps1 -Repo C:\gavrik `
  -Url wss://<tailscale-vps-name>:8765/pc/ws `
  -Token '<тот-же-токен-что-в-.env>'
```

На VPS в `.env`:

```dotenv
PC_AGENT_TOKEN=<длинный-случайный-токен>
PC_GATEWAY_HOST=0.0.0.0
PC_GATEWAY_PORT=8765
```

После перезапуска Гаврика проверь `/pcstatus`. Токен не добавляй в git и не отправляй в Telegram.
