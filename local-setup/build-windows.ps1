$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Build this executable on Windows, not Linux or macOS." }
$Root = Split-Path $PSScriptRoot -Parent
Push-Location $Root
try {
  # Build-time dependencies only; end users do not need Python, pip, or this script.
  python -m pip install --disable-pip-version-check ".[ollama,documents,dev]" "pyinstaller==6.16.0"
  if ($LASTEXITCODE -ne 0) { throw "Could not install build dependencies." }
  python -m PyInstaller --noconfirm --clean --onefile --console --noupx `
    --name LangFORM --paths "$Root/src" --paths "$Root/local-setup" `
    --collect-all langform --collect-all docx --collect-all pypdf `
    --collect-all openpyxl --collect-all requests --collect-all certifi `
    --hidden-import tkinter --hidden-import tkinter.messagebox --hidden-import tkinter.filedialog `
    --distpath generated-artifacts/windows --workpath generated-artifacts/windows-build `
    --specpath generated-artifacts/windows-build local-setup/windows-companion.py
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
  & ".\generated-artifacts\windows\LangFORM.exe" --smoke-test
  if ($LASTEXITCODE -ne 0) { throw "The executable smoke check failed." }
  Copy-Item local-setup/WINDOWS-README.txt generated-artifacts/windows/README.txt
  $Hash = (Get-FileHash generated-artifacts/windows/LangFORM.exe -Algorithm SHA256).Hash.ToLower()
  "$Hash  LangFORM.exe" | Set-Content generated-artifacts/windows/SHA256SUMS.txt -Encoding ascii
  Compress-Archive -Path generated-artifacts/windows/* -DestinationPath generated-artifacts/LangFORM-windows-x64.zip -Force
  Write-Host "Built generated-artifacts/LangFORM-windows-x64.zip"
} finally {
  Pop-Location
}
