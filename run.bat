@echo off
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python main.py
