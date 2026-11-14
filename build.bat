@echo off
rem Build AscendInQ.exe into dist\AscendInQ\
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -c "import os; from ascendinq.icon import save_ico; os.makedirs('build_assets', exist_ok=True); save_ico('build_assets/icon.ico')" || exit /b 1
python -m PyInstaller --noconfirm --clean --windowed --name AscendInQ --icon build_assets\icon.ico --add-data "ascendinq\viewer_template.html;ascendinq" --add-data ".env.example;." app.py || exit /b 1
echo.
echo Built: dist\AscendInQ\AscendInQ.exe
