@echo off
chcp 65001 >nul 2>&1
python "%~dp0generate_gallery.py" "%~dp0."
pause
