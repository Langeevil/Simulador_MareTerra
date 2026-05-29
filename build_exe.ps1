$ErrorActionPreference = "Stop"

Write-Host "Validando estrutura do projeto..."
foreach ($path in @("app\app.py", "src\simulador_aquicola.py", "launcher.py", "requirements.txt")) {
  if (-not (Test-Path $path)) {
    throw "Arquivo obrigatorio nao encontrado: $path"
  }
}

$iconPath = "app\assets\mar-terra-logo.ico"
if (-not (Test-Path $iconPath)) {
  throw "Icone obrigatorio nao encontrado: $iconPath"
}

Write-Host "Instalando dependencias..."
python -m pip install -r requirements.txt

Write-Host "Validando sintaxe Python..."
python -m py_compile app\app.py src\simulador_aquicola.py launcher.py

Write-Host "Limpando builds anteriores..."
if (Test-Path "build") { Remove-Item -LiteralPath "build" -Recurse -Force }
if (Test-Path "dist\SimuladorBiomassa") { Remove-Item -LiteralPath "dist\SimuladorBiomassa" -Recurse -Force }
if (Test-Path "dist") { Remove-Item -LiteralPath "dist" -Recurse -Force }
if (Test-Path "SimuladorBiomassa.exe") { Remove-Item -LiteralPath "SimuladorBiomassa.exe" -Force }

Write-Host "Gerando executavel..."
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "SimuladorBiomassa" `
  --distpath "." `
  --icon $iconPath `
  --add-data "app;app" `
  --add-data "src;src" `
  --add-data "data\input;data\input" `
  --add-data "requirements.txt;." `
  --collect-all streamlit `
  --collect-all altair `
  --collect-all openpyxl `
  launcher.py

Write-Host ""
Write-Host "Executavel gerado em: .\SimuladorBiomassa.exe"
Write-Host "Para testar: .\SimuladorBiomassa.exe"
