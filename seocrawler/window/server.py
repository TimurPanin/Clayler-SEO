"""Веб-сервер окна программы (только 127.0.0.1) и открытие окна Chrome/Edge."""
import json
import mimetypes
import os
import re
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import REPORTS, PAGE_DIR
from .job import BUSY, BUSY_START, JOB
from . import reports_list as RL

PAGE_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
              ".js": "application/javascript; charset=utf-8", ".woff2": "font/woff2",
              ".ico": "image/x-icon", ".png": "image/png"}


def _folder(name):
    """Папка проверки внутри «reports» по имени из окна (только имя, без путей наружу)."""
    return os.path.join(REPORTS, os.path.basename(name or ""))


def _has_crawl(folder):
    return os.path.exists(os.path.join(folder, "crawl.db"))


_TITLES = {}


def _check_titles():
    """{ключ проблемы: название} из списка проверок программы. Список собирается разбором кода всех проверок, а
    метки окно перечитывает при каждом возврате в окно - считаем один раз за запуск."""
    if not _TITLES:
        from .settings_ui import catalog
        _TITLES.update({c["key"]: c["title"] for c in catalog()})
    return _TITLES


HOST_RE = re.compile(r"[a-z0-9а-яё.-]+\.[a-zа-яё]{2,}")


def _host(data, www=True):
    """Имя сайта из запроса окна ({"host": ...}) или "", если на имя сайта не похоже. www=True - без «www.»."""
    host = str(data.get("host") or "").strip().lower()
    if www:
        host = host.removeprefix("www.")
    return host if HOST_RE.fullmatch(host) else ""


def _site_of(data):
    """Сайт действия для «Журнала»: из папки проверки, адреса или домена в запросе окна."""
    if not isinstance(data, dict):
        return ""
    for k in ("folder", "f", "host", "site", "url"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            v = re.sub(r"^https?://", "", v.strip()).split("/")[0]
            return (v.split("_")[0] if k in ("folder", "f") else v).removeprefix("www.")[:80]
    for k in ("folders", "sites"):
        v = data.get(k)
        if isinstance(v, list) and v and isinstance(v[0], str):
            return _site_of({k[:-1]: v[0]})
    return ""


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """Окно закрыли или обновили, пока ответ ещё шёл (WinError 10053, 10054, обрыв канала) — это не ошибка
        программы, в чёрное окно не печатаем. Остальные ошибки — как раньше, с трассировкой."""
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        try:   # сбой в самом окне: плашка простыми словами, трассировка - в «Журнал» (Подробнее)
            import traceback
            from . import events
            tb = traceback.format_exc()
            last = tb.strip().splitlines()[-1] if tb.strip() else ""
            events.error(last + "\n" + tb[-1500:], where="Ошибка в окне программы")
        except Exception:
            pass
        super().handle_error(request, client_address)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if code >= 400 and code != 404:   # отказ или ошибка на действие - в «Журнал» (сайт - из запроса)
            try:
                from .. import applog
                msg = body.get("error") if isinstance(body, dict) else body if isinstance(body, str) else ""
                applog.write("error", f"{msg} ({urlsplit(self.path).path})", getattr(self, "_site", ""))
            except Exception:
                pass
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_page(self, name):
        """Файл самой страницы окна (index.html, style.css, app.js) из папки page."""
        full = os.path.join(PAGE_DIR, os.path.basename(name))
        ext = os.path.splitext(full)[1]
        if ext not in PAGE_TYPES or not os.path.isfile(full):
            return self.send(404, "Нет такого файла", "text/plain; charset=utf-8")
        with open(full, "rb") as f:
            return self.send(200, f.read(), PAGE_TYPES[ext])

    def answer(self, err):
        """Ответ на действие: текст ошибки — 400, пусто — {"ok": true}."""
        return self.send(400 if err else 200, {"error": err} if err else {"ok": True})

    def busy(self):
        """Идёт проверка — ответить 409 и вернуть True (новую задачу не запускать)."""
        if JOB.running:
            self.send(409, {"error": BUSY})
            return True
        return False

    def started(self, ok, extra=None):
        """Ответ на запуск: JOB.start вернул False - другая проверка успела начаться между busy() и запуском
        (очередь, наблюдение, Telegram), ничего не запущено - 409, а не «запущено»."""
        if not ok:
            return self.send(409, {"error": BUSY})
        return self.send(200, {"ok": True, **(extra or {})})

    def query(self):
        """Параметры из адреса (?f=...&live=1) — по первому значению."""
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def ready_folder(self, data):
        """Папка готовой проверки (и в архиве), с которой сейчас никто не работает. Иначе — ответ с ошибкой и None."""
        name = data.get("folder")
        folder = RL._safe(REPORTS, name) or RL._safe(RL.ARCHIVE, name)
        if not folder:
            self.send(400, {"error": "Нет такой проверки."})
            return None
        if os.path.basename(folder) in JOB.busy_folders():
            self.send(409, {"error": "С этой проверкой программа сейчас работает. Дождитесь окончания."})
            return None
        return folder

    def make_file(self, data, write, fail):
        """«PDF для витрины», «Видео обхода»: собрать файл из готовой проверки и открыть его."""
        folder = self.ready_folder(data)
        if not folder:
            return
        try:
            dst, err = write(folder)
        except Exception as e:
            dst, err = "", str(e)[:150]
        if err:
            return self.send(400, {"error": fail + err})
        try:
            os.startfile(dst)
        except Exception:
            pass
        return self.send(200, {"ok": True})

    # Адрес → метод. Сначала точный адрес, потом начало адреса (по порядку). Нет ни того, ни другого — 404.
    GET = {"/": "g_index", "/favicon.ico": "g_favicon", "/semantics": "g_semantics_page", "/dictionary": "g_dictionary_page",
           "/api/semantics": "g_semantics", "/api/semantics_stop": "g_semantics_stop",
           "/api/semantics_masks": "g_semantics_masks", "/api/semantics_files": "g_semantics_files",
           "/api/semantics_tz": "g_semantics_tz", "/api/sembx": "g_sembx", "/api/semdemand": "g_semdemand",
           "/api/semupd": "g_semupd", "/api/version": "g_version", "/api/status": "g_status", "/api/events": "g_events",
           "/api/log": "g_log", "/api/web": "g_web", "/api/web_node": "g_web_node", "/api/brand": "g_brand",
           "/api/site_auth": "g_site_auth", "/api/lists": "g_lists", "/api/settings": "g_settings", "/api/extract": "g_extract",
           "/api/catalog": "g_catalog", "/api/direct": "g_direct", "/api/accounts": "g_accounts",
           "/oauth/yandex": "g_oauth", "/oauth/google": "g_oauth", "/api/telegram": "g_telegram",
           "/api/queue": "g_queue", "/api/watch": "g_watch", "/api/reports": "g_reports", "/api/labels": "g_labels",
           "/api/show": "g_show", "/api/clayler": "g_clayler"}
    GET_PREFIX = (("/page/", "g_page"), ("/api/dict", "g_dict"), ("/api/semdec", "g_semdec"),
                  ("/api/semsort", "g_semsort"), ("/r/", "g_file"))
    POST = {"/api/events": "p_events", "/api/log": "p_log", "/api/log_open": "p_log_open", "/api/start": "p_start",
            "/api/compare_sites": "p_compare_sites", "/api/semantics_stop": "p_semantics_stop",
            "/api/semantics_ok": "p_semantics_ok", "/api/semantics_masks": "p_semantics_masks",
            "/api/semantics_masks_propose": "p_semantics_masks_propose", "/api/semantics_files": "p_semantics_files",
            "/api/semantics": "p_semantics", "/api/semantics_new": "p_semantics_new",
            "/api/archive": "p_folder_action", "/api/unarchive": "p_folder_action", "/api/delete": "p_folder_action",
            "/api/open_folder": "p_folder_action", "/api/rebuild": "p_rebuild", "/api/demo_pdf": "p_demo_pdf",
            "/api/crawl_video": "p_crawl_video", "/api/catalog": "p_catalog", "/api/settings": "p_settings",
            "/api/list": "p_list", "/api/brand": "p_brand", "/api/search": "p_search", "/api/extract": "p_extract",
            "/api/extract_test": "p_extract_test", "/api/robot_view": "p_robot_view",
            "/api/fav": "p_fav", "/api/direct_many": "p_direct_many", "/api/dict": "p_dict", "/api/sembx": "p_sembx",
            "/api/semdemand": "p_semdemand", "/api/semupd": "p_semupd", "/api/stop": "p_stop",
            "/api/labels": "p_labels", "/api/site_tag": "p_site_tag", "/api/monthly": "p_monthly"}
    POST_PREFIX = (("/api/reindex/", "p_reindex"), ("/api/site_auth/", "p_site_auth"), ("/api/direct/", "p_direct"),
                   ("/api/accounts/", "p_accounts"), ("/api/telegram/", "p_telegram"), ("/api/queue/", "p_queue"),
                   ("/api/watch/", "p_watch"), ("/api/semdec/", "p_semdec"), ("/api/semsort", "p_semsort"))

    @staticmethod
    def route(path, exact, prefix):
        return exact.get(path) or next((name for p, name in prefix if path.startswith(p)), None)

    def _show_host(self):
        """Запрос пришёл на show.localhost - адрес копий чужих страниц (highlight.py): там только /api/show."""
        return (self.headers.get("Host") or "").split(":")[0].lower() == "show.localhost"

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if self._show_host() and path != "/api/show":   # 404, а не 403: значок вкладки и обновление - не ошибки окна
            return self.send(404, "<!doctype html><meta charset='utf-8'><body style='font:15px Arial;padding:24px'>"
                             "Это была копия страницы с подсветкой: обновить её нельзя. Откройте её заново из отчёта.",
                             "text/html; charset=utf-8")
        name = self.route(path, self.GET, self.GET_PREFIX)
        if not name:
            return self.send(404, "Нет такой страницы", "text/plain; charset=utf-8")
        return getattr(self, name)(path)

    def do_POST(self):
        path = urlsplit(self.path).path
        # действия - только со страниц самого окна (и без Origin - из программы и автотестов): копия чужой страницы
        # на show.localhost и любые сайты в браузере не могут ничего удалить или поменять
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        if self._show_host() or (origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")):
            return self.send(403, {"error": "нет такого действия"})
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n) or b"{}")
        self._site = _site_of(data)
        name = self.route(path, self.POST, self.POST_PREFIX)
        if not name:
            return self.send(404, {"error": "нет такого действия"})
        return getattr(self, name)(path, data)

    # ---------- GET: страницы окна и данные для них ----------

    def g_index(self, path):
        return self.send_page("index.html")

    def g_favicon(self, path):   # своя иконка окна и панели задач (рисунок: tests/нарисовать_иконку.py)
        return self.send_page("icon.ico")

    def g_page(self, path):
        return self.send_page(path[6:])

    def g_semantics_page(self, path):
        return self.send_page("semantics.html")

    def g_dictionary_page(self, path):   # «Словарь»: синонимы, бренды, омонимы… по темам (window/dictview.py)
        return self.send_page("dictionary.html")

    def g_dict(self, path):
        from . import dictview
        return dictview.get(self, path)

    def g_semantics(self, path):  # с решениями человека: разделённые группы, решения по страницам
        from .semdec import load_semantics
        from ..semantics.labels import for_js
        data = load_semantics(self.query().get("f"))[1]
        if data:
            data["labels"] = for_js()   # одни слова для видов групп в окне, отчётах, Excel и Telegram
            from ..semantics import masks
            data["ok_words"] = masks.load(data.get("host") or "").get("ok") or []   # «Это про нас» в «Отсеяно»
            from ..semantics import bukvarix, imports
            try:   # видимость в Яндексе по группам (Букварикс) - колонка «В Яндексе» в «Запрос → страница»
                data["yandex"] = bukvarix.visibility(data, data["host"])
            except Exception as e:   # дополнение: сбой не мешает открыть семантику
                print("Видимость для «Запрос → страница» не посчиталась:", str(e)[:200])
                data["yandex"] = None
            # файлы с частотностью и выгрузки показов: подпись «откуда цифры и от какого числа»
            data["src_files"] = [f for f in imports.listing(data["host"]) if f["kind"] in ("freq", "stats")]
        return self.send(200, data) if data else self.send(404, {"error": "Семантика для этой проверки ещё не собрана."})

    def g_semantics_stop(self, path):
        from ..semantics.words import load_stop
        return self.send(200, {"words": load_stop()})

    def g_semantics_masks(self, path):  # маски и стоп-слова клиента (semantics/masks.py)
        from ..semantics import masks, export
        q = self.query()
        sem = export.load(_folder(q["s"])) if q.get("s") else None
        return self.send(200, masks.view(q.get("host") or "", q.get("f") or "", sem))

    def g_semantics_files(self, path):  # запросы из файлов (Вордстат, Key Collector, выгрузки Вебмастера и SC)
        from ..semantics import imports
        return self.send(200, {"files": imports.listing(self.query().get("host") or "")})

    def g_semantics_tz(self, path):  # ТЗ копирайтеру пачкой: собрать заново из семантика.json и отдать файл
        from urllib.parse import quote
        from ..semantics import brief_docx
        from .semdec import load_semantics
        full, data = load_semantics(self.query().get("f"))
        if not data:
            return self.send(404, "Семантика для этой проверки ещё не собрана.", "text/plain; charset=utf-8")
        try:
            tz = brief_docx.write(full, data)
        except OSError:
            return self.send(409, "Не получилось записать файл: наверное, он открыт в Word. Закройте его и нажмите ещё раз.",
                             "text/plain; charset=utf-8")
        if not tz:
            return self.send(200, "Заданий нет: новых страниц и страниц с замечаниями в семантике нет.",
                             "text/plain; charset=utf-8")
        self.send_response(302)
        self.send_header("Location", f"/r/{quote(os.path.basename(full))}/{quote(brief_docx.FILE)}")
        self.end_headers()

    def g_semdec(self, path):  # решения по семантике (window/semdec.py)
        from . import semdec
        return semdec.get(self, path)

    def g_semsort(self, path):  # разложить новые запросы по группам, словари (window/semsort.py)
        from . import semsort
        return semsort.get(self, path)

    def g_sembx(self, path):  # вкладка «Видимость»: запросы сайта и конкурентов из Букварикса (window/sembx.py)
        from . import sembx
        return sembx.get(self)

    def g_semdemand(self, path):  # вкладка «Спрос»: Вордстат через Директ (window/semdemand.py)
        from . import semdemand
        return semdemand.get(self)

    def g_semupd(self, path):  # вкладка «Обновления»: обновления поиска на графиках, «Что просело» (window/semupd.py)
        from . import semupd
        return semupd.get(self)

    def g_clayler(self, path):   # «это окно Clayler SEO?» - для отчёта, открытого файлом (подсветка через окно)
        body = b'{"app": "clayler"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")   # только этот ответ: в нём ничего, кроме имени программы
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def g_version(self, path):  # версии программы и «Семантики» - в меню слева
        from .. import VERSION
        from ..semantics import VERSION as SEM_VERSION
        return self.send(200, {"app": VERSION, "semantics": SEM_VERSION})

    def g_status(self, path):
        return self.send(200, JOB.status())

    def g_events(self, path):   # уведомления: новые после ?after=, колокольчик, звук (window/events.py)
        from . import events
        try:
            after = int(self.query().get("after") or 0)
        except ValueError:
            after = 0
        return self.send(200, events.since(after))

    def g_log(self, path):   # вкладка «Журнал» (applog.py): ?kind=action|event|error&q=поиск
        from .. import applog
        from ..plain_errors import explain
        q = self.query()
        items = applog.read(1000, q.get("kind") or "", q.get("q") or "")
        for it in items:   # у ошибки - что сделать, простыми словами
            if it["kind"] == "error":
                it["todo"] = explain(it["detail"] or it["text"])["todo"]
        return self.send(200, {"items": items, "file": applog.path()})

    def g_web(self, path):  # для живой паутины (page/web_live.js): ход проверки и сколько ошибок
        s = JOB.status()
        bad = warn = None
        sf = getattr(JOB, "status_file", "")
        q = parse_qs(urlsplit(self.path).query or "")
        subs = getattr(JOB, "subs", None) or []
        folder = (subs[0].out_dir if subs else JOB.out_dir) or ""  # для наведения на узел паутины
        if q.get("run"):  # одновременная проверка: паутина одного сайта (ваш или конкурент)
            try:
                r = JOB.run_status(int(q["run"][0]))
            except ValueError:
                r = None
            if not r:
                return self.send(200, {"running": False})
            s = dict(r, running=r["state"] == "run", stopped=r["state"] == "stopped")
            sf = r.get("status_file") or ""
            folder = subs[r["n"] - 1].out_dir or ""
        if s["running"] and sf and os.path.exists(sf):
            try:
                with open(sf, encoding="utf-8") as f:
                    st = json.load(f)
                bad, warn = st.get("web_bad"), st.get("web_warn")
            except (OSError, ValueError):
                pass
        return self.send(200, {k: s.get(k) for k in ("running", "stopped", "overall", "progress", "unit", "stuck", "step", "site")}
                         | {"bad": bad, "warn": warn, "folder": os.path.basename(folder)})

    def g_web_node(self, path):  # узел живой паутины: адрес страницы и её главная проблема (window/web_node.py)
        from . import web_node
        q = parse_qs(urlsplit(self.path).query or "")
        try:
            n = int((q.get("n") or ["0"])[0])
        except ValueError:
            n = 0
        kind = (q.get("kind") or ["page"])[0]
        return self.send(200, web_node.lookup((q.get("folder") or [""])[0], kind if kind in ("page", "err", "warn") else "page",
                                              n, JOB.busy_folders()))

    def g_brand(self, path):
        from .. import brand
        return self.send(200, brand.status())

    def g_site_auth(self, path):
        from .. import site_auth
        return self.send(200, {"sites": site_auth.sites()})

    def g_lists(self, path):
        return self.send(200, {"items": list_results()})

    def g_settings(self, path):
        from .settings_ui import current
        return self.send(200, current())

    def g_extract(self, path):   # «Свои данные со страниц»: правила извлечения (seocrawler/extract.py)
        from .. import extract
        return self.send(200, {"rules": extract.load_all(), "max": extract.MAX_RULES})

    def g_catalog(self, path):   # общая таблица «Бренды и прочие» и запись в Google Таблицу (catalog.py)
        from .. import catalog
        _p, xlsx = catalog._paths()
        g = catalog.google()
        return self.send(200, {"xlsx": xlsx, "exists": bool(xlsx and os.path.isfile(xlsx)), "script": catalog.script(),
                               "google": {k: g.get(k, "") for k in ("url", "sheet", "at", "error")}})

    def g_direct(self, path):   # Яндекс Директ: ключ и загрузка точной частотности (direct.py)
        from .. import direct
        from ..semantics import export
        f = os.path.basename(self.query().get("f") or "")
        data = export.load(os.path.join(REPORTS, f)) if f else None
        return self.send(200, dict(direct.status(), job=direct.job(f),
                                   progress=direct.progress(data) if data and data.get("groups") else None))

    def g_accounts(self, path):
        from .. import accounts
        return self.send(200, accounts.status(self.server.server_port))

    def g_oauth(self, path):  # сюда Яндекс/Google возвращают человека после «Разрешить»
        from .. import accounts
        err = accounts.finish(path[7:], self.query())
        return self.send(200, _oauth_page(err), "text/html; charset=utf-8")

    def g_telegram(self, path):
        from .. import telegram
        return self.send(200, telegram.status(live="live=1" in (urlsplit(self.path).query or "")))

    def g_queue(self, path):  # «Очередь сайтов» (site_queue.py)
        from .. import site_queue
        return self.send(200, site_queue.status(JOB))

    def g_watch(self, path):
        return self.send(200, watch_status())

    def g_reports(self, path):
        return self.send(200, RL.list_reports(busy=JOB.busy_folders()))

    def g_file(self, path):  # файлы отчётов
        full = os.path.realpath(os.path.join(REPORTS, path[3:]))
        if not full.startswith(os.path.realpath(REPORTS) + os.sep) or not os.path.isfile(full):
            return self.send(404, "Нет такого файла", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        elif full.endswith(".csv"):
            ctype = "text/csv; charset=utf-8"
        with open(full, "rb") as f:
            return self.send(200, f.read(), ctype)

    # ---------- POST: действия из окна ----------

    def p_events(self, path, data):   # колокольчик: {"seen": id} прочитано, {"sound": bool}, {"clear": true}
        from . import events
        return self.send(200, events.update(data.get("seen"), data.get("sound"), bool(data.get("clear"))))

    def p_log(self, path, data):   # из окна: нажатые кнопки и ошибки страницы {"items": [{kind, text, site, detail}]}
        from .. import applog
        for it in (data.get("items") or [])[:50]:
            if isinstance(it, dict) and it.get("kind") in ("action", "error", "event"):
                applog.write(it["kind"], str(it.get("text") or "")[:300], str(it.get("site") or "")[:80],
                             str(it.get("detail") or "")[:1500])
        return self.send(200, {"ok": True})

    def p_log_open(self, path, data):   # «Открыть файл журнала» - в Блокноте
        from .. import applog
        if os.path.isfile(applog.path()):
            os.startfile(applog.path())
        return self.send(200, {"ok": True})

    def p_start(self, path, data):
        err = start_check(data)
        if err:
            return self.send(409 if JOB.running else 400, {"error": err})
        return self.send(200, {"ok": True})

    def p_compare_sites(self, path, data):
        if self.busy():
            return
        folders = [f for f in map(_folder, data.get("folders", [])) if _has_crawl(f)]
        if len(folders) < 2:
            return self.send(400, {"error": "Выберите хотя бы одного конкурента."})
        return self.started(JOB.start([], [], compare_folders=folders))

    def p_semantics_stop(self, path, data):   # стоп-слова семантики: добавить / убрать
        from ..semantics.words import load_stop, save_stop
        cur = set(load_stop()) | {str(w).lower() for w in data.get("add") or []}
        cur -= {str(w).lower() for w in data.get("remove") or []}
        return self.send(200, {"words": save_stop(cur)})

    def p_semantics_ok(self, path, data):   # «Это про нас» в «Отсеяно»: слово, которого нет на сайте, но оно по теме
        from ..semantics import masks
        host = _host(data)
        if not host:
            return self.send(400, {"error": "Не понятно, для какого сайта."})
        return self.send(200, {"ok": masks.set_ok(host, data.get("add") or [], data.get("remove") or [])})

    def p_semantics_masks(self, path, data):   # правки масок, стоп-слова клиента, подтверждение
        from ..semantics import masks
        host = _host(data)
        if not host:
            return self.send(400, {"error": "Не понятно, для какого сайта маски."})
        m = data.get("masks")
        masks.update(host, masks=m if isinstance(m, list) else None,
                     stop=data["stop"] if isinstance(data.get("stop"), list) else None,
                     confirmed=data["confirmed"] if isinstance(data.get("confirmed"), bool) else None)
        return self.send(200, masks.view(host, data.get("f") or ""))

    def p_semantics_masks_propose(self, path, data):   # предложить маски по проверке - отдельной программой
        if self.busy():
            return
        folder = _folder(data.get("folder"))
        if not _has_crawl(folder):
            return self.send(400, {"error": "Нет такой проверки."})
        return self.started(JOB.start([], [], label="семантика: маски " + os.path.basename(folder), masks_folder=folder))

    def p_semantics_files(self, path, data):
        import base64
        from ..semantics import imports
        host = _host(data, www=False)
        if not host:
            return self.send(400, {"error": "Не понятно, для какого сайта файл."})
        if data.get("remove"):
            imports.remove_file(host, str(data["remove"]))
            return self.send(200, {"files": imports.listing(host)})
        name = os.path.basename(str(data.get("name") or "запросы.txt"))
        try:
            raw = base64.b64decode(data.get("data") or "")
            from ..semantics import bukvarix
            if bukvarix.detect(raw):   # «Анализ домена» Букварикса - не статистика сайта, а вкладка «Видимость»
                return self.send(200, {"added": bukvarix.add_file(host, name, raw), "files": imports.listing(host)})
            info = imports.add_file(host, name, raw)
        except Exception as e:
            return self.send(400, {"error": f"Не получилось прочитать «{name}»: {str(e)[:150]}. Подойдут Excel (xlsx), "
                                            "CSV или текстовый файл: запрос в первой колонке, число - во второй."})
        return self.send(200, {"added": info, "files": imports.listing(host)})

    def p_semantics(self, path, data):
        if self.busy():
            return
        folders = [f for f in map(_folder, data.get("folders", [])) if _has_crawl(f)]
        hosts = []  # конкуренты по адресу (без проверки): только имя сайта
        for h in data.get("hosts") or []:
            h = re.sub(r"^https?://", "", str(h).strip().lower()).split("/")[0].removeprefix("www.")
            if HOST_RE.fullmatch(h) and h not in hosts:
                hosts.append(h)
        if not folders:
            return self.send(400, {"error": "Нет такой проверки."})
        return self.started(JOB.start([], [], semantics_folders=folders[:6], label="семантика " + os.path.basename(folders[0]),
                                      deep=bool(data.get("deep")), semantics_hosts=hosts[:5]))

    def p_semantics_new(self, path, data):   # семантика нового сайта (semantics/newsite.py): проект, конкуренты, сбор
        if self.busy():
            return
        from ..semantics import newsite
        words = newsite.split_words(data.get("words"))
        if not words:
            return self.send(400, {"error": "Напишите хотя бы одно слово темы: чем будет заниматься сайт."})
        folders = [f for f in map(_folder, data.get("folders") or []) if _has_crawl(f) and not newsite.info(f)]
        hosts = []   # конкуренты по адресу: перед сбором программа их быстро проверит
        for h in data.get("hosts") or []:
            h = newsite.clean_domain(h)
            if h and h not in hosts:
                hosts.append(h)
        if len(folders) + len(hosts) > 5:
            return self.send(400, {"error": "Не больше 5 конкурентов за раз."})
        city = str(data.get("city") or "").strip()
        if city:
            from ..semantics.words import city_by_name
            c = city_by_name(city)
            if not c:
                return self.send(400, {"error": f"Не знаю город «{city}». Напишите полное название (Уфа, Москва, "
                                                "Санкт-Петербург) или оставьте пустым - тогда по всей России."})
            city = c[0]
        proj = newsite.create(REPORTS, data.get("name"), words, city, data.get("domain"), data.get("brand"))
        ok = JOB.start([], [], semantics_folders=[proj] + folders[:5], label="семантика нового сайта",
                       deep=bool(data.get("deep")), crawl_hosts=hosts[:5])
        if not ok:   # другая проверка успела начаться: только что созданный пустой проект не оставляем
            import shutil
            shutil.rmtree(proj, ignore_errors=True)
        return self.started(ok, {"folder": os.path.basename(proj)})

    def p_folder_action(self, path, data):   # «В архив», «Из архива», «Удалить», «Открыть папку»
        folder = os.path.basename(data.get("folder") or "")
        if path != "/api/open_folder" and folder in JOB.busy_folders():
            return self.send(409, {"error": "С этой проверкой программа сейчас работает. Дождитесь окончания."})
        if path == "/api/archive":
            err = RL.archive(folder)
        elif path == "/api/unarchive":
            err = RL.unarchive(folder)
        elif path == "/api/delete":
            err = RL.delete(folder, archived=bool(data.get("archived")))
        else:
            err = RL.open_folder(folder, client=bool(data.get("client")), dev=bool(data.get("dev")))
        return self.answer(err)

    def p_rebuild(self, path, data):
        if self.busy():
            return
        folder = _folder(data.get("folder"))
        if not _has_crawl(folder):
            return self.send(400, {"error": "Нет такой проверки."})
        ok = JOB.start([], [], report_folder=folder, label=data.get("site") or os.path.basename(folder))
        if ok and data.get("again"):   # кнопка в карточке после «Остановить» - видно в «Подробном журнале»
            import time as _t
            JOB.add(_t.strftime("%H:%M:%S") + " Нажата кнопка «Обновить отчёт ещё раз»: продолжаю после остановки")
        return self.started(ok)

    def p_demo_pdf(self, path, data):  # PDF для витрины: из готовой проверки, сайт заново не обходится
        from ..demo_pdf import write
        return self.make_file(data, write, "PDF для витрины не собран: ")

    def p_crawl_video(self, path, data):  # видео обхода для Авито и Kwork: из готовой проверки, ~20 с записи
        from ..crawl_video import write
        return self.make_file(data, write, "Видео не записалось: ")

    def p_catalog(self, path, data):   # {"do": "open" | "connect" (url) | "push" | "off"}
        from .. import catalog
        do = data.get("do")
        if do == "open":
            _p, xlsx = catalog._paths()
            if not (xlsx and os.path.isfile(xlsx)):
                return self.answer("Таблицы пока нет: она появится после проверки сайта или сборки семантики.")
            try:
                os.startfile(xlsx)
            except Exception as e:
                return self.answer("Не открылась: " + str(e)[:120])
            return self.answer("")
        if do == "connect":
            return self.answer(catalog.google_connect(data.get("url")))
        if do == "push":
            return self.answer(catalog.push() if catalog.google().get("url") else "Google-таблица не подключена.")
        if do == "off":
            catalog.google_off()
            return self.answer("")
        return self.answer("Не понятно, что сделать.")

    def g_show(self, path):   # страница сайта с обведённой проблемой - из отчёт.html (highlight.py)
        from . import highlight
        if not self._show_host():   # чужие скрипты не должны жить на адресе окна: переходим на show.localhost
            self.send_response(302)
            self.send_header("Location", f"http://{highlight.HOST}:{self.server.server_address[1]}{self.path}")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        q = self.query()
        port, key = self.server.server_address[1], q.get("key", "")
        from ..problem_shots import KINDS
        if q.get("inner") != "1" and (key == "mobile_diff" or KINDS.get(key, ("",))[0] == "mobile"):
            # проблемы телефона: копия шириной с телефон, у «телефону не то, что компьютеру» - обе версии рядом
            return self.send(200, highlight.frames(q.get("url", ""), q.get("find", ""), port, key, q.get("t", ""),
                                                   key == "mobile_diff", q.get("d", "")), "text/html; charset=utf-8")
        return self.send(200, highlight.render(q.get("url", ""), q.get("find", ""), port, key, q.get("t", ""),
                                               "phone" if q.get("ua") == "phone" else "chrome", q.get("d", ""),
                                               q.get("shot") == "1"),
                         "text/html; charset=utf-8")

    def g_labels(self, path):   # метки работы у проблем сайта (labels.py): ?site=site.ru; ?all=1 - все сайты
        from .. import labels
        if not self.query().get("all"):
            return self.send(200, {"labels": labels.load(self.query().get("site", "")), "states": labels.STATES})
        # все метки с названиями проблем: из последней проверки сайта (проблемы.csv), «не ошибка» там уже нет -
        # из списка проверок программы (карточка сайта и фильтры в окне)
        import csv
        import glob
        names = _check_titles()
        items = []
        for site, got in labels.everything().items():
            titles = {}
            # папки проверки «сайт_ГГГГ-ММ-ДД_ЧЧ-ММ-СС» и «www.сайт_…», свежая первой; «сайт.ru:8080_…» и
            # «сайт.ru.old_…» - другой сайт
            # и «…_2» - две проверки в одну секунду (как reindex._FOLDER_RX)
            dated = re.compile(r"(?:www\.)?" + re.escape(site) + r"_(\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d(?:_\d+)?)$", re.I)
            found = [(m.group(1), d) for d in glob.glob(os.path.join(REPORTS, "*" + glob.escape(site) + "_*"))
                     for m in [dated.match(os.path.basename(d))] if m]
            for _when, d in sorted(found, reverse=True):
                p = os.path.join(d, "проблемы.csv")
                if os.path.exists(p):
                    with open(p, encoding="utf-8-sig", newline="") as f:
                        for r in list(csv.reader(f, delimiter=";"))[1:]:
                            if len(r) > 6 and r[6].endswith(".csv"):
                                titles[os.path.splitext(os.path.basename(r[6]))[0]] = r[2]
                    break
            for k, v in got.items():
                items.append({"site": site, "key": k, "state": v["state"], "label": labels.STATES[v["state"]],
                              "at": v.get("at", ""), "title": titles.get(k) or names.get(k) or k})
        items.sort(key=lambda x: (x["site"], x["state"], x["title"]))
        return self.send(200, {"items": items, "states": labels.STATES})

    def p_labels(self, path, data):   # {site, key, state: not_error | sent | wait | ""} - из отчёт.html
        from .. import labels
        return self.answer(labels.put(str(data.get("site") or ""), str(data.get("key") or ""), str(data.get("state") or "")))

    def p_settings(self, path, data):
        from .settings_ui import save
        return self.answer(save(data))

    def p_list(self, path, data):  # проверка списка адресов или переезда
        if self.busy():
            return
        import time as _t
        lists = os.path.join(REPORTS, "списки")
        os.makedirs(lists, exist_ok=True)
        if data.get("folder"):
            folder = _folder(data["folder"])
            if not _has_crawl(folder):
                return self.send(400, {"error": "Нет такой проверки."})
            args = ["--old", folder] + (["--new-host", data["new_host"].strip()] if data.get("new_host") else [])
            label = "переезд " + os.path.basename(folder)
        else:
            from ..urllist import read_list
            urls = read_list(data.get("urls") or "")
            if not urls:
                return self.send(400, {"error": "Не нашёл адресов: нужны полные адреса, начинающиеся с https://"})
            src = os.path.join(lists, f".вход-{int(_t.time())}.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("\n".join(urls))
            args, label = ["--list", src], f"список из {len(urls)} адресов"
        return self.started(JOB.start([], [], list_args=args, label=label))

    def p_reindex(self, path, data):  # сообщить Яндексу об изменённых страницах
        from .. import reindex
        folder = _folder(data.get("folder"))
        if not _has_crawl(folder):
            return self.send(400, {"error": "Выберите сайт."})
        act = path[13:]
        try:
            start = reindex._pages(folder)[0]
            if act == "key":
                return self.send(200, reindex.key_status(start))
            if act == "changed":
                urls, prev = reindex.changed(folder)
                if urls is None:
                    return self.send(400, {"error": "Не с чем сравнить: у этого сайта одна проверка. Вставьте адреса руками."})
                return self.send(200, {"urls": urls, "prev": prev})
            if act == "send":
                urls = [u for u in (data.get("urls") or []) if str(u).startswith(("http://", "https://"))]
                msg = (reindex.send_indexnow(start, urls) if data.get("way") == "indexnow"
                       else reindex.send_webmaster(start, urls))
                return self.send(200, {"message": msg})
        except Exception as e:
            return self.send(400, {"error": str(e)[:300]})
        return self.send(404, {"error": "нет такого действия"})

    def p_site_auth(self, path, data):  # логин и пароль закрытого сайта
        from .. import site_auth
        act = path[15:]
        if act == "save":
            err = site_auth.save(data.get("site") or "", data.get("user") or "", data.get("password") or "",
                                 data.get("cookie") or "")
        elif act == "remove":
            err = site_auth.remove(data.get("site") or "")
        else:
            err = "нет такого действия"
        return self.answer(err)

    def p_brand(self, path, data):  # ваши данные и логотип в аудите
        from .. import brand
        n = len(data.get("logo") or "")
        return self.answer(brand.save(data) if n < 1_000_000 else "Логотип слишком большой.")

    def p_search(self, path, data):  # поиск своего текста по готовой проверке
        from ..search import search
        folder = _folder(data.get("folder"))
        try:
            return self.send(200, search(folder, data.get("query") or "", data.get("mode") or "has",
                                         data.get("where") or "text", bool(data.get("regex"))))
        except ValueError as e:
            return self.send(400, {"error": str(e)})

    def p_extract(self, path, data):   # сохранить правила «Свои данные со страниц»
        from .. import extract
        rules, err = extract.save_all(data.get("rules") or [])
        return self.send(400, {"error": err}) if err else self.send(200, {"rules": rules})

    def p_extract_test(self, path, data):   # проверить правила (ещё не сохранённые) на одной странице
        from .. import extract
        url = (data.get("url") or "").strip()
        if not url:
            return self.send(400, {"error": "Укажите адрес страницы."})
        if "://" not in url:
            url = "https://" + url
        rules = []
        for r in (data.get("rules") or [])[:extract.MAX_RULES]:
            ok, err = extract.check_rule(r if isinstance(r, dict) else {})
            if not ok:
                return self.send(400, {"error": err})
            rules.append(ok)
        if not rules:
            return self.send(400, {"error": "Добавьте хотя бы одно правило."})
        try:
            return self.send(200, extract.test_url(url, rules))
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:
            return self.send(500, {"error": "Не получилось открыть страницу: " + str(e)[:200]})

    def p_robot_view(self, path, data):
        from .robot_view import view
        url = (data.get("url") or "").strip()
        if not url:
            return self.send(400, {"error": "Укажите адрес страницы."})
        try:
            return self.send(200, view(url, data.get("ua") or "crawler"))
        except Exception as e:
            return self.send(500, {"error": "Не получилось открыть страницу: " + str(e)[:200]})

    def p_direct(self, path, data):
        from .. import direct
        act = path[12:]
        if act == "save":
            err = direct.save(data.get("client_id"), data.get("token"), data.get("login"))
        elif act == "key":   # страница Яндекса, где показывают ключ
            if not direct.status()["auth_url"]:
                return self.answer("Сначала вставьте ClientID и нажмите «Сохранить».")
            webbrowser.open(direct.auth_url())
            return self.send(200, {"ok": True, "url": direct.auth_url()})
        elif act == "check":
            text, err = direct.check()
            if not err:
                return self.send(200, {"ok": True, "text": text})
        elif act == "forget":
            err = direct.forget()
        elif act == "start":
            err = direct.start(os.path.basename(str(data.get("f") or "")))
        elif act == "stop":
            err = direct.stop()
        else:
            err = "нет такого действия"
        return self.answer(err)

    def p_accounts(self, path, data):
        from .. import accounts
        prov, act = data.get("provider") or "", path[14:]
        if act == "app":
            err = accounts.save_app(prov, data.get("client_id"), data.get("secret"))
        elif act == "login":
            url, err = accounts.start(prov, self.server.server_port)
            if url:
                webbrowser.open(url)  # обычный браузер: там человек уже вошёл в свой Яндекс/Google
                return self.send(200, {"ok": True, "url": url})
        elif act == "logout":
            err = accounts.disconnect(prov)
        elif act == "refresh":
            err = accounts.refresh_sites(prov)
        else:
            err = "нет такого действия"
        return self.answer(err)

    def p_telegram(self, path, data):
        from .. import telegram
        act = path[14:]
        if act == "token":
            err = telegram.save_token(data.get("token"))
        elif act == "chat":
            err = telegram.find_chat()
        elif act == "test":
            err = telegram.test()
        elif act == "option":
            err = telegram.set_option(data.get("name"), data.get("on"))
        elif act == "off":
            err = telegram.disconnect()
        else:
            err = "нет такого действия"
        return self.answer(err)

    def p_monthly(self, path, data):   # «Отчёт за месяц» с экрана «Клиенты» (monthly.py): {key} → {url}
        if self.busy():
            return
        from .. import monthly
        rel, err = monthly.build(str(data.get("key") or ""))
        if err:
            return self.answer(err)
        return self.send(200, {"ok": True, "url": "/r/" + "/".join(quote(x) for x in rel.split("/"))})

    def p_site_tag(self, path, data):   # метка сайта: {key, tag: client | rival | test | ""} (экран «Клиенты»)
        return self.answer(RL.set_site_tag(data.get("key"), str(data.get("tag") or "")))

    def p_fav(self, path, data):   # звёздочка «Избранное» у сайта в «Отчётах»
        return self.answer(RL.set_favorite(data.get("key"), bool(data.get("on"))))

    def p_direct_many(self, path, data):   # «Загрузить частотность» для выбранных сайтов: по очереди, в лимит Директа
        from .. import direct
        folders = []
        for f in data.get("folders") or []:
            f = os.path.basename(str(f))
            if os.path.exists(os.path.join(_folder(f), "семантика.json")):
                folders.append(f)
        if not folders:
            return self.answer("У выбранных сайтов семантика ещё не собрана.")
        err = direct.start_many(folders)
        return self.answer(err) if err else self.send(200, {"ok": True, "added": len(folders)})

    def p_queue(self, path, data):  # «Очередь сайтов»: добавить, запустить, пауза, стоп, убрать
        from .. import site_queue
        act = path[11:]
        if act == "add":
            n, err = site_queue.add(data.get("text"), data.get("pages"))
        elif act == "add_list":
            n, err = site_queue.add_list(data.get("file"), data.get("pages"))
        elif act == "add_sem":   # «Собрать семантику» для выбранных сайтов в «Отчётах»
            from .reports_list import read_check
            checks = []
            for f in data.get("folders") or []:
                f = os.path.basename(str(f))
                c = read_check(REPORTS, f) if _has_crawl(_folder(f)) else None
                if c and not c.get("new_site"):
                    checks.append((f, c["site"]))
            if not checks:
                return self.answer("Выберите хотя бы один сайт с законченной проверкой.")
            n, err = site_queue.add_sem(checks), ""
            if data.get("start") and n:
                err = site_queue.action("start", {}, JOB)
        else:
            n, err = None, site_queue.action(act, data, JOB)
        if err:
            return self.answer(err)
        return self.send(200, {"ok": True, "added": n})

    def p_watch(self, path, data):
        from .. import watch
        act, url = path[11:], data.get("url") or ""
        if act == "save":
            weekly, err = watch.parse_weekly(data.get("weekly"))
            if not err:
                _cur, err = watch.update(url, monitor=bool(data.get("monitor")), weekly=weekly,
                                         pages=max(1, int(data.get("pages") or 10000)))
        elif act == "clients":
            # «Клиенты»: всем сайтам-клиентам одно время проверки по расписанию (ночью); окно проверяет их по одному.
            # Мониторинг и лимит страниц, если сайт уже в наблюдении, не меняются
            weekly, err = watch.parse_weekly(data.get("weekly"))
            for x in ([] if err else data.get("sites") or []):
                s = watch.find(x.get("url") or "")
                _cur, err = watch.update(x.get("url") or "", monitor=bool(s and s.get("monitor")), weekly=weekly,
                                         pages=int((s or {}).get("pages") or x.get("pages") or 10000))
                if err:
                    break
        elif act == "remove":
            err = watch.remove(url)
        elif act == "check_now":  # мониторинг сейчас (без повторной перепроверки — человек смотрит сам)
            s = watch.find(url)
            err = "" if s else "Такого сайта в наблюдении нет."
            if s:
                watch.monitor(s["url"], REPORTS, pause=0)
        else:
            err = "нет такого действия"
        return self.answer(err)

    def p_semdec(self, path, data):  # решения по семантике (window/semdec.py)
        from . import semdec
        return semdec.post(self, path, data)

    def p_semsort(self, path, data):  # разложить новые запросы по группам, словари (window/semsort.py)
        from . import semsort
        return semsort.post(self, path, data)

    def p_dict(self, path, data):  # «Словарь»: правила, темы, привязка сайтов, из файла (window/dictview.py)
        from . import dictview
        return dictview.post(self, data)

    def p_sembx(self, path, data):  # Букварикс: загрузить через API, добавить файл, убрать домен (window/sembx.py)
        from . import sembx
        return sembx.post(self, data)

    def p_semdemand(self, path, data):  # вкладка «Спрос»: поставить загрузку из Вордстата в очередь (window/semdemand.py)
        from . import semdemand
        return semdemand.post(self, data)

    def p_semupd(self, path, data):  # вкладка «Обновления»: загрузить данные, «Что просело», свои даты встрясок
        from . import semupd
        return semupd.post(self, data)

    def p_stop(self, path, data):
        JOB.stop()
        return self.send(200, {"ok": True})


def list_results(limit=8):
    """Последние проверки списков и переездов (папка «reports/списки») - для окна."""
    import json as _j
    import time as _t
    lists = os.path.join(REPORTS, "списки")
    try:
        names = sorted((n for n in os.listdir(lists) if n.endswith(".html")),
                       key=lambda n: -os.path.getmtime(os.path.join(lists, n)))
    except OSError:
        return []
    out = []
    for n in names[:limit]:
        base = os.path.join(lists, n[:-5])
        info = {}
        try:
            with open(base + ".json", encoding="utf-8") as f:
                info = _j.load(f)
        except (OSError, ValueError):
            pass
        c = info.get("counts") or {}
        kind, _, rest = n[:-5].partition("_")
        host = rest.rsplit("_", 2)[0]
        out.append({"path": "списки/" + n, "title": ("Переезд: " if kind == "переезд" else "Список: ") + host,
                    "when": _t.strftime("%d.%m %H:%M", _t.localtime(os.path.getmtime(base + ".html"))),
                    "total": info.get("total", 0), "bad": c.get("gone", 0) + c.get("home", 0) + c.get("loop", 0)})
    return out


def watch_status():
    from .. import watch
    out = []
    for s in watch.sites():
        out.append(dict(s, weekly_text=watch.weekly_text(s.get("weekly")), mon=watch.mon_state(s["url"])))
    return {"sites": out, "days": watch.DAYS}


def start_semantics_light(folder):
    """Очередь сайтов: быстрая семантика готовой проверки (главная и разделы, без Вордстата). Ошибка или ""."""
    if JOB.running:
        return "Проверка уже идёт."
    full = _folder(folder)
    if not folder or not _has_crawl(full):
        return "Нет такой проверки."
    if not JOB.start([], [], semantics_folders=[full], label="семантика " + os.path.basename(full), from_queue=True,
                     light=True):
        return "Проверка уже идёт."
    return ""


def start_check(data):
    """Запустить проверку с настройками из окна (или из Telegram / расписания). Возвращает ошибку или ""."""
    if JOB.running:
        return BUSY_START
    site = (data.get("site") or "").strip()
    mode = data.get("mode") or "site"
    scope_args = []
    if mode == "list":  # «Мой список адресов»: адреса — во временный файл, crawl.py скопирует их в папку проверки
        import re
        import tempfile
        urls = re.findall(r"https?://\S+", data.get("urls") or "")
        if not urls:
            return "Вставьте полные адреса, начинающиеся с https://"
        fd, path = tempfile.mkstemp(prefix="clayler-list-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        site = urls[0]
        scope_args = ["--only-urls", path]
    elif mode == "section":
        scope_args = ["--only-section"]
    if not site:
        return "Укажите адрес сайта."
    if "://" not in site:
        site = "https://" + site
    args = [site, "--max-pages", str(max(1, int(data.get("pages") or 10000)))] + scope_args
    if data.get("js"):
        args.append("--js")
    if data.get("resume"):
        args.append("--continue")
    if data.get("robots") == "yandex":
        args += ["--robots", "yandex"]
    if data.get("ua") in ("googlebot", "yandexbot", "chrome"):
        args += ["--ua", data["ua"]]
    speed = data.get("speed") or "normal"
    if speed == "slow":
        args += ["--threads", "2", "--delay", "1"]
    elif speed == "fast":
        args += ["--threads", "8", "--delay", "0.05"]
    if data.get("ignore_robots"):
        args.append("--ignore-robots")
    if data.get("subdomains"):
        args.append("--subdomains")
    if data.get("regions"):
        args.append("--regions")
    if data.get("no_external"):
        args.append("--no-external")
    from ..crawler.common import read_masks
    for m in read_masks(data.get("skip") or "")[:50]:   # «Не обходить адреса»: маски с *
        args += ["--skip-mask", m]
    comps = []
    for line in (data.get("competitors") or "").replace(",", "\n").splitlines():
        c = line.strip()
        if c:
            comps.append(c if "://" in c else "https://" + c)
    args = args[1:]  # адрес подставляется для каждого сайта отдельно
    if not JOB.start([site] + comps[:5], args, from_queue=bool(data.get("queue"))):
        return BUSY_START
    return ""


def _oauth_page(err):
    import html
    msg = ("<h2>Не получилось</h2><p>" + html.escape(err) + "</p>") if err else         "<h2>Готово - доступ подключён</h2><p>Пароль программа не получала. Эту вкладку можно закрыть "         "и вернуться в окно Clayler SEO.</p>"
    return ("<!doctype html><meta charset=utf-8><title>Clayler SEO</title>"
            "<body style='font:16px system-ui;max-width:560px;margin:60px auto;padding:0 16px'>" + msg)


def open_window(url):
    """Открывает программу отдельным окном Chrome (без вкладок и адресной строки),
    если Chrome нет — Edge, если и его нет — в обычном браузере."""
    from ..pdf import find_browser   # Chrome или Edge: умеют открыть страницу отдельным окном (--app)
    exe = find_browser()
    if exe:
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1150,900"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    webbrowser.open(url)


def _already_running():
    """Если программа уже запущена — вернуть её адрес, чтобы не запускать вторую копию."""
    from ..sysproxy import urlopen   # свой компьютер - без прокси VPN (через прокси был ответ 502, и шла вторая копия)
    for p in range(8900, 8920):
        try:
            with urlopen(f"http://127.0.0.1:{p}/api/status", timeout=0.5) as r:
                if "running" in r.read(200).decode("utf-8", "ignore"):
                    return f"http://127.0.0.1:{p}/"
        except Exception:
            continue
    return None


def main():
    # «Семантику» и её страницы окна - загрузить сразу, до потоков бота, наблюдения и очереди: два потока, впервые
    # загружающие эти модули одновременно, падали с _DeadlockError (/api/version при открытии страницы)
    from .. import semantics  # noqa: F401
    from . import dictview, sembx, semdec, semdemand, semsort, semupd  # noqa: F401
    running = _already_running()
    if running:
        print("Программа уже запущена - открываю её окно: " + running)
        open_window(running)
        return
    port = None
    for p in range(8900, 8920):
        try:
            srv = Server(("127.0.0.1", p), H)
            port = p
            break
        except OSError:
            continue
    if not port:
        print("Не удалось занять порт 8900–8919. Закройте другие копии программы.")
        return
    url = f"http://127.0.0.1:{port}/"
    print(f"Clayler SEO работает: {url}")
    print("Окно программы открылось (отдельное окно Chrome или вкладка браузера).")
    print("Если окно случайно закрыли, откройте этот адрес в браузере: " + url)
    print("Это чёрное окно не закрывайте, пока работаете.")
    print("Чтобы выйти, закройте это окно.")
    threading.Timer(0.8, lambda: open_window(url)).start()
    from .. import telegram, watch
    telegram.start_bot(JOB, lambda url, pages=10000: start_check({"site": url, "pages": pages}))  # команды боту
    from . import events

    def alert(text, url=None):   # наблюдение: в Telegram и плашкой в окне
        events.from_telegram(text)
        telegram.send_alert(text, url)
    watch.start(JOB, lambda url, pages: start_check({"site": url, "pages": pages}), alert, REPORTS)
    from .. import applog
    applog.write("info", "Программа запущена: " + url)
    from .. import site_queue
    site_queue.start(JOB, start_check, start_semantics_light)  # «Очередь сайтов»: сайты по одному, пока окно открыто
    from .. import direct
    direct.resume()   # загрузка частотности из Директа, не законченная до перезапуска окна
    from ..semantics import demand
    demand.season_auto()   # своя сезонность: раз в месяц запомнить частоту главных запросов
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
