"""Clayler SEO — краулер для технического SEO-аудита.

Примеры:
    python crawl.py https://example.ru
    python crawl.py https://example.ru --max-pages 50000 --threads 8
    python crawl.py https://example.ru --continue        (продолжить прерванный обход)
    python crawl.py https://example.ru --robots yandex --ua yandexbot

Здесь только запуск: сам код - в папке seocrawler/run/ (обход, сборка отчёта, семантика, списки адресов).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

# прежние имена crawl.<функция> - для автотестов и старых вызовов
from seocrawler.run.build import HEALTH_VERSION, build_report, status  # noqa: E402,F401
from seocrawler.run.cli import main  # noqa: E402
from seocrawler.run.extras import run_list, setup_js  # noqa: E402,F401
from seocrawler.run.history import later_crawl, previous_crawl, resume_settings, run_compare  # noqa: E402,F401
from seocrawler.run.semantics_run import run_semantics  # noqa: E402,F401


if __name__ == "__main__":
    main()
