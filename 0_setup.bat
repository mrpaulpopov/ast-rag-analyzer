@echo off
chcp 65001 >nul

set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

set "DEST_INCOMING_PATH=%CURRENT_DIR%\incoming_files"

echo ========================================================
echo               Setup RAG Copy Script
echo ========================================================
echo.

set /p "SRC_REPO_PATH=Please enter the Repository Path (former BASE_DIR): "

if "%SRC_REPO_PATH%"=="" (
    echo Error: No path entered. Setup aborted.
    pause
    exit /b
)
set "SRC_REPO_PATH=%SRC_REPO_PATH:"=%"

set "TARGET_FILE=%CURRENT_DIR%\0_copy_files_to_rag.bat"
set "TEMP_FILE=%CURRENT_DIR%\0_copy_files_to_rag.tmp"

if not exist "%TARGET_FILE%" (
    echo Error: "%TARGET_FILE%" not found in the current folder!
    pause
    exit /b
)

echo.
echo Updating copy_files_to_rag.bat...

setlocal DisableDelayedExpansion
(for /f "delims=" %%A in ('findstr /n "^" "%TARGET_FILE%"') do (
    set "fullLine=%%A"
    setlocal EnableDelayedExpansion

    set "line=!fullLine:*:=!"

    if "!line!"=="" (
        echo(
    ) else if /I "!line:~0,16!"=="set "TARGET_DIR=" (
        echo set "TARGET_DIR=!DEST_INCOMING_PATH!"
    ) else if /I "!line:~0,14!"=="set "BASE_DIR=" (
        echo set "BASE_DIR=!SRC_REPO_PATH!"
    ) else (
        echo(!line!
    )
    endlocal
)) > "%TEMP_FILE%"

move /y "%TEMP_FILE%" "%TARGET_FILE%" >nul

set "ENV_FILE=%CURRENT_DIR%\.env"
set "ENV_TEMP=%CURRENT_DIR%\.env.tmp"

if exist "%ENV_FILE%" (
    echo Updating .env...
    setlocal DisableDelayedExpansion
    (for /f "delims=" %%A in ('findstr /n "^" "%ENV_FILE%"') do (
        set "fullLine=%%A"
        setlocal EnableDelayedExpansion

        set "line=!fullLine:*:=!"

        if "!line!"=="" (
            echo(
        ) else if /I "!line:~0,11!"=="TARGET_DIR=" (
            echo TARGET_DIR=!SRC_REPO_PATH!
        ) else (
            echo(!line!
        )
        endlocal
    )) > "%ENV_TEMP%"

    move /y "%ENV_TEMP%" "%ENV_FILE%" >nul
) else (
    echo [WARNING] .env not found in the current folder! Skipping.
)

echo.
echo [SUCCESS] Settings updated successfully!
echo.
echo [copy_files_to_rag.bat]
echo   - TARGET_DIR : %DEST_INCOMING_PATH%
echo   - BASE_DIR   : %SRC_REPO_PATH%
echo.
echo [.env file]
echo   - TARGET_DIR : %SRC_REPO_PATH%
echo.

docker-compose up -d

echo.
pause