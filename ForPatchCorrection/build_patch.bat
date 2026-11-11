@echo off
setlocal enabledelayedexpansion
set "root=%~dp0"
set "md=%~1"
if not defined md set "md=%root%..\md"
set "stage=%TEMP%\Tamayura-scenario-%RANDOM%-%RANDOM%"
set "sborka=%root%sborka_tamayura"
set "archive=%root%sborka_tamayura.xp3"
set "target_patch=%root%..\patch2.xp3"

if not exist "%sborka%\" (
    mkdir "%sborka%"
)
if exist "%archive%" (
    del /f /q "%archive%"
)

echo [1/4] Inserting translations from "%md%"...
python -X utf8 "%root%ks_excel_tool.py" insert "%md%" "%root%..\UNP" "%stage%"
if errorlevel 1 (
    echo Error during ks_excel_tool insert!
    exit /b 1
)

echo [2/4] Copying scenarios to sborka folder...
robocopy "%stage%" "%sborka%" *.ks /IS /IT /R:1 /W:1 /NJH /NJS /NDL /NFL >nul
rmdir /s /q "%stage%" >nul 2>&1

echo [3/4] Packing XP3 archive with Xp3Pack.exe...
pushd "%root%" || exit /b 1
"%root%Xp3Pack.exe" sborka_tamayura
set "pack_exit=%ERRORLEVEL%"
popd
if not "%pack_exit%"=="0" (
    echo Xp3Pack failed with code %pack_exit%!
    exit /b 1
)

if not exist "%archive%" (
    echo Xp3Pack did not create "%archive%"!
    exit /b 1
)

echo [4/4] Deploying patch2.xp3 to game root...
move /Y "%archive%" "%target_patch%" >nul
if errorlevel 1 (
    echo Failed to move archive to "%target_patch%"!
    exit /b 1
)

echo.
echo ===================================================
echo SUCCESS: Built and deployed "%target_patch%"!
echo Game will automatically load it on startup.
echo ===================================================
