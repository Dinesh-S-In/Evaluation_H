@echo off
cd /d "%~dp0"
copy /b Project_Task.7z.001 + Project_Task.7z.002 + Project_Task.7z.003 + Project_Task.7z.004 "Project_Task (2).7z"
echo.
echo Merged into "Project_Task (2).7z"
certutil -hashfile "Project_Task (2).7z" SHA256
echo Expected:
type SHA256.txt
pause
