@echo off
REM Fingerprint Bridge Service Configuration
REM Copy this file to config.bat and edit values

SET GYM_API_URL=https://your-gym-system.railway.app
SET GYM_API_KEY=your-api-key-here
SET FINGERPRINT_IP=192.168.1.224
SET FINGERPRINT_PORT=5005
SET SYNC_INTERVAL=30

REM Run the bridge service
python bridge.py
