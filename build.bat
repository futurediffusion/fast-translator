@echo off

rem Build the Floating Translator executable

rem Create virtual environment if it doesn't exist
if not exist venv (
    python -m venv venv
)

rem Activate the virtual environment
call venv\Scripts\activate

rem Ensure build dependencies
pip install --upgrade pip
pip install pyinstaller

rem Package the application into a single executable with custom icon
pyinstaller --noconsole --onefile --icon icon.ico floating_translator.py

echo.
echo Build complete. The executable can be found in the dist folder.

