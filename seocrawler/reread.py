"""Дочитать с сайта при сборке отчёта то, чего обход не открывал и не сохранил. Каждое - один раз на проверку.

Функции появились из разбора thehome.ru, суть одна - закон сохранения (ИНЖЕНЕРНЫЕ_ПРАВИЛА, 1а):
- ensure_redirect_ends: 699 редиректов вели на адреса, закрытые в robots.txt. Обход такие адреса не открывает, код там
  был неизвестен, и отчёт молча считал редирект нормальным, хотя 192 из 672 таких адресов отдают 404.
- ensure_sitemap_blocks: у адресов из sitemap не сохранялся текст страницы, поэтому 5 425 удалённых товаров
  («Элемент не найден», код 200) попали в «страницы-сироты» с текстом «эти страницы работают». Новые проверки текст
  таких страниц сохраняют сами (crawler/page.handle), здесь - для уже готовых.
- ensure_sitemap_absent: у готовых проверок sitemap считался «нет» только при 404 и 410, а не при странице вместо файла.
Адрес без ответа в итог не пишется: нет ответа - ещё не значит ошибка сайта, в отчёте он останется «не проверялся»."""
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from . import site_auth
from .crawler.common import RateLimiter
from .fetcher import HTML_TYPES, REDIRECTS, UA_PRESETS, Fetcher
from .parser import parse_html
from .robots import CLOSED_LIKE, sitemap_gone

END_LIMIT = 3000    # адресов за один раз: больше на обычном сайте не бывает, а отчёт не должен ждать часами
BLOCKS_LIMIT = 20000  # страниц за один раз
BLOCKS_THREADS = 4  # как обычный обход; пауза между запросами - из настроек проверки
MISSES_STOP = 20    # столько подряд без ответа - сайт перестал отвечать, ждать таймаут каждого адреса незачем
SAVE_EVERY = 200    # промежуточное сохранение: остановка сборки не теряет сделанное
HOPS = 5            # редиректов подряд от закрытого адреса


def _site_fetcher(store):
    """Загрузчик с настройками этой проверки (тот же робот). Возвращает (загрузчик, пауза между запросами)."""
    cfg = store.get_meta("config", None) or {}
    ua = cfg.get("user_agent") or "crawler"
    fetcher = Fetcher(UA_PRESETS.get(ua, ua), timeout=15, total_timeout=30, verify_ssl=cfg.get("verify_ssl", True))
    # закрытый сайт: без входа каждый адрес ответил бы 401, и вышли бы ложные «редирект ведёт на ошибку»
    fetcher.host_headers.update(site_auth.login_headers(store.get_meta("start", "") or ""))
    return fetcher, cfg.get("delay", 0.2)


def closed_redirect_targets(db) -> list:
    """Адреса, куда ведут редиректы сайта, закрытые в robots.txt (обход их не открывал)."""
    return [r[0] for r in db.execute(
        "SELECT DISTINCT p.location FROM pages p JOIN urls u ON u.url=p.location "
        "WHERE p.location<>'' AND u.state='skipped' AND u.skip_reason LIKE ?", (CLOSED_LIKE,))]


def _end_status(fetcher, url, pause):
    """Код в конце пути от адреса: сам адрес может перенаправлять дальше. 0 или None - не ответил или конца не видно."""
    for _ in range(HOPS + 1):
        r = fetcher.fetch(url, read_body=False)
        time.sleep(pause)
        if r.status not in REDIRECTS or not r.location:
            return r.status
        url = urljoin(url, r.location)
    return None


def _save_ends(store, ends, total, done):
    store.set_meta("redirect_ends", {"ends": ends, "total": total, "done": done})
    store.commit()


def _read_ends(store, todo, ends, total, log) -> bool:
    """Дочитать коды, по пути сохраняя. False - сайт перестал отвечать, остальное при следующей сборке."""
    fetcher, pause = _site_fetcher(store)
    misses = 0
    for n, url in enumerate(todo, 1):
        code = _end_status(fetcher, url, pause)
        if code:
            ends[url], misses = code, 0
        else:
            misses += 1
        if misses >= MISSES_STOP:
            log(f"Сайт перестал отвечать ({misses} адресов подряд): остальные адреса посмотрю при следующей сборке.")
            return False
        if not n % SAVE_EVERY:
            _save_ends(store, ends, total, False)
    return True


def ensure_redirect_ends(store, log=print) -> None:
    """meta «redirect_ends»: {ends: {адрес: код в конце}, total, done}. Читает analyze/prepare."""
    old = store.get_meta("redirect_ends", None) or {}
    if old.get("done"):
        return
    targets = closed_redirect_targets(store.db)
    ends = dict(old.get("ends") or {})   # прошлую сборку остановили или сайт не отвечал - продолжаем с этого места
    todo = [u for u in targets if u not in ends][:END_LIMIT]
    done = True
    if todo:
        log(f"Смотрю, что отвечают адреса, закрытые в robots.txt, на которые ведут редиректы: {len(todo)}...")
        done = _read_ends(store, todo, ends, len(targets), log)
    _save_ends(store, ends, len(targets), done)


def _read_blocks(store, urls, log) -> tuple:
    """Дочитать текст страниц. (сколько дочитано, ответил ли сайт хоть раз, перестал ли отвечать)."""
    fetcher, pause = _site_fetcher(store)
    limiter = RateLimiter(pause)

    def fetch(url):
        limiter.wait()
        return url, fetcher.fetch(url)
    done = misses = 0
    answered = False
    pool = ThreadPoolExecutor(BLOCKS_THREADS)
    for url, r in pool.map(fetch, urls[:BLOCKS_LIMIT]):
        answered = answered or bool(r.status)
        misses = 0 if r.status else misses + 1
        if misses >= MISSES_STOP:
            log("Сайт перестал отвечать: остальные страницы дочитаю при следующей сборке.")
            break
        if r.status == 200 and r.body:
            blocks = parse_html(r.body, r.headers.get("content-type", "")).get("blocks")
            store.db.execute("UPDATE pages SET blocks=? WHERE url=?", (blocks, url))
            done += 1
            if not done % SAVE_EVERY:
                store.commit()
    pool.shutdown(wait=False, cancel_futures=True)
    return done, answered, misses >= MISSES_STOP


def ensure_sitemap_blocks(store, log=print) -> None:
    """Текст страниц из sitemap без H1 (кандидаты в пустые страницы) для готовых проверок: колонка blocks."""
    if store.get_meta("sitemap_blocks", None) is not None:
        return
    urls = [r[0] for r in store.db.execute(
        "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND u.kind='sitemap' AND p.status=200 "
        f"AND p.content_type IN {HTML_TYPES!r} AND p.blocks IS NULL AND (p.h1 IS NULL OR p.h1='')")]
    done, answered, stopped = 0, False, False
    if urls:
        log(f"Дочитываю страницы из sitemap без заголовка H1: {len(urls)}...")
        done, answered, stopped = _read_blocks(store, urls, log)
    # сайт не отвечал - в следующий раз продолжим (дочитанных в запросе уже нет); ответил, но не 200 - читать незачем
    if not stopped and (answered or not urls):
        store.set_meta("sitemap_blocks", {"pages": done, "of": len(urls)})
    store.commit()


def ensure_sitemap_absent(store) -> None:
    """Готовые проверки: нет ли sitemap (crawler/sitemaps различает это сам у новых). Один раз."""
    if store.get_meta("sitemap_absent", False) or store.get_meta("sitemap_rechecked", False) \
            or store.db.execute("SELECT 1 FROM sitemap LIMIT 1").fetchone():
        return
    urls = store.get_meta("sitemaps", []) or []
    if not urls:
        return
    fetcher, pause = _site_fetcher(store)

    def gone(url):
        r = fetcher.fetch(url, any_type=True)
        time.sleep(pause)
        return sitemap_gone(r.status, r.body)
    store.set_meta("sitemap_absent", all(gone(u) for u in urls))
    store.set_meta("sitemap_rechecked", True)
    store.commit()
