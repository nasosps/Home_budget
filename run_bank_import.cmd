@echo off
setlocal
cd /d "%~dp0"
python scripts\process_bank_files.py %*
endlocal
