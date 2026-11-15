"""Ошибки простыми словами: что случилось и что сделать. Техническое сообщение остаётся «Подробнее».

explain(text) -> {"title": ..., "todo": ..., "detail": ...}. Используют плашки-уведомления окна и «Журнал».
Правило ищется по тексту ошибки (английский текст Python и Windows, коды ответа сайта). Если текст уже
русский и понятный, он и остаётся заголовком."""
import re

from .access_check import TEXT as _ACCESS

# (шаблон, что случилось, что сделать) - первое совпадение
RULES = [
    # причины из access_check.py (dog-comfort.kz): обрыв на шаге https и отказ только программам
    (r"режут по дороге|сброшено на шаге https", *_ACCESS["tls_reset"]),
    (r"обрывают через раз", *_ACCESS["tls_flaky"]),
    (r"не пускает программы", *_ACCESS["bots_blocked"]),
    (r"закрыт и для браузера", *_ACCESS["blocked"]),
    (r"обрывает соединение без ответа", *_ACCESS["dropped"]),
    (r"No space left|WinError 112|ENOSPC|disk full|недостаточно места",
     "На диске кончилось место",
     "Освободите место на диске: удалите или перенесите старые проверки из папки «reports», потом запустите ещё раз."),
    (r"MemoryError|out of memory|нехватк\w* памяти",
     "Компьютеру не хватило памяти",
     "Закройте лишние программы и вкладки браузера. Если не помогло, проверьте меньше страниц за раз."),
    (r"PermissionError|Permission denied|WinError 32|WinError 5\b|being used by another process|занят другим процессом|открыт в Word|открыт в Excel",
     "Файл занят другой программой",
     "Закройте этот файл в Word, Excel или браузере и нажмите кнопку ещё раз."),
    (r"Token has been expired or revoked",
     "Подключение к Google отключилось",
     "Переподключите Google: «Подключения» внизу меню слева. Если это повторяется раз в неделю, приложение в Google "
     "Cloud в тестовом режиме: откройте Google Auth Platform → Audience и нажмите Publish app."),
    (r"invalid_grant|unauthori[sz]ed|\b401\b|token (?:has )?expired|токен устарел|OAuth token|invalid[_ ]token",
     "Подключение к Яндексу или Google устарело",
     "Переподключите аккаунт: «Подключения» внизу меню слева, потом нажмите кнопку ещё раз."),
    (r"getaddrinfo|Name or service not known|nodename nor servname|No address associated|WinError 11001|11004|не найден адрес",
     "Сайт не найден по этому адресу",
     "Проверьте адрес на опечатки и откройте его в браузере. Если сайт не открывается и там, дело не в программе."),
    (r"CERTIFICATE_VERIFY_FAILED|SSLError|SSL:|certificate|сертификат",
     "Проблема с защищённым соединением (HTTPS) сайта",
     "Откройте сайт в браузере. Если браузер предупреждает о небезопасном сайте, это проблема сайта, её стоит отметить в аудите."),
    (r"timed out|Timeout|WinError 10060|таймаут|не ответил за",
     "Сайт слишком долго не отвечает",
     "Откройте сайт в браузере. Если он медленный, при запуске выберите скорость «Бережно» (в «Дополнительных настройках») или запустите позже."),
    (r"WinError 1005[34]|Connection reset|ConnectionReset|ConnectionAborted|RemoteDisconnected|Connection refused|WinError 10061|Connection aborted",
     "Сайт оборвал соединение",
     "Часто так сайт защищается от частых запросов. При запуске выберите скорость «Бережно» (в «Дополнительных настройках»)."),
    (r"\b429\b|Too Many Requests",
     "Сайт просит обращаться реже",
     "При запуске выберите скорость «Бережно» (в «Дополнительных настройках») и запустите ещё раз."),
    (r"\b403\b|Forbidden|captcha|капч|DDoS-Guard|Cloudflare",
     "Сайт закрыл доступ программе",
     "Сайт защищается от роботов. Попробуйте режим JavaScript или настройте доступ в «Закрытые сайты»."),
    (r"\b50[0-4]\b|Service Unavailable|Bad Gateway|Internal Server Error|Gateway Time-?out",
     "Сайт отвечает ошибкой сервера",
     "Сайт сейчас работает с перебоями. Попробуйте позже; если повторяется, это стоит отметить в аудите."),
    (r"Failed to fetch|NetworkError|Load failed|ERR_CONNECTION",
     "Окно не достучалось до программы",
     "Проверьте, что чёрное окно программы открыто. Если закрыто, запустите «Clayler SEO.bat» заново."),
    (r"database is locked|disk I/O error|malformed|sqlite",
     "Не получилось прочитать базу проверки",
     "Скорее всего, эту проверку сейчас читает другая операция. Подождите минуту и нажмите ещё раз."),
    (r"Traceback|Exception|Error\b|Errno|WinError|Unexpected token|is not defined|Cannot read propert",
     "Внутренняя ошибка программы",
     "Нажмите кнопку ещё раз. Если ошибка повторится, откройте вкладку «Журнал» и покажите запись чату, который правит программу."),
]
_RULES = [(re.compile(p, re.I), t, d) for p, t, d in RULES]
_LATIN = re.compile(r"[A-Za-z]{4,}")


def explain(text):
    """Что случилось и что сделать, простыми словами. detail - исходный текст (для «Подробнее»)."""
    s = str(text or "").strip()
    for rx, title, todo in _RULES:
        if rx.search(s):
            return {"title": title, "todo": todo, "detail": s}
    if s and not _LATIN.search(re.sub(r"https?://\S+|\b[\w.-]+\.[a-zа-я]{2,}\b", "", s)):
        return {"title": s, "todo": "", "detail": ""}   # уже по-русски и понятно
    return {"title": "Что-то пошло не так", "todo": "Нажмите кнопку ещё раз. Если повторится, откройте вкладку «Журнал».",
            "detail": s}


# ---------- строка журнала с технической ошибкой → простыми словами (по скриншоту пользователя:
# «Яндекс Вебмастер: … - <urlopen error _ssl.c:1064: The handshake operation timed out>», JSON от Google 403,
# «Page.goto: net::ERR_CONNECTION_CLOSED»). Оригинал остаётся в «Журнале» (Подробнее).
TECH = re.compile(r"urlopen error|Page\.\w+:|net::ERR_|Errno|WinError|HTTP Error \d|\{\s*\"error\"|_ssl\.c|"
                  r"timed out|Connection (?:reset|refused|aborted)|Request had|insufficient authentication|"
                  r"invalid_grant|Token has been|RemoteDisconnected|Max retries|getaddrinfo|"
                  r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*(?:Error|Exception)\b|ответил \d{3}: \{", re.I)
_TRACE = re.compile(r"^(Traceback|\s+File \"|\w+(?:Error|Exception|Interrupt):)")
# службы, к которым ходит программа: ошибка связи с ними - не беда проверяемого сайта
SERVICES = [(r"Вебмастер", "Яндекс Вебмастером"), (r"Search Console", "Google Search Console"),
            (r"Метрик", "Яндекс Метрикой"), (r"Telegram|телеграм", "Telegram"), (r"Wordstat|Вордстат", "Wordstat"),
            (r"Букварикс|bukvarix", "Буквариксом"), (r"Директ", "Яндекс Директом"), (r"Google", "Google"),
            (r"Яндекс", "Яндексом"), (r"орфограф|Спеллер", "проверкой орфографии Яндекса")]
_NET = re.compile(r"timed out|handshake|urlopen error|Connection (?:reset|refused|aborted)|RemoteDisconnected|"
                  r"getaddrinfo|WinError 100|_ssl\.c|EOF occurred|Max retries|Таймаут|Соединение сброшено", re.I)
_BROWSER_NET = re.compile(r"net::ERR_(CONNECTION_(?:CLOSED|RESET|REFUSED|ABORTED|TIMED_OUT)|TIMED_OUT|SSL_\w+|"
                          r"EMPTY_RESPONSE|NAME_NOT_RESOLVED|INTERNET_DISCONNECTED|PROXY_\w+|TUNNEL_\w+)")


def service_error(service, err):
    """Ошибка связи со службой (Вебмастер, Search Console, Метрика…): что случилось и что сделать, одной строкой."""
    s = str(err or "")
    from .accounts import NO_SCOPE, EXPIRED, SCOPE_TEXT
    if NO_SCOPE.search(s):
        return "у программы нет доступа к Search Console. " + SCOPE_TEXT
    if re.search(r"\b403\b", s):
        return f"{service} не дал доступ (403): переподключите аккаунт в «Подключениях» и разрешите всё, что спросит вход"
    if EXPIRED.search(s):
        return "вход истёк: переподключите аккаунт в «Подключениях» (внизу меню слева)"
    if _NET.search(s):
        return (f"нет связи с {service}: соединение не открылось или оборвалось. Обычно это VPN или временный сбой - "
                f"попробуйте ещё раз (для отчёта - «Обновить отчёт»), при необходимости выключите VPN или включите его для всех сайтов")
    e = explain(s)
    return (e["title"][0].lower() + e["title"][1:] + (". " + e["todo"] if e["todo"] else "")) if e["title"] else s


def browser_error(err):
    """Встроенный браузер не открыл страницу (Page.goto: net::ERR_…): простыми словами."""
    s = str(err or "")
    m = _BROWSER_NET.search(s)
    if not m:
        e = explain(s)
        return e["title"][0].lower() + e["title"][1:]
    code = m.group(1)
    if code.startswith("NAME_NOT_RESOLVED"):
        return "домен не находится"
    if code.startswith(("PROXY", "TUNNEL")):
        return "прокси Windows (VPN-программа) не подключился к сайту"
    if code.startswith("INTERNET"):
        return "нет интернета"
    if "TIMED_OUT" in code:
        return "сайт не ответил вовремя"
    return "соединение оборвали (провайдер или защита сайта; часто помогает VPN)"


def humanize(line):
    """Строка журнала с технической ошибкой → та же строка, но ошибка простыми словами. Строки трассировки Python
    (Traceback) не трогаем: по ним очередь находит сбой программы. Без технической ошибки - как есть."""
    s = str(line)
    if not TECH.search(s) or _TRACE.match(s.strip("\r\n")) or s.lstrip().startswith("File \""):
        return s
    start = TECH.search(s).start()
    cut = max(s.rfind(" - ", 0, start), s.rfind(": ", 0, start), s.rfind(" (", 0, start))
    # «Search Console: не получилось …» - двоеточие в названии службы не граница ошибки: ищем ближайшую к ошибке
    prefix, tail = (s[:cut], s[cut:].lstrip(" -:(").rstrip(")")) if cut > 0 else ("", s)
    if prefix and not re.search(r"[А-Яа-яЁё]", prefix):
        prefix, tail = "", s   # перед ошибкой нет русского текста - заменяем всю строку
    svc = next((name for rx, name in SERVICES if re.search(rx, prefix, re.I)), "")
    if _BROWSER_NET.search(tail):
        text = browser_error(tail)
    elif svc:
        text = service_error(svc, tail)
    else:
        e = explain(tail)
        text = e["title"][0].lower() + e["title"][1:] + (". " + e["todo"] if e["todo"] else "")
    lead = re.match(r"\s*", s).group(0)
    return (f"{prefix.rstrip()} - {text}" if prefix.strip() else lead + text[0].upper() + text[1:])
