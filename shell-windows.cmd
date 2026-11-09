@echo off
rem BMW iDrive 8.5 emulator for Windows - see docs\WINDOWS.md
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\shell.ps1" %*
exit /b %ERRORLEVEL%
