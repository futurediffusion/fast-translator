@echo off

rem Update repository
git pull

rem Create virtual environment if it doesn't exist
if not exist venv (
    python -m venv venv
)

rem Activate the virtual environment
call venv\Scripts\activate

rem Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

rem Run the translator
python floating_translator.py
