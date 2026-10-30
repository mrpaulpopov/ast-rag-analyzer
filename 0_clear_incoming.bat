@echo off
chcp 65001 >nul

set "TARGET_DIR=%~dp0incoming_files"

echo ========================================================
echo   Clearing incoming_files folder
echo ========================================================
echo.

if exist "%TARGET_DIR%" (
    echo Deleting contents...
    rd /s /q "%TARGET_DIR%"

    mkdir "%TARGET_DIR%"

    echo [SUCCESS] Folder cleared successfully!
) else (
    echo [INFO] Folder does not exist. Creating a new empty one...
    mkdir "%TARGET_DIR%"
    echo [SUCCESS] Folder created!
)

echo.
pause