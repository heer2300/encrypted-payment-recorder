@echo off
echo Installing PyInstaller...
python -m pip install pyinstaller
echo.
echo Building exe...
python -m PyInstaller --onefile --noconsole --name PaymentRecords payment_records.py
echo.
echo Done! Your exe is in the "dist" folder: dist\PaymentRecords.exe
pause
