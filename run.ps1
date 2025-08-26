# run.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$envPath = Join-Path $root ".env"
if (Test-Path $envPath) {
  Write-Host "✅ .env найден: $envPath"
} else {
  Write-Host "ℹ️ .env не найден — переменные будут взяты из окружения"
}

$env:PYTHONPATH = "$root\src"

# выбрать доступный интерпретатор
if (Get-Command py -ErrorAction SilentlyContinue) {
  & py -3 -m bot.main
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  & python -m bot.main
} else {
  Write-Error "Не найден python/py в PATH"
}
