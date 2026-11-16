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
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 (
  echo Нужен Python 3.10 или новее, а установлен:
  %PY% --version
  echo Скачайте свежий с https://www.python.org/downloads/ и запустите этот файл снова.
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

rem Встроенный браузер Chromium: снимки страниц с обведённой ошибкой, вид на телефоне, скорость, кнопки покупки
rem и проверка с JavaScript. Ставится один раз (около 150-200 МБ), потом эта часть пропускается.
if not exist "data\.chromium-ready" (
  echo Один раз готовлю встроенный браузер Chromium: снимки ошибок, вид на телефоне, проверка с JavaScript.
  echo Нужен интернет, скачается около 150-200 МБ. Это займёт несколько минут, дальше запуск будет быстрым.
  %PY% crawl.py --setup-js
  if errorlevel 1 (
    echo Браузер подготовить не получилось. Программа работает, но без снимков страниц и проверки с JavaScript.
    echo Попробую ещё раз при следующем запуске.
  ) else (
    if not exist "data" mkdir "data"
    echo готово> "data\.chromium-ready"
  )
  echo.
)

%PY% app.py
pause
