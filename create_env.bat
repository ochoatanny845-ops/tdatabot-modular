@echo off
echo Creating clean .env file...
(
echo # Bot Configuration
echo TOKEN=8330585611:AAGv4e7RmCWa1S8xpN3LKxZG2MakBl5GWkE
echo API_ID=2040
echo API_HASH=b18441a1ff607e10a989891a5462e627
echo.
echo # Admin Configuration
echo ADMIN_IDS=5991190607,2011437257,5566433309,1329956615
echo.
echo # Performance
echo MAX_CONCURRENT_CHECKS=100
echo CHECK_TIMEOUT=15
echo SPAMBOT_WAIT_TIME=2.0
echo TDATA_PIPELINE_CONVERT_CONCURRENT=100
echo TDATA_PIPELINE_CHECK_CONCURRENT=50
echo TDATA_PIPELINE_CONVERT_TIMEOUT=5
echo.
echo # Proxy
echo USE_PROXY=true
echo PROXY_TIMEOUT=60
echo PROXY_FILE=proxy.txt
echo.
echo # Database
echo DATABASE_PATH=bot_data.db
) > .env

echo .env file created successfully!
echo Now you can run: python run.py
pause
