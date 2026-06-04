@echo off
chcp 437 > nul
echo ==========================================================
echo   IoT Risk Sound Detection Project Integration (Windows)
echo ==========================================================
echo.

:: Check virtual environment
if not exist ".venv" (
    echo [ERROR] .venv folder not found.
    echo Please create virtual environment first.
    pause
    exit /b
)

echo Starting FastAPI Backend... (Port: 8000)
start "FastAPI Backend" cmd /k "call .venv\Scripts\activate && cd backend && uvicorn main:app --reload --port 8000"

echo Starting Flask Frontend... (Port: 5000)
start "Flask Frontend" cmd /k "call .venv\Scripts\activate && cd frontend && python app.py"

echo.
echo ==========================================================
echo   All modules have been started in separate windows.
echo   - Backend: http://127.0.0.1:8000
echo   - Frontend: http://127.0.0.1:5000
echo ==========================================================
echo.
pause
