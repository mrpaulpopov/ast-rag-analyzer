@echo off
chcp 65001 >nul

set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

echo ========================================================
echo               Setup RAG Copy Script
echo ========================================================
echo.

set /p "USER_BASE_DIR=Please enter the path for BASE_DIR: "

if "%USER_BASE_DIR%"=="" (
    echo Error: No path entered. Setup aborted.
    pause
    exit /b
)
set "USER_BASE_DIR=%USER_BASE_DIR:"=%"

set "TARGET_FILE=copy_files_to_rag.bat"
set "TEMP_FILE=copy_files_to_rag.tmp"

if not exist "%TARGET_FILE%" (
    echo Error: "%TARGET_FILE%" not found in the current folder!
    pause
    exit /b
)

echo.
echo Updating %TARGET_FILE%...

setlocal DisableDelayedExpansion
(for /f "delims=" %%A in ('findstr /n "^" "%TARGET_FILE%"') do (
    set "fullLine=%%A"
    setlocal EnableDelayedExpansion

    set "line=!fullLine:*:=!"

    if "!line!"=="" (
        echo(
    ) else if "!line:~0,15!"=="set "TARGET_DIR=" (
        echo set "TARGET_DIR=!CURRENT_DIR!\incoming_files"
    ) else if "!line:~0,13!"=="set "BASE_DIR=" (
        echo set "BASE_DIR=!USER_BASE_DIR!"
    ) else (
        echo(!line!
    )
    endlocal
)) > "%TEMP_FILE%"

move /y "%TEMP_FILE%" "%TARGET_FILE%" >nul

echo.
echo [SUCCESS] Settings updated successfully!
echo.
echo TARGET_DIR : %CURRENT_DIR%\incoming_files
echo BASE_DIR   : %USER_BASE_DIR%
echo.

docker-compose up -d

echo.
pause