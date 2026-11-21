$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt
python -m pip install pillow -q
python make_icon.py
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "Camera Shutter Count" `
  --icon (Join-Path $PSScriptRoot "icon.ico") `
  --add-data "icon.ico;." `
  --hidden-import shutter_count `
  --hidden-import cameras `
  --hidden-import comtypes `
  --hidden-import comtypes.client `
  --hidden-import comtypes.stream `
  --collect-submodules comtypes `
  app.py

$built = Join-Path $PSScriptRoot "dist\Camera Shutter Count.exe"
$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Camera Shutter Count.exe"
if (Test-Path $built) {
    Copy-Item $built $desktop -Force
    Write-Host "Built: $built"
    Write-Host "Copied to Desktop: $desktop"
} else {
    throw "Build finished but the exe was not found."
}
