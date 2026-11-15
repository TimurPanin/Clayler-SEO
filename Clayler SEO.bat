@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title Clayler SEO

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo Python не найден.
  echo Скачайте его с https://www.python.org/downloads/ и при установке
  echo поставьте галочку "Add python.exe to PATH". Потом запустите этот файл снова.
  pause
  exit /b
)

rem Модули: truststore - проверка HTTPS как в браузере, openpyxl - отчёт в Excel. Ставятся один раз.
%PY% -c "import truststore, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo Один раз устанавливаю модули truststore и openpyxl...
  %PY% -m pip install --quiet --disable-pip-version-check truststore openpyxl >nul 2>nul
  echo.
)

%PY% app.py
pause
