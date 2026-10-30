@echo off
chcp 65001 >nul

echo ========================================================
echo   Starting Update Pipeline in Docker...
echo ========================================================
echo.

docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/update_pipeline.py

echo.
pause