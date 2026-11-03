@echo off
rem HoldKey.exe oluşturur (dist klasörüne)
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name HoldKey --icon assets\icon.ico --add-data "assets\icon.ico;assets" holdkey.pyw
echo.
echo Bitti: dist\HoldKey.exe
pause
