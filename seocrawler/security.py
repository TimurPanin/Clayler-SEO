"""Проверка безопасности сайта, дополнение к поиску служебных файлов при обходе (extra_passes.check_exposed):
- заголовки защиты на главной: HSTS, X-Content-Type-Options, защита от встраивания в чужой сайт, Referrer-Policy, CSP;
- версии программ, которые сервер сообщает всем (Server, X-Powered-By), и устаревший PHP;
- ещё служебные файлы: копии файлов настроек с паролем к базе, настройки доступа к серверу (sftp), .env-варианты,
  архивы .rar, журнал ошибок, Adminer, состояние сервера, открытые списки файлов папок;
- с 30.10.2026: cookie главной без флагов Secure / HttpOnly / SameSite; WordPress - логины пользователей через
  /wp-json/wp/v2/users и /?author=1, открытый xmlrpc.php; скрипты, стили и фреймы с доменов, которых нет в DNS
  (домен может купить кто угодно и подменить код); jQuery старше 3.5 и версия движка в мета-теге generator.
  Только чтение того, что сайт отдаёт всем; логины WordPress и xmlrpc - только у своего сайта (как служебные файлы).
У найденного .env записываются только ИМЕНА переменных (DB_PASSWORD…), значения не сохраняются и не показываются.
Один раз на проверку при сборке отчёта (нужен интернет), результат — meta «security». У конкурентов служебные файлы
не ищутся (как и при обходе: --no-exposed), заголовки — смотрятся."""
import datetime as dt
import re
from urllib.parse import urljoin, urlsplit
from .site_tech import ENGINES

VERSION = 4  # 2 -: мета-теги referrer и Content-Security-Policy считаются; 3 -: cookie,
# WordPress, домены скриптов, jQuery, generator
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
SECRET = re.compile(r"PASS|SECRET|KEY|TOKEN|PWD|AUTH|PRIVATE|DSN|DATABASE_URL", re.I)

# заголовок → (что даёт, что поставить)
HEADERS = [
    ("strict-transport-security", "HSTS", "браузер всегда открывает сайт только по защищённому https, даже если "
     "посетитель набрал http:// или перешёл по старой ссылке", "Strict-Transport-Security: max-age=31536000"),
    ("x-content-type-options", "X-Content-Type-Options", "браузер не «угадывает» тип файла - так нельзя выдать "
     "загруженную картинку за скрипт", "X-Content-Type-Options: nosniff"),
    ("x-frame-options", "X-Frame-Options", "чужой сайт не может показать ваш внутри своего и подсунуть "
     "посетителю невидимую кнопку (кликджекинг)", "X-Frame-Options: SAMEORIGIN"),
    ("referrer-policy", "Referrer-Policy", "полные адреса страниц (иногда с личными данными в параметрах) не уходят "
     "на чужие сайты", "Referrer-Policy: strict-origin-when-cross-origin"),
    ("content-security-policy", "Content-Security-Policy", "браузер выполняет скрипты только с разрешённых адресов - "
     "главная защита от внедрения чужого кода", "Content-Security-Policy: (составляется под сайт)"),
]
PHP_SUPPORTED = (8, 2)  # PHP ниже 8.2 больше не получает исправлений безопасности (на осень 2026 года)
JQUERY_SAFE = (3, 5)    # jQuery до 3.5: известные уязвимости XSS (CVE-2020-11022, CVE-2020-11023)
# cookie входа и сессии: без HttpOnly их может украсть чужой скрипт на странице
SESSION_COOKIE = re.compile(r"sess|sid$|auth|token|login|logged_in|remember|BITRIX_SM_UIDH|csrf", re.I)


def _fetcher():
    from .fetcher import Fetcher
    return Fetcher(UA, timeout=12, total_timeout=20)


def _home(f, start):
    """Главная после редиректов: (адрес, ответ)."""
    url = "/".join(start.split("/", 3)[:3]) + "/"
    r = None
    for _ in range(6):
        r = f.fetch(url)
        if r.status in (301, 302, 303, 307, 308) and r.location:
            url = urljoin(url, r.location)
            continue
        break
    return url, r


def _text(b):
    return (b or b"")[:4000].decode("utf-8", "replace")


def _not_html(b):
    return not re.search(r"<(html|body|head|!doctype)", _text(b), re.I)


MODX_SIGN = re.compile("|".join(next(e for e in ENGINES if e[0] == "MODX")[2]), re.I)   # одни признаки с site_tech
MODX_SETUP = re.compile(r"<title>[^<]*(?:modx[^<]*(?:install|setup|установ)|(?:install|setup|установ)[^<]*modx)", re.I)


def modx_probes():
    """Типичные риски MODX (документация «Securing MODX»: убрать setup/ после установки, закрыть core/ от посетителей).
    Файл считается найденным только по содержимому: сайт, отдающий на любой адрес главную, сюда не попадает."""
    conf = lambda b: _not_html(b) and re.search(r"\$database_password|\$database_user", _text(b))
    out = [("/setup/", "установщик движка MODX (папка setup)", lambda b: MODX_SETUP.search(_text(b))),
           ("/core/docs/changelog.txt", "служебная папка движка MODX открыта (core)",
            lambda b: _not_html(b) and "modx" in _text(b).lower())]
    out += [(f"/core/config/config.inc.php{end}", "копия файла настроек с паролем к базе", conf)
            for end in ("", ".bak", ".old", "~", ".save", ".txt")]
    return out


def modx_manager(f, base: str) -> str:
    """Вход в управление по стандартному адресу /manager/ - не взлом, а замечание. Только смотрим страницу, ничего не
    вводим."""
    r = f.fetch(base + "/manager/")
    text = _text(r.body)
    found = r.status == 200 and "modx" in text.lower() and re.search(r"type=[\"']?password", text, re.I)
    return base + "/manager/" if found else ""


def env_keys(body):
    """Имена переменных из .env, в которых похоже лежат пароли и ключи. Значения не берём."""
    names = re.findall(r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*\S", _text(body))
    return [n for n in dict.fromkeys(names) if SECRET.search(n)][:12]


def probes(bare):
    name = bare.split(".")[0]
    env = lambda b: _not_html(b) and len(re.findall(r"(?m)^[A-Z][A-Z0-9_]*=", _text(b))) >= 2
    conf = lambda b: _not_html(b) and re.search(r"DB_PASSWORD|DBPassword|\$db_?pass|\$database_password|"
                                                r"'password'\s*=>|define\(\s*'DB_",
                                                _text(b), re.I)
    out = [(f"/{p}", "файл с паролями и ключами (.env)", env)
           for p in (".env.local", ".env.production", ".env.prod", ".env.backup", ".env.old", ".env.save")]
    out += [(f"/{p}", "копия файла настроек с паролем к базе", conf)
            for p in ("wp-config.php.bak", "wp-config.php~", "wp-config.old", "wp-config.php.save", "wp-config.txt",
                      "config.php.bak", "config.php~", "configuration.php.bak", "bitrix/php_interface/dbconn.php.bak",
                      "bitrix/.settings.php.bak")]
    out += [(f"/{p}", "настройки доступа к серверу (sftp)",
             lambda b: _not_html(b) and re.search(r'"(password|host)"\s*:', _text(b)))
            for p in (".vscode/sftp.json", "sftp-config.json", ".ftpconfig")]
    out += [(f"/{p}", "архив сайта (бэкап)", lambda b: (b or b"")[:4] == b"Rar!")
            for p in ("backup.rar", "site.rar", "www.rar", f"{name}.rar", f"{bare}.rar")]
    out += [("/wp-content/debug.log", "журнал ошибок сайта (debug.log)",
             lambda b: _not_html(b) and re.search(r"PHP (Notice|Warning|Fatal|Deprecated)", _text(b))),
            ("/adminer.php", "вход в базу данных (Adminer)", lambda b: "adminer" in _text(b).lower() and "<form" in _text(b)),
            ("/server-status", "состояние сервера (server-status)", lambda b: "Apache Server Status" in _text(b))]
    out += [(f"/{p}/", "список файлов папки открыт", lambda b: re.search(r"<title>\s*Index of /", _text(b), re.I))
            for p in ("upload", "uploads", "files", "images", "wp-content/uploads", "backup", "tmp")]
    return out


def check(start, exposed=None, look_files=True, log=print, ext=(), libs=()):
    """ext - [(адрес файла с чужого сайта, страница)] из проверки, libs - адреса скриптов с jquery в имени."""
    f = _fetcher()
    url, r = _home(f, start)
    out = {"version": VERSION, "checked_at": dt.date.today().isoformat(), "url": url, "https": url.startswith("https"),
           "headers": {}, "found": [], "checked": 0, "env_keys": {}}
    if not r or r.status != 200:
        out["error"] = f"главная не открылась ({r.status or r.error if r else 'нет ответа'})"
        return out
    keep = [h for h, *_ in HEADERS] + ["server", "x-powered-by", "x-aspnet-version"]
    out["headers"] = {h: r.headers.get(h, "") for h in keep if r.headers.get(h)}
    csp = r.headers.get("content-security-policy", "")
    if "frame-ancestors" in csp:  # CSP frame-ancestors заменяет X-Frame-Options
        out["headers"].setdefault("x-frame-options", "через Content-Security-Policy")
    # мета-теги в <head> действуют как заголовки Referrer-Policy и CSP (на GitHub Pages и Тильде иначе никак)
    head = (r.body or b"")[:200_000].decode("utf-8", "replace").split("</head>")[0]
    if re.search(r"<meta[^>]+name=[\"']?referrer[\"']?[^>]*content=[\"']?[\w-]", head, re.I):
        out["headers"].setdefault("referrer-policy", "через мета-тег")
    if re.search(r"<meta[^>]+http-equiv=[\"']?content-security-policy[\"']?[^>]*content=[\"']?\S", head, re.I):
        out["headers"].setdefault("content-security-policy", "через мета-тег")
    out["set_cookie"] = cookie_problems(r.headers.get("set-cookie", ""), out["https"])
    m = re.search(r"<meta[^>]+name=[\"']?generator[\"']?[^>]*content=[\"']([^\"']*\d+\.\d+[^\"']*)", head, re.I)
    out["generator"] = m.group(1).strip()[:80] if m else ""
    out["libs"] = old_libs(libs)
    out["dead_hosts"] = dead_hosts(ext, urlsplit(url).hostname or "")
    if not look_files:
        return out
    if re.search(r"/wp-(content|includes)/", head + _text(r.body), re.I):
        out["wp"] = wordpress(f, url.rstrip("/"))
    is_modx = bool(MODX_SIGN.search(head + _text(r.body)))
    if is_modx:
        out["modx_manager"] = modx_manager(f, url.rstrip("/"))
    host = urlsplit(url).hostname or ""
    bare = host[4:] if host.startswith("www.") else host
    base = url.rstrip("/")
    for path, what, ok in probes(bare) + (modx_probes() if is_modx else []):
        out["checked"] += 1
        binary = path.endswith(".rar")
        rr = f.fetch(base + path, read_body=False, peek=64) if binary else f.fetch(base + path, any_type=True)
        if rr.status == 200 and rr.body and ok(rr.body):
            item = {"url": base + path, "what": what}
            if ".env" in path:
                out["env_keys"][base + path] = env_keys(rr.body)
            out["found"].append(item)
    for x in (exposed or {}).get("found", []):  # .env, найденный при обходе: какие в нём переменные
        if ".env" in x["url"] and x["url"] not in out["env_keys"]:
            rr = f.fetch(x["url"], any_type=True)
            if rr.status == 200 and rr.body:
                out["env_keys"][x["url"]] = env_keys(rr.body)
    out["checked"] += (exposed or {}).get("checked", 0)  # и то, что смотрели при обходе
    if out["found"]:
        log(f"   ВНИМАНИЕ: ещё открытые служебные файлы: {len(out['found'])}")
    return out


def ensure(store, log=print):
    """Один раз на проверку, при сборке отчёта."""
    old = store.get_meta("security", None)
    if old and old.get("version") == VERSION:
        return old
    start = store.get_meta("start", "")
    if not start:
        return None
    look = (store.get_meta("config", None) or {}).get("check_exposed", True) is not False
    log("Проверяю безопасность сайта: заголовки защиты, служебные файлы, cookie, домены скриптов...")
    own = (urlsplit(start).hostname or "").lower()
    own = own[4:] if own.startswith("www.") else own
    ext, libs = [], []
    try:   # скрипты, стили и фреймы с чужих сайтов (по одному примеру на домен) и файлы jQuery
        seen = set()
        for src, page in store.db.execute("SELECT src, MIN(page) FROM resources WHERE type IN ('js', 'css', 'iframe') "
                                          "AND src LIKE 'http%' GROUP BY src"):
            h = (urlsplit(src).hostname or "").lower()
            if h and h not in seen and h != own and not h.endswith("." + own):
                seen.add(h)
                ext.append((src, page))
        libs = [s for (s,) in store.db.execute("SELECT DISTINCT src FROM resources WHERE type='js' AND "
                                               "lower(src) LIKE '%jquery%' LIMIT 200")]
    except Exception:
        pass
    try:
        sec = check(start, store.get_meta("exposed", None), look, log, ext, libs)
        try:   # были ли вообще стили и скрипты в проверке (иначе «нет мёртвых доменов» - не проверено, а не «в порядке»)
            sec["res_checked"] = bool(store.db.execute(
                "SELECT 1 FROM resources WHERE type IN ('js', 'css') LIMIT 1").fetchone())
        except Exception:
            pass
    except Exception as e:
        sec = {"version": VERSION, "checked_at": dt.date.today().isoformat(), "error": str(e)[:150]}
    store.set_meta("security", sec)
    store.commit()
    return sec


def cookie_problems(raw, https):
    """[(cookie, каких флагов нет, cookie входа или сессии)] по заголовкам Set-Cookie главной (по строке на cookie).
    Secure нужен только на https-сайте, HttpOnly - только cookie входа и сессии (остальные читает сам сайт)."""
    out = []
    for line in (raw or "").split("\n"):
        name = line.split("=", 1)[0].strip()
        if not name or "=" not in line:
            continue
        flags = {p.strip().split("=", 1)[0].lower() for p in line.split(";")[1:]}
        sess = bool(SESSION_COOKIE.search(name))
        miss = [f for f, need in (("Secure", https), ("HttpOnly", sess), ("SameSite", True)) if need and f.lower() not in flags]
        if miss and not (miss == ["SameSite"] and not sess):   # одной SameSite у простой cookie мало для замечания
            out.append((name[:60], miss, sess))
    return out[:20]


def old_libs(srcs):
    """[(адрес, «jQuery», версия)] для jQuery старше JQUERY_SAFE: версия из имени файла (jquery-1.12.4.min.js)
    или из ?ver= у jquery.js / jquery.min.js (WordPress). jquery-migrate и плагины jQuery не в счёт."""
    out, seen = [], set()
    for s in srcs or ():
        path = urlsplit(s).path.lower().rsplit("/", 1)[-1]
        m = re.match(r"jquery[-.]?(\d+)\.(\d+)(?:\.(\d+))?(?:\.slim)?(?:\.min)?\.js$", path)
        if not m and re.fullmatch(r"jquery(?:\.slim)?(?:\.min)?\.js", path):
            m = re.search(r"[?&]ver=(\d+)\.(\d+)(?:\.(\d+))?", s)
        if not m:
            continue
        v = tuple(int(x or 0) for x in m.groups())
        if v[:2] < JQUERY_SAFE and v not in seen:
            seen.add(v)
            out.append((s, "jQuery", ".".join(str(x) for x in v)))
    return out[:10]


def _dns(host):
    """«ok» - имя есть в DNS; «none» - DNS точно ответил «такого имени нет»; «?» - не узнали (временный сбой DNS,
    нет сети). Раньше любой сбой считался «домена нет» - и временная ошибка DNS давала ложную критичную находку
."""
    import socket
    import time
    for i in range(2):
        try:
            socket.getaddrinfo(host, 443)
            return "ok"
        except UnicodeError:
            return "ok"    # кривое имя - не про «домен свободен»
        except socket.gaierror as e:
            if e.errno == socket.EAI_NONAME:   # Windows 11001, Linux -2: «такого имени нет»
                return "none"
        except OSError:
            pass
        if not i:
            time.sleep(0.5)
    return "?"


def _resolves(host):
    return _dns(host) == "ok"


def dead_hosts(ext, own):
    """Чужие домены скриптов, стилей и фреймов, которых нет в DNS и которые можно купить: [(домен, пример файла,
    страница)]. Если не находится в DNS и сам сайт - нет сети, ничего не пишем (иначе каждый домен был бы «мёртвым»).
    Удалённый поддомен существующего домена (old-cdn.client.ru при живом client.ru) купить нельзя - его файл просто не
    загружается, это пункт «Не загружаются стили, скрипты» (res_broken), а не этот."""
    if not ext or not own or not _resolves(own):
        return []
    out, cache = [], {}

    def dns(h):
        if h not in cache:
            cache[h] = _dns(h)
        return cache[h]
    for src, page in list(ext)[:80]:
        h = (urlsplit(src).hostname or "").lower().rstrip(".")
        if not h or dns(h) != "none":
            continue
        labels = h.split(".")
        if len(labels) > 2 and dns(".".join(labels[-2:])) == "ok":
            continue   # домен жив, нет только поддомена
        out.append((h, src, page))
    return out


def wordpress(f, base):
    """Имена пользователей WordPress (slug - имя в адресе автора, обычно сделано из логина, но не обязательно он сам;
    в данных по-старому «logins») и открытый xmlrpc.php. Только чтение: ни одного входа и подбора."""
    out = {"users": [], "xmlrpc": ""}
    r = f.fetch(base + "/wp-json/wp/v2/users", any_type=True)
    if r.status == 200 and r.body:
        try:
            import json
            data = json.loads(r.body.decode("utf-8", "replace"))
            slugs = [str(u.get("slug", ""))[:40] for u in data if isinstance(u, dict) and u.get("slug")]
        except (ValueError, AttributeError, TypeError):
            slugs = []
        if slugs:
            out["users"].append({"url": base + "/wp-json/wp/v2/users", "logins": slugs[:10]})
    r = f.fetch(base + "/?author=1")
    m = re.search(r"/author/([^/?#]+)", r.location or "") if r.status in (301, 302, 307, 308) else None
    if m:
        out["users"].append({"url": base + "/?author=1", "logins": [m.group(1)[:40]]})
    r = f.fetch(base + "/xmlrpc.php", any_type=True)
    if r.status in (200, 405) and "XML-RPC server accepts POST requests only" in _text(r.body):
        out["xmlrpc"] = base + "/xmlrpc.php"
    return out


def versions(headers):
    """[(что сообщает сервер, вывод)]; вывод «устарел», если PHP ниже поддерживаемого."""
    out = []
    for h in ("server", "x-powered-by", "x-aspnet-version"):
        v = (headers or {}).get(h, "")
        if not re.search(r"\d+\.\d+", v):
            continue
        m = re.search(r"PHP/(\d+)\.(\d+)", v, re.I)
        old = bool(m) and (int(m.group(1)), int(m.group(2))) < PHP_SUPPORTED
        out.append((f"{h.title()}: {v}", "PHP этой версии больше не получает исправлений безопасности" if old
                    else "версия видна всем - по ней подбирают известные уязвимости"))
    return out


# ---------- блок «Проверка безопасности» для отчётов (итог по пунктам: что проверено и что нашлось)

def summary_rows(sec, issues):
    by = {i.key: i for i in issues}
    rows = []  # (хорошо ли, пункт, подробности)
    exp = by.get("exposed_files")
    n_files = (sec or {}).get("checked", 0)
    rows.append((not exp, "Служебные файлы (.git, .env, архивы и дампы базы, копии настроек)",
                 f"открыто: {exp.count}" if exp else (f"ничего не открыто" + (f", проверено адресов: {n_files}" if n_files
                                                                               else ""))))
    dl = by.get("dir_listing")
    rows.append((not dl, "Списки файлов в папках сайта", f"открыто папок: {dl.count}" if dl else "закрыты"))
    if sec and not sec.get("error"):
        if sec.get("https"):
            for h, name, *_ in HEADERS:
                rows.append((bool(sec["headers"].get(h)), f"Заголовок {name}",
                             "есть" if sec["headers"].get(h) else "нет"))
        else:
            rows.append((False, "Защищённое соединение https", "сайт открывается по http"))
        v = versions(sec.get("headers"))
        rows.append((not v, "Версии ПО на сервере", "; ".join(a for a, _ in v) if v else "не видны"))
        if "set_cookie" in sec:   # проверки
            for key, name, ok_text in (("cookie_flags", "Флаги защиты у cookie", "в порядке"),
                                       ("dead_script_domain", "Скрипты и стили с несуществующих доменов", "нет"),
                                       ("old_jquery", "Старый jQuery (до 3.5)", "не найден")):
                if key != "cookie_flags" and sec.get("res_checked") is False and key not in by:
                    # стили и скрипты при обходе не собирались - «нет» было бы неправдой
                    rows.append((None, name, "не проверялось: стили и скрипты при этой проверке не собирались"))
                    continue
                rows.append((key not in by, name, f"проблема: {by[key].count_text}" if key in by else ok_text))
        if sec.get("wp") is not None:
            rows.append(("wp_users" not in by, "Имена пользователей WordPress",
                         f"видны: {by['wp_users'].count_text}" if "wp_users" in by else "закрыты"))
    for key, name in (("ssl_own", "Сертификат https"), ("cert_expiry", "Срок сертификата"),
                      ("domain_expiry", "Срок оплаты домена"),
                      ("mixed_active", "Скрипты и стили по http:// на https-страницах"),
                      ("mixed_passive", "Картинки по http:// на https-страницах")):
        rows.append((key not in by, name, f"проблема: {by[key].count_text}" if key in by else "в порядке"))
    return rows


def html_block(sec, issues, h2="h2", h2_cls="sec", cls="card"):
    if not sec:
        return ""
    rows = summary_rows(sec, issues)
    bad = sum(1 for ok, *_ in rows if ok is False)   # None - «не проверялось»: не замечание и не «в порядке»
    env = [(u, k) for u, k in (sec.get("env_keys") or {}).items() if k]
    from .fmt import esc as _e
    mark = {True: ("good", "#2f855a", "✓"), False: ("crit", "#c0392b", "✗"), None: ("mut", "#888", "-")}
    li = "".join(f'<tr><td style="width:28px;font-weight:700;color:var(--{mark[ok][0]},{mark[ok][1]})">{mark[ok][2]}'
                 f'</td><td>{_e(name)}</td><td class="mut">{_e(det)}</td></tr>' for ok, name, det in rows)
    env_p = "".join(f'<p class="warnbox"><b>Открыт файл с паролями</b> {_e(u)}: в нём есть {_e(", ".join(k))}. '
                    'Любой может их прочитать. Закройте файл и смените все эти пароли и ключи.</p>' for u, k in env)
    return (f'<{h2} class="{h2_cls}">Проверка безопасности</{h2}><div class="{cls}">'
            f'<p class="mut" style="margin:0 0 8px">Проверили то, что взломщики ищут на сайтах первым делом. '
            f'Пунктов с замечаниями: {bad} из {len(rows)}. Подробности и что сделать - в проблемах раздела '
            f'«Безопасность».</p>{env_p}<div class="tw" style="margin:0"><table class="rg"><tbody>{li}'
            f'</tbody></table></div></div>')


def audit_html(sec, issues):
    b = html_block(sec, issues, h2="h2", h2_cls="", cls="")
    return f'<section class="pt">{b}</section>' if b else ""
