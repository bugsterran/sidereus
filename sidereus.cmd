@echo off
rem py launcher first; python.org installs without it only have python on PATH
where py >nul 2>nul
if %errorlevel%==0 (py -3 "%~dp0sidereus_cli.py" %*) else (python "%~dp0sidereus_cli.py" %*)
