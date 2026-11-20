@echo off
REM Opens the local TFM dashboard in your browser (http://127.0.0.1:8502). Close this window to stop it.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m streamlit run dashboard\app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
pause
