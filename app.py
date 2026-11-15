"""Clayler SEO — окно программы в браузере.

Запуск: python app.py (или двойной щелчок по «Clayler SEO.bat»). Откроется страница в браузере:
там запуск проверки, прогресс и список всех отчётов. Сервер работает только на этом компьютере
(адрес 127.0.0.1), из интернета к нему не подключиться.
Сам код окна — в папке seocrawler/window.
"""
import os

# свои файлы - в папку «data» до того, как модули окна запомнят пути к ним (seocrawler/paths.py)
from seocrawler import paths
paths.migrate()
from seocrawler.window import REPORTS  # noqa: E402
from seocrawler.window.server import main  # noqa: E402

os.makedirs(REPORTS, exist_ok=True)

if __name__ == "__main__":
    main()
