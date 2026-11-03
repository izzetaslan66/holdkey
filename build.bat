@echo off
rem BasiliTut.exe oluşturur (dist klasörüne)
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name BasiliTut --icon assets\icon.ico --add-data "assets\icon.ico;assets" basili_tut.pyw
echo.
echo Bitti: dist\BasiliTut.exe
pause
