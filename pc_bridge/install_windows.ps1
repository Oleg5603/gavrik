param(
  [string]$Python = "python",
  [string]$Repo = "C:\gavrik",
  [string]$Url,
  [string]$Token,
  [string]$Roots = "C:\Users\HP\Downloads\Gavrik",
  [int]$MaxFileBytes = 52428800
)

$ErrorActionPreference = "Stop"
if (-not $Url -or -not $Token) { throw "Укажите -Url и -Token" }
$task = "Gavrik PC Bridge"
$envLine = "PC_AGENT_URL=$Url`nPC_AGENT_TOKEN=$Token`nPC_AGENT_ROOTS=$Roots`nPC_AGENT_MAX_FILE_BYTES=$MaxFileBytes`nPC_AGENT_ALLOW_EXEC=0"
$envFile = Join-Path $Repo "pc_agent.env"
[IO.File]::WriteAllText($envFile, $envLine, [Text.UTF8Encoding]::new($false))
$acl = Get-Acl $envFile
$acl.SetAccessRuleProtection($true, $false)
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "Read", "Allow")))
Set-Acl $envFile $acl
$runner = Join-Path $Repo "pc_bridge\run_windows.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -EnvFile `"$envFile`" -Repo `"$Repo`" -Python `"$Python`"" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName $task
if ((Get-ScheduledTask -TaskName $task).State -ne "Running") { throw "PC bridge не запустился" }
Write-Host "PC bridge установлен и запущен без прав администратора: $task"
