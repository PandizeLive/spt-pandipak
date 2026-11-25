@echo off
setlocal
powershell.exe -NoProfile -STA -ExecutionPolicy RemoteSigned -File "%~dp0Update-Pandipak.ps1" %*
set "rc=%ERRORLEVEL%"
pause
exit /b %rc%
