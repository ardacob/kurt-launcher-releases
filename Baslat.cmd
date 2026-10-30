@echo off
setlocal
cd /d "%~dp0"
if exist "KurtLauncher.exe" (
    start "" "KurtLauncher.exe"
    exit /b
)
echo Kaynak surumu icin Python 3.12 veya daha yenisi gereklidir.
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Python bulunamadi. Python'u kurup yeniden deneyin.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Paketler yuklenemedi. Internet baglantisini kontrol edin.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" src\main.py
if errorlevel 1 pause
