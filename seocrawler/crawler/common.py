"""Настройки обхода (Config), ограничитель скорости и мелкие помощники."""
import os
import re
import threading
import time
from dataclasses import dataclass, field

from .. import jsonfile
from ..fmt import num as _n, plural as _plural  # noqa: F401 - _plural берут другие части crawler/


@dataclass
class Config:
    start_url: str
    max_pages: int = 10000          # сколько HTML-страниц сайта обойти
    max_depth: int = 50
    threads: int = 4
    delay: float = 0.2              # пауза между запросами (секунды, на все потоки вместе)
    timeout: float = 15
    total_timeout: float = 30       # сколько всего можно качать один адрес (медленная отдача файла)
    user_agent: str = "crawler"     # crawler / googlebot / yandexbot / chrome или своя строка
    robots_for: str = "googlebot"   # чьи правила robots.txt соблюдать: googlebot / yandex
    respect_robots: bool = True
    use_clean_param: bool = True    # Clean-param из robots.txt (правило Яндекса)
    strip_tracking: bool = True     # вырезать utm_*, gclid, yclid... перед постановкой в очередь
    max_params: int = 3             # URL с большим числом параметров не обходим
    follow_nofollow: bool = False
    crawl_subdomains: bool = False  # или набор поддоменов городов (заполняется при поиске городов)
    regions: bool = False           # сайт с городами: найти городские версии по переключателю города и обойти их
    check_external: bool = True     # проверять коды ответа внешних ссылок
    check_resources: bool = True    # проверять картинки
    crawl_canonicals: bool = True
    use_sitemap: bool = True        # прочитать sitemap.xml и сравнить с обходом
    crawl_sitemap: bool = False     # обходить адреса из sitemap как обычные страницы
    use_search_urls: bool = True    # взять адреса из Яндекс Вебмастера и Search Console и проверить те, где нет ссылок
    exclude: list = field(default_factory=list)  # регулярные выражения
    skip_masks: list = field(default_factory=list)  # «Не обходить адреса» из окна: маски с * (уже вошли в exclude)
    section: str = ""               # «Только этот раздел»: обходить только адреса, начинающиеся с этого адреса
    url_list: str = ""              # «Мой список адресов»: файл с адресами (по одному в строке), только они
    verify_ssl: bool = True
    retries: int = int(os.environ.get("CLAYLER_RETRIES") or 2)  # повторов при сбросе соединения и таймауте (автотест - 0)
    stop_file: str = ""             # если такой файл появился — остановить обход (кнопка «Стоп» в окне программы)
    status_file: str = ""           # сюда пишется состояние (шаг, страницы) для окна программы — JSON
    render_js: bool = False         # выполнять JavaScript во встроенном браузере
    render_tabs: int = 3            # сколько страниц рендерить одновременно
    render_wait: float = 5.0        # сколько секунд ждать, пока скрипты догрузят данные
    check_exposed: bool = True      # искать открытые служебные файлы (.git, .env, бэкапы) — только свой сайт
    extract: list = None            # правила «Свои данные со страниц» (seocrawler/extract.py); None - из файла правил


def mask_to_regex(mask):
    """Маска адреса из окна → регулярное выражение: * - любые символы, маска ищется в любом месте адреса,
    без учёта заглавных букв. «/filter/», «*?sort=*», «/tag/*/page-*»."""
    return "(?i)" + ".*".join(re.escape(p) for p in mask.strip().split("*"))


def read_masks(text):
    """Строки окна → маски: пустые и повторы убираются."""
    out = []
    for line in (text or "").splitlines():
        m = line.strip()
        if m and m.strip("*") and m not in out:
            out.append(m)
    return out


RES_DELAY = 0.05   # своя пауза для картинок и файлов своего сайта
# вкладок браузера на обычной и быстрой скорости (thehome.ru: 6 - 1,42 стр/с вместо 1,15, 9 - хуже)
JS_TABS = 6
JS_TABS_GENTLE = 3  # «Бережно»: нагрузка на сайт прежняя


def js_load(delay: float, threads: int, tabs: int = 0) -> tuple:
    """(вкладок браузера, потоков) для проверки с JavaScript. Потоков больше вкладок на 2: иначе вкладки стоят без дела,
    пока потоки заняты картинками. Не прибавляем на «Бережно» (пауза больше 0,2 с) и когда число вкладок задано явно:
    при проверке с конкурентами window/job.py нарочно даёт меньше, общий поток не должен расти."""
    if tabs:
        return max(1, tabs), threads
    if delay > 0.2:
        return JS_TABS_GENTLE, threads
    return JS_TABS, max(threads, JS_TABS + 2)


def res_delay(delay: float) -> float:
    """Пауза между своими картинками и файлами. Статику сервер отдаёт почти даром (thehome.ru: ответ 0,05 с, берём
    первые
    64 КБ), а при общей паузе 0,2 с 408 тыс. картинок шли ровно по 5 в секунду. «Бережно» (пауза больше 0,2 с) не
    ускоряем.
    Если сайт начнёт сбоить, пауза растёт как обычно (RateLimiter.backoff, shaky.py)."""
    return delay if delay > 0.2 else min(delay, RES_DELAY)


class RateLimiter:
    """Пауза между запросами одной очереди (на все её потоки вместе; у страниц сайта, его файлов и каждого чужого
    сайта очередь своя - crawler/base.limiter_for). «Умная»: если сервер отвечает быстро и без ошибок,
    пауза постепенно уменьшается до половины заданной; медленный ответ — снова заданная; ошибка сервера,
    «слишком много запросов» или обрыв — пауза растёт, и до конца обхода быстрее заданной уже не будет."""
    FAST = 0.5       # ответ быстрее — сервер справляется
    SLOW = 1.5       # ответ дольше — сервер нагружен

    def __init__(self, delay, speed_up=True):
        self.delay = self.base = delay
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.hold = 0.0  # до этого времени никто не идёт к сайту: сервер попросил паузу (backoff, calm)
        # «Бережно» (пауза 1 с) не ускоряем; speed_up=False - пауза и так короткая (res_delay)
        self.floor = delay * 0.5 if speed_up and 0 < delay <= 0.3 else delay
        self.fast_ok = True

    def wait(self, stop=None):
        """Дождаться своей очереди. stop - функция «пора остановиться?»: тогда ожидание прерывается и
        возвращается False. Поток, занявший время до того, как сервер попросил паузу, ждёт и её: раньше после
        429/503 уже стоявшие в очереди потоки шли к сайту по старому расписанию (ревизия кода)."""
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next_at)
            self.next_at = at + self.delay
        while True:
            while True:
                left = at - time.monotonic()
                if stop is not None and stop():
                    return False
                if left <= 0:
                    break
                time.sleep(min(left, 0.5) if stop is not None else left)
            with self.lock:
                now = time.monotonic()
                if now >= self.hold:
                    return True
                at = max(self.hold, self.next_at)
                self.next_at = at + self.delay

    def success(self, elapsed=None):
        with self.lock:
            if self.delay > self.base:
                # после торможения постепенно возвращаемся к исходной скорости
                self.delay = max(self.base, self.delay * 0.9)
            elif elapsed is not None and elapsed > self.SLOW:
                self.delay = self.base
            elif elapsed is not None and elapsed < self.FAST and self.fast_ok:
                self.delay = max(self.floor, self.delay * 0.97)

    def server_error(self):
        """Ответ 5xx: сервер не справляется — больше не ускоряемся."""
        with self.lock:
            self.fast_ok = False
            self.delay = max(self.delay, self.base)

    def backoff(self, seconds):
        with self.lock:
            self.fast_ok = False
            self.delay = min(max(self.delay * 2, 0.5), 5.0)
            self.next_at = max(self.next_at, time.monotonic() + seconds)
            self.hold = max(self.hold, time.monotonic() + seconds)

    def calm(self, seconds, min_delay):
        """Сайт отвечает через раз (crawler/shaky.py): пауза и пауза между запросами не меньше min_delay,
        пока не вызовут uncalm()."""
        with self.lock:
            if not hasattr(self, "orig"):
                self.orig = self.base
            self.fast_ok = False
            self.base = max(self.base, min_delay)
            self.delay = max(self.delay, self.base)
            self.next_at = max(self.next_at, time.monotonic() + seconds)
            self.hold = max(self.hold, time.monotonic() + seconds)

    def uncalm(self):
        with self.lock:
            self.base = getattr(self, "orig", self.base)


def retry_after(value, default=10, cap=60):
    """Сколько секунд ждать по заголовку Retry-After (ответы 429/503). Бывает числом секунд или датой
    («Wed, 21 Oct 2026 07:28:00 GMT», RFC 9110) - раньше дата не понималась и всегда ждали 10 с. Не меньше 1 и не
    больше cap; пусто или непонятно - default."""
    v = (value or "").strip()
    if not v:
        return default
    if v.isdigit():
        return max(1, min(int(v), cap))
    try:
        from datetime import timezone
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(1, min(int(dt.timestamp() - time.time() + 0.999), cap))
    except (TypeError, ValueError, IndexError, OverflowError):
        return default


def scope_key(url):
    """Адрес без http(s):// и www. — чтобы раздел и список адресов не зависели от того, как адрес написан."""
    u = url.split("://", 1)[-1]
    return u[4:] if u.startswith("www.") else u


def read_url_list(path):
    """Адреса из файла: по одному в строке, без повторов, в исходном порядке. Только полные (http/https)."""
    from .. import urls as U
    out, seen = [], set()
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            for raw in line.replace(",", " ").replace(";", " ").split():
                if "://" not in raw:
                    continue
                n = U.normalize(raw)
                if n and scope_key(n) not in seen:
                    seen.add(scope_key(n))
                    out.append(n)
    return out


def write_status(path, data):
    """Атомарно: сначала во временный файл, потом замена — окно не прочитает полузаписанный файл."""
    try:
        jsonfile.save(path, data)
    except OSError:
        pass


def _ago(sec):
    sec = int(sec)
    return f"{sec // 60} мин {sec % 60} с" if sec >= 60 else f"{sec} с"
