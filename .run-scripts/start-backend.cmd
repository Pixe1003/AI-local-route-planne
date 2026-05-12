@echo off
set "PYTHONPATH=D:\Codex ??\POI???? longcat api\AI-local-route-planne\.run-backend-20260511164418"
cd /d "D:\Codex ??\POI???? longcat api\AI-local-route-planne"
"E:\Miniconda\envs\ai_agent\python.exe" -m uvicorn app.main:app --app-dir "D:\Codex ??\POI???? longcat api\AI-local-route-planne\.run-backend-20260511164418" --host 127.0.0.1 --port 8000 >> ".run-logs\backend.detached.log" 2>&1
