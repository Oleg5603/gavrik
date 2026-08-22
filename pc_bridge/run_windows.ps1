param([Parameter(Mandatory=$true)][string]$EnvFile, [Parameter(Mandatory=$true)][string]$Repo, [string]$Python = "python")
$env:PC_AGENT_ENV_FILE = $EnvFile
Set-Location $Repo
& $Python -m pc_bridge.client
exit $LASTEXITCODE
