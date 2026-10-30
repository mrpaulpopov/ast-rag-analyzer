@echo off
chcp 65001 >nul

echo ========================================================
echo   Starting Inference Pipeline in Docker...
echo ========================================================
echo.

docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/inference_pipeline.py

echo.
pause