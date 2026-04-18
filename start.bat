@echo off
chcp 65001 >nul
cd /d C:\Users\Administrator\.openclaw\workspace\tdatabot-modular
set PYTHONIOENCODING=utf-8
python run.py
pause
