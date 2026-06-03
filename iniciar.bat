@echo off
cd /d C:\Users\octav\football-predictor
start "Flask API" py src/app.py
timeout /t 3 /nobreak > nul
start "Telegram Bot" py bot.py
start "" "http://localhost:5000"
echo Flask y Bot iniciados. Cerrá esta ventana cuando quieras detenerlos.
pause
