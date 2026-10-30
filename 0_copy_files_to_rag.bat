@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================================
echo      Copy files to RAG (Preserving Hierarchy)
echo ========================================================
echo.

:: 1. SET THE PATH TO YOUR DOCKER PROJECT'S incoming_files FOLDER
set "TARGET_DIR=C:\Users\YourName\AST-RAG\incoming_files"

:: 2. SET THE PATH TO YOUR PERFORCE REPOSITORY ROOT
:: Since the script is on the Desktop, we must define the repo path explicitly
set "BASE_DIR=C:\Users\YourName\PerforceWorkspace"

:: Check if files were dragged and dropped
if "%~1"=="" (
    echo Warning: Drag and drop modified .py files directly onto this script icon!
    echo.
    pause
    exit /b
)

:loop
if "%~1"=="" goto done

:: Absolute path of the dragged file
set "FILE_PATH=%~1"

:: Remove the base repository path to get the relative path
:: (Example: C:\P4\repo\src\utils.py -> \src\utils.py)
set "REL_PATH=!FILE_PATH:%BASE_DIR%=!"

:: Security check: if the file is not from the base repository, skip it
if "!REL_PATH!"=="!FILE_PATH!" (
    echo [SKIPPED] File is not from the specified repository: %FILE_PATH%
) else (
    :: Remove leading backslash if present
    if "!REL_PATH:~0,1!"=="\" set "REL_PATH=!REL_PATH:~1!"

    :: Construct the final destination path in the incoming_files folder
    set "DEST_FILE=%TARGET_DIR%\!REL_PATH!"

    :: Extract the destination folder path and create it if it doesn't exist
    for %%I in ("!DEST_FILE!") do set "DEST_FOLDER=%%~dpI"
    if not exist "!DEST_FOLDER!" mkdir "!DEST_FOLDER!"

    :: Copy the file quietly
    copy /Y "!FILE_PATH!" "!DEST_FILE!" >nul
    echo [COPIED] !REL_PATH!
)

:: Move to the next dragged file
shift
goto loop

:done
echo.
echo All files transferred! You can now run Docker.
pause