"""Окно программы (страница в браузере на этом компьютере).

- job.py — запуск проверки (процесс crawl.py) и её состояние для окна;
- reports_list.py — список готовых отчётов: карточка на сайт, история проверок;
- server.py — маленький веб-сервер на 127.0.0.1 и открытие окна Chrome/Edge;
- page/ — сама страница: index.html, style.css, app.js.
Запуск — app.py в папке программы."""
import os

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # папка программы
# папка проверок - одна на всю программу: crawl.py, окно, семантика, каталог брендов. Автотесты подменяют её
# через CLAYLER_REPORTS (раньше переменную видел только crawl.py, а окно и семантика читали настоящую папку)
from .. import paths  # noqa: E402

REPORTS = paths.reports_dir()   # «reports» (или старая «reports», пока окно её не перенесло)
PAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page")
