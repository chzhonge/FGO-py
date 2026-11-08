@echo off
title FGO-py
set PYTHONUTF8=1
set "_root=%~dp0"
set "PATH=%_root%Python311;%_root%Python311\Scripts;%_root%Git\mingw64\bin;%PATH%"
cd "%_root%FGO-py\FGO-py"
@REM set /p update_choice="Check for updates? (Y/N) [N]: "
@REM if /I "%update_choice%"=="Y" (
@REM     python ../../deploy/updater.py
@REM     if errorlevel 1 (
@REM         echo "Update failed. See above."
@REM         pause
@REM         exit
@REM     )
@REM )
python fgo.py %*