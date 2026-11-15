"""Общее: настройки, загрузчики, журнал, состояние для окна, паузы и «Стоп»."""
import os
import re
import time
from .. import urls as U
from ..fetcher import Fetcher, UA_PRESETS
from ..storage import Store
from .common import Config, RateLimiter, res_delay, write_status, scope_key, read_url_list


class Base:
    def __init__(self, cfg: Config, db_path: str, log=print):
        self.cfg = cfg
        self._print = log
        self._st = {}
        self.store = Store(db_path)
        self.store_path = db_path
        ua = UA_PRESETS.get(cfg.user_agent, cfg.user_agent)
        self.fetcher = Fetcher(ua, timeout=cfg.timeout, verify_ssl=cfg.verify_ssl, total_timeout=cfg.total_timeout)
        # запасной загрузчик без проверки сертификата: чтобы понять, отвечает ли сайт вообще
        self.insecure = Fetcher(ua, timeout=cfg.timeout, verify_ssl=False, total_timeout=cfg.total_timeout)
        self.limiter = RateLimiter(cfg.delay)
        # Свои картинки, стили и скрипты — своя очередь пауз: на torrefacto.ru их 12 тыс. на 2 тыс. страниц,
        # и в общей очереди они забирали у страниц две трети ходов. Ссылки на другие сайты — пауза для каждого
        # сайта своя: медленный или сбойный чужой сайт не должен тормозить обход проверяемого.
        self.res_limiter = RateLimiter(res_delay(cfg.delay), speed_up=False)
        self._ext_limiters = {}
        self.robots = {}
        self.exclude = [re.compile(x) for x in cfg.exclude]
        self.stop_flag = False
        start = U.normalize(cfg.start_url)
        if not start:
            raise ValueError("Некорректный адрес: " + cfg.start_url)
        self.start = start
        self.root_host = U.host_of(start)
        # часть сайта: только раздел (адреса с этого начала) или только адреса из списка
        self.scope_prefix = scope_key(U.normalize(cfg.section) or cfg.section) if cfg.section else ""
        self.list_urls = read_url_list(cfg.url_list) if cfg.url_list else None
        self.list_keys = {scope_key(u) for u in self.list_urls} if self.list_urls is not None else None
        self.renderer = None
        # закрытый тестовый сайт: логин/пароль или cookie из окна программы — только этому сайту
        from .. import site_auth
        self.auth = site_auth.login_headers(start, self.log)
        if self.auth:
            self.fetcher.host_headers.update(self.auth)
            self.insecure.host_headers.update(self.auth)
            self.log("Вход на сайт: логин и пароль (или cookie) из окна программы - передаются только этому сайту.")

    def limiter_for(self, url, internal, kind):
        """Очередь пауз для адреса: страницы сайта, свои файлы или чужой сайт."""
        if internal:
            if kind == "resource" and getattr(self, "pages_idle", False):
                # страницы кончились (или лимит страниц): их очередь пауз свободна - картинки идут через обе, сайт
                # получает не больше запросов, чем во время обхода страниц, а хвост из картинок проходит вдвое
                # быстрее (lancentre.ru 28.10.2026: 3,3 тыс. картинок после страниц - 14 мин по ~5 в секунду)
                return min((self.res_limiter, self.limiter), key=lambda x: x.next_at)
            return self.res_limiter if kind == "resource" else self.limiter
        host = U.host_of(url)
        lim = self._ext_limiters.get(host)
        if lim is None:
            # та же пауза, что у сайта: с одного CDN фото проверяются не медленнее, чем раньше в общей очереди
            lim = self._ext_limiters.setdefault(host, RateLimiter(self.cfg.delay))
        return lim

    # ---------- часть сайта: «Только этот раздел» и «Мой список адресов»
    @property
    def partial(self):
        return bool(self.scope_prefix) or self.list_keys is not None

    def in_scope(self, url):
        """Входит ли страница в проверку. Без раздела и списка — всё."""
        if self.list_keys is not None:
            return scope_key(url) in self.list_keys
        if self.scope_prefix:
            return scope_key(url).startswith(self.scope_prefix)
        return True

    def scope_meta(self):
        """Что проверяли: для отчёта, сравнения с прошлой проверкой и окна программы. None — весь сайт."""
        if self.list_keys is not None:
            return {"mode": "list", "count": len(self.list_urls)}
        if self.scope_prefix:
            return {"mode": "section", "prefix": self.scope_prefix}
        return None

    # ---------- общие паузы и «Стоп» для всех дополнительных проходов после обхода
    def stopped(self):
        """Нажата ли «Остановить» (файл-флаг из окна программы) или Ctrl+C."""
        if not self.stop_flag and self.cfg.stop_file and os.path.exists(self.cfg.stop_file):
            self.stop_flag = True
            self.log("\nПолучена команда «Стоп». Заканчиваю, всё проверенное сохранено.")
        return self.stop_flag

    def pace(self, minimum=0.3):
        """Пауза между запросами (не меньше minimum секунд). Возвращает False, если пора остановиться:
        «Стоп» прерывает и саму паузу."""
        end = time.monotonic() + max(self.cfg.delay, minimum)
        while time.monotonic() < end:
            if self.stopped():
                return False
            time.sleep(min(0.25, max(0.0, end - time.monotonic())))
        return not self.stopped()

    # ---------- журнал сбоев программы: ошибка не должна пропадать молча
    def log_failure(self, url, exc):
        """exc - исключение или готовый текст (ошибки разбора HTML, crawler/page.handle)."""
        import traceback
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(self.store_path)), "сбои.txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {url}\n")
                if isinstance(exc, BaseException):
                    f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-3:]) + "\n")
                else:
                    f.write(str(exc) + "\n\n")
        except OSError as e:
            # обход из-за журнала не останавливаем, но одной строкой скажем, что журнал не пишется
            if not getattr(self, "_fail_log_said", False):
                self._fail_log_said = True
                self.log(f"   Не получается записать сбои.txt ({e.strerror or e}) - сбои видны только в отчёте.")

    # ---------- состояние для окна программы (status.json) и журнал
    def st(self, **kw):
        """Записать состояние проверки в файл: окно программы читает его, а не разбирает текст журнала."""
        if not self.cfg.status_file:
            return
        if "step" in kw and "unit" not in kw and kw["step"] != self._st.get("step"):
            kw["unit"] = ""  # новый шаг: старая полоса прогресса (страницы, sitemap) к нему уже не относится
            try:
                kw.setdefault("pages", self.store.count("state='done' AND kind='page' AND internal=1"))
                kw.setdefault("limit", self.cfg.max_pages)
            except Exception:
                pass
        self._st.update(kw)
        self._st["updated"] = time.time()
        from .. import memory
        if memory.LAST:
            self._st["res"] = dict(memory.LAST)   # память и процессор проверки - для окна
        write_status(self.cfg.status_file, self._st)

    def log(self, msg=""):
        self._print(msg)
        m = re.search(r"Шаг (\d) из 4\. ([^\n]+)", msg)
        if m:
            self.st(step=f"Шаг {m.group(1)} из 4: {m.group(2).strip()}")
