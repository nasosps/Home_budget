@echo off
setlocal
cd /d "%~dp0"
python scripts\watch_bank_files.py %*
endlocal
