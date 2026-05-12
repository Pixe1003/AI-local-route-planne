@echo off
cd /d "D:\Codex ??\POI???? longcat api\AI-local-route-planne\frontend"
npm.cmd run dev -- --host 127.0.0.1 --port 5173 >> "..\.run-logs\frontend.detached.log" 2>&1
