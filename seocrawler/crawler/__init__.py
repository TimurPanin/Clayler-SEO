"""Краулер: очередь -> загрузчик -> парсер -> новые URL обратно в очередь.

Класс Crawler собран из частей (каждая — свой файл):
- base.py — общее: настройки, загрузчики, журнал, паузы и «Стоп»;
- queue.py — очередь адресов и robots.txt;
- sitemaps.py — карты сайта;
- page.py — загрузка и разбор одной страницы;
- extra_passes.py — дополнительные проходы после обхода;
- main_loop.py — главный цикл (run);
- shaky.py — сайт отвечает через раз: пауза, меньше потоков, повтор адресов без ответа;
- access.py — сайт не открывается: понятная причина (режут по дороге, не пускает программы);
- common.py — Config (настройки обхода) и мелкие помощники."""
from .common import Config, RateLimiter, write_status, _plural, _n  # noqa: F401
from .base import Base
from .queue import QueueMixin
from .sitemaps import SitemapsMixin
from .page import PageMixin
from .extra_passes import ExtraPassesMixin
from .main_loop import MainLoopMixin
from .shaky import ShakyMixin
from .access import AccessMixin


class Crawler(MainLoopMixin, ShakyMixin, AccessMixin, ExtraPassesMixin, PageMixin, SitemapsMixin, QueueMixin, Base):
    """Весь обход сайта. Запуск: Crawler(Config(...), путь_к_базе).run()"""
