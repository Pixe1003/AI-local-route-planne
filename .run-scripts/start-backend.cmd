@echo off
cd /d "%~dp0.."
set "PYTHONPATH=backend"
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 >> ".run-logs\backend.detached.log" 2>&1
