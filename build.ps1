$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ gerekli.' }
}
$launcherPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $launcherPython -m pip install -r requirements.txt 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Paketler yuklenemedi.' }
$env:KURT_BUILD_MODE = 'folder'
& $launcherPython -m PyInstaller --noconfirm --clean --distpath release --workpath .build KurtLauncher.spec
if ($LASTEXITCODE -ne 0) { throw 'Derleme basarisiz.' }
Write-Host 'Hazir: release\KurtLauncher\KurtLauncher.exe'
