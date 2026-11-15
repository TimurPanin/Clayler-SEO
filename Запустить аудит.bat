@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

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

rem Модули: truststore - проверка HTTPS-сертификатов как в браузере, openpyxl - отчёт в Excel. Ставятся один раз.
%PY% -c "import truststore, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo Один раз устанавливаю модули truststore и openpyxl: проверка HTTPS как в браузере и отчёт в Excel...
  %PY% -m pip install --quiet --disable-pip-version-check truststore openpyxl >nul 2>nul
  %PY% -c "import truststore, openpyxl" >nul 2>nul
  if errorlevel 1 (echo Не получилось, работаю без них. Отчёт в браузере и CSV-файлы будут в любом случае.) else (echo Готово.)
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

echo ============================================================
echo   Clayler SEO - технический аудит сайта
echo ============================================================
echo.
echo Программа обойдёт сайт по ссылкам, как поисковый робот,
echo и соберёт отчёт с ошибками. Отчёт откроется в браузере сам.
echo Нужно ответить на 4 вопроса.
echo.
set /p SITE=1. Адрес сайта (например, https://example.ru): 
if "%SITE%"=="" exit /b
echo.
echo 2. Сколько страниц проверить?
echo    500   - быстрая проба, обычно 5-10 минут
echo    10000 - большинство сайтов целиком
echo    Картинки и ссылки на другие сайты в это число не входят.
set /p PAGES=   Число (просто Enter = 10000): 
if "%PAGES%"=="" set PAGES=10000
echo.
echo 3. Выполнять JavaScript, как это делает Google?
echo    Нужно, если сайт сделан на React, Vue, Angular или меню и каталог подгружаются скриптами.
echo    Проверка будет в несколько раз медленнее.
echo    д - да,  н или Enter - нет.
set /p JS=   Ваш ответ: 
set JSFLAG=
if /i "%JS%"=="д" set JSFLAG=--js
if /i "%JS%"=="да" set JSFLAG=--js
if /i "%JS%"=="y" set JSFLAG=--js
if defined JSFLAG (
  %PY% crawl.py --setup-js
  if errorlevel 1 set JSFLAG=
)
echo.
echo 4. Продолжить прошлую проверку этого сайта с того места, где она остановилась?
echo    д - продолжить,  н или Enter - начать заново.
set /p CONT=   Ваш ответ: 
set EXTRA=
if /i "%CONT%"=="д" set EXTRA=--continue
if /i "%CONT%"=="да" set EXTRA=--continue
if /i "%CONT%"=="y" set EXTRA=--continue
echo.

%PY% crawl.py "%SITE%" --max-pages %PAGES% %EXTRA% %JSFLAG%
echo.
echo Окно можно закрыть.
pause
