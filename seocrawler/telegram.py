"""Сообщение в Telegram, когда проверка закончилась (для себя: если вы не у компьютера).

Пользователь один раз создаёт своего бота у @BotFather, вставляет его токен в окно программы и пишет боту
любое сообщение — программа находит этот чат сама (getUpdates) и дальше пишет туда. Токен хранится в «доступы.json»
зашифрованным средствами Windows (как ключи Яндекса и Google), в git не попадает.
Запросы к api.telegram.org идут через системный прокси Windows, если он настроен (urllib берёт его сам).

Пока окно программы открыто, бот отвечает на /status (что проверяется сейчас) и предупреждает, если проверка
застряла. Отвечает только в сохранённый чат — чужие сообщения боту игнорируются.
"""
import csv
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import accounts, sysproxy

API = os.environ.get("CLAYLER_TELEGRAM_TEST") or "https://api.telegram.org"
STUCK_SECONDS = 15 * 60
OPTIONS = {"enabled": True, "pdf": True, "stuck": True}  # галочки в окне и их значения по умолчанию

STEPS = [
    "Откройте в Telegram бота @BotFather и отправьте ему /newbot.",
    "Придумайте название (например «Clayler SEO») и имя бота на латинице, в конце - bot (например clayler_timur_bot).",
    "BotFather пришлёт токен - строку вида 123456789:AAH… Скопируйте её сюда и нажмите «Сохранить».",
    "Откройте своего нового бота (ссылка есть в том же сообщении BotFather), нажмите «Старт» или напишите ему «привет».",
    "Вернитесь сюда и нажмите «Найти чат и проверить» - в Telegram придёт пробное сообщение.",
]
COMMANDS = [("check", "Проверить сайт: /check site.ru"), ("express", "Экспресс-аудит на 1 лист: /express site.ru"), ("stop", "Остановить проверку"),
            ("status", "Что сейчас проверяется"), ("last", "Итог последней проверки"),
            ("sites", "Сайты под наблюдением"), ("watch", "Следить за сайтом: /watch site.ru"),
            ("weekly", "Раз в неделю: /weekly site.ru пн 09:00"),
            ("semantics", "Семантика сайта: /semantics site.ru"), ("help", "Все команды")]

_online = {"t": 0.0, "ok": None, "error": ""}  # последняя проверка связи (для значка в окне)


def _call(token, method, fields=None, timeout=20, files=None):
    url = f"{API}/bot{token}/{method}"
    headers = {}
    if files:  # отправка файла: multipart/form-data
        boundary = uuid.uuid4().hex
        body = b""
        for k, v in (fields or {}).items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        for k, (name, content) in files.items():
            # имя файла — UTF-8 как есть: filename*= Telegram не понимает и принимает файл за адрес
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                     f"filename=\"{name.replace(chr(34), '')}\"\r\n"
                     "Content-Type: application/octet-stream\r\n\r\n").encode() + content + b"\r\n"
        data = body + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    else:
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with sysproxy.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read() or b"{}")
        except ValueError:
            res = {}
        if e.code in (401, 404):
            raise RuntimeError("Telegram не узнал токен. Скопируйте его из сообщения @BotFather целиком.")
        raise RuntimeError("Telegram ответил: " + (res.get("description") or f"ошибка {e.code}"))
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError("Нет связи с Telegram. Если в браузере Telegram открывается только через VPN, "
                           "включите VPN или прокси для всего компьютера. (" + str(e)[:120] + ")")
    if not res.get("ok"):
        raise RuntimeError("Telegram ответил: " + (res.get("description") or "ошибка"))
    return res.get("result")


def _cfg():
    return accounts._get("telegram")


def _opt(cur, name):
    return cur.get(name, OPTIONS[name])


def _token():
    return accounts.unseal(_cfg()["token"])


def check_online(force=False):
    """Есть ли связь с ботом (getMe), не чаще раза в минуту. None — бот не настроен."""
    cur = _cfg()
    if not cur.get("token"):
        return None
    if force or time.time() - _online["t"] > 60:
        try:
            _call(_token(), "getMe", timeout=20)
            _mark(True)
        except Exception as e:
            _mark(False, e)
    return _online["ok"]


def _mark(ok, err=None):
    """Запомнить, есть ли связь. Через VPN запрос иногда не проходит с первого раза —
    «нет связи» показываем только после двух неудач подряд."""
    _online["t"] = time.time()
    if ok:
        _online.update(ok=True, error="", fails=0)
        return
    _online["fails"] = _online.get("fails", 0) + 1
    if _online["fails"] >= 2 or _online["ok"] is None:
        _online.update(ok=False, error=str(err)[:300])


def status(live=False):
    cur = _cfg()
    out = {"has_token": bool(cur.get("token")), "bot": cur.get("bot", ""), "chat": cur.get("chat_name", ""),
           "ready": bool(cur.get("token") and cur.get("chat_id")), "error": cur.get("error", ""), "steps": STEPS,
           "online": check_online() if live else _online["ok"]}
    for k in OPTIONS:
        out[k] = _opt(cur, k)
    if out["online"] is False:
        out["error"] = _online["error"]
    return out


def save_token(token):
    """Проверить токен у Telegram и сохранить. Чат пока не известен — его найдёт find_chat()."""
    token = (token or "").strip()
    if not token or ":" not in token:
        return "Вставьте токен от @BotFather - строку вида 123456789:AAH…"
    try:
        me = _call(token, "getMe")
    except RuntimeError as e:
        return str(e)
    accounts._put("telegram", token=accounts.seal(token), bot="@" + (me.get("username") or ""), chat_id=None,
                  chat_name=None, error=None)
    _online.update(t=time.time(), ok=True, error="")
    _set_commands(token)
    return ""


def _set_commands(token):
    """Меню команд у бота (кнопка «/» в Telegram)."""
    try:
        _call(token, "setMyCommands", {"commands": json.dumps([{"command": c, "description": d} for c, d in COMMANDS],
                                                             ensure_ascii=False)})
    except RuntimeError:
        pass


def find_chat():
    """Найти чат, где человек написал боту, запомнить и прислать пробное сообщение."""
    cur = _cfg()
    if not cur.get("token"):
        return "Сначала вставьте токен бота и нажмите «Сохранить»."
    try:
        updates = _call(_token(), "getUpdates", {"allowed_updates": '["message"]'})
    except RuntimeError as e:
        return str(e)
    chat = None
    for u in updates or []:
        c = (u.get("message") or {}).get("chat") or {}
        if c.get("type") == "private":
            chat = c  # последний написавший
    if not chat and cur.get("chat_id"):
        chat = {"id": cur["chat_id"], "first_name": cur.get("chat_name", "")}
    if not chat:
        return (f"Бот {cur.get('bot', '')} пока не получил от вас сообщений. Откройте его в Telegram, нажмите "
                "«Старт» или напишите «привет», потом нажмите эту кнопку ещё раз.")
    name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username") or ""
    accounts._put("telegram", chat_id=chat["id"], chat_name=name, error=None)
    return test()


def test():
    return send("✅ Clayler SEO на связи. Когда проверка сайта закончится, сообщение придёт сюда.\n"
                "Внизу чата - кнопки: проверить сайт, что идёт сейчас, последний итог, мои сайты.", menu=True)


def set_option(name, on):
    if name not in OPTIONS:
        return "Нет такой настройки."
    accounts._put("telegram", **{name: bool(on)})
    return ""


def disconnect():
    accounts._put("telegram", token=None, bot=None, chat_id=None, chat_name=None, error=None,
                  **{k: None for k in OPTIONS})
    _online.update(t=0.0, ok=None, error="")
    return ""


def send(text, buttons=None, menu=False):
    """Отправить сообщение себе. buttons — кнопки под сообщением: [[(надпись, данные), …], …];
    menu — показать меню кнопок внизу чата. Возвращает текст ошибки или ""."""
    cur = _cfg()
    if not (cur.get("token") and cur.get("chat_id")):
        return "Бот не настроен."
    fields = {"chat_id": cur["chat_id"], "text": str(text)[:4000], "parse_mode": "HTML",
              "disable_web_page_preview": "true"}
    rows = [r for r in (buttons or []) if r]
    if rows:
        fields["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r]
                                                                 for r in rows]}, ensure_ascii=False)
    elif menu:
        fields["reply_markup"] = json.dumps({"keyboard": [[{"text": t} for t in r] for r in MENU],
                                             "resize_keyboard": True, "is_persistent": True}, ensure_ascii=False)
    try:
        _call(_token(), "sendMessage", fields)
    except RuntimeError as e:
        accounts._put("telegram", error=str(e)[:300])
        return str(e)
    if cur.get("error"):
        accounts._put("telegram", error=None)
    return ""


def send_file(path, caption="", name=""):
    cur = _cfg()
    if not (cur.get("token") and cur.get("chat_id")):
        return "Бот не настроен."
    try:
        if os.path.getsize(path) > 45 * 1024 * 1024:
            return "файл больше 45 МБ - Telegram не примет"
        with open(path, "rb") as f:
            content = f.read()
        _call(_token(), "sendDocument", {"chat_id": cur["chat_id"], "caption": caption[:1000]}, timeout=120,
              files={"document": (name or os.path.basename(path), content)})
    except (RuntimeError, OSError) as e:
        return str(e)[:300]
    return ""


# ---------- сообщение об окончании проверки ----------

def _e(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _top_problems(folder, n=3):
    """Первые проблемы из проблемы.csv (там уже по порядку: сначала критичные, потом по числу страниц)."""
    try:
        with open(os.path.join(folder, "проблемы.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.reader(f, delimiter=";"))[1:]
    except OSError:
        return []
    icon = {"Критично": "🔴", "Предупреждение": "🟡"}
    return [f"{icon.get(r[0], '⚪')} {_e(r[2])} - {_e(r[3])}" for r in rows[:n] if len(r) > 3]


def _previous_health(folder, item):
    """Здоровье прошлой проверки того же сайта (www и без — один сайт), или None."""
    from .window.reports_list import list_checks
    for c in list_checks(os.path.dirname(folder)):
        if c["folder"] != os.path.basename(folder) and c["key"] == item.get("key") \
                and (c["started"] or c["folder"]) < (item.get("started") or item.get("folder") or "") \
                and (c.get("summary") or {}).get("health") is not None:
            return c["summary"]["health"]
    return None


HEALTH_DROP_ALARM = 10  # здоровье упало на столько процентов и больше — тревога в сообщении


def _broke(cmp):
    """Что сломалось с прошлой проверки: новые виды критичных проблем, сильное падение здоровья. [] — ничего."""
    if not cmp:
        return []
    out = []
    if cmp.get("new_crit"):
        out.append("🚨 Появились критичные ошибки, которых не было: " + "; ".join(_e(t) for t in cmp["new_crit"][:3])
                   + (f" и ещё {len(cmp['new_crit']) - 3}" if len(cmp["new_crit"]) > 3 else ""))
    d = (cmp.get("health_old") or 0) - (cmp.get("health_new") or 0)
    if d >= HEALTH_DROP_ALARM:
        out.append(f"📉 Здоровье упало на {d}: {cmp['health_old']}% → {cmp['health_new']}%")
    return out


def _changes(cmp):
    """Строки «что изменилось с прошлой проверки» для сообщения."""
    if not cmp:
        return []
    out = [f"С прошлой проверки: исправлено {cmp.get('fixed', 0)}, новых {cmp.get('added', 0)}"]
    out += [f"✅ {_e(x['title'])} ({x['old']} → {x['new']})" for x in (cmp.get("top_fixed") or [])[:2]]
    out += [f"➕ {_e(x['title'])} ({x['old']} → {x['new']})" for x in (cmp.get("top_added") or [])[:2]]
    return out + _broke(cmp)


def _site_block(folder, main, show_site=True):
    from .window.reports_list import read_check
    item = read_check(os.path.dirname(folder), os.path.basename(folder)) or {}
    s = item.get("summary") or {}
    site = item.get("site") or os.path.basename(folder)
    if not os.path.exists(os.path.join(folder, "отчёт.html")) or not s:
        return f"<b>{_e(site)}</b>: отчёт не собран"
    lines = [f"<b>{_e(site)}</b>" + ("" if main else " (конкурент)")] if show_site else []
    health = f"Здоровье: <b>{s.get('health', '-')}%</b>"
    if main:
        prev = _previous_health(folder, item)
        if prev is not None and s.get("health") is not None:
            d = s["health"] - prev
            health += f" (было {prev}%, " + ("без изменений)" if d == 0 else f"{'+' if d > 0 else '−'}{abs(d)})")
    lines.append(health)
    lines.append(f"Страниц: {s.get('html_ok', s.get('pages', 0))}"
                 + (f" · проверка шла {item['took']}" if item.get("took") and show_site else ""))
    if s.get("crit") or s.get("warn"):
        lines.append(f"Проблем: критичных {s.get('crit', 0)}, предупреждений {s.get('warn', 0)}")
    if main:
        lines += _changes(item.get("compare"))
        lines += _top_problems(folder)
    return "\n".join(lines)


def job_message(job):
    """Текст сообщения по законченной проверке из окна (Job)."""
    from .duration import fmt
    took = fmt((job.finished or 0) - job.started) if job.started else ""
    dirs = list(job.dirs) or ([job.out_dir] if job.out_dir else [])
    ok = [d for d in dirs if os.path.exists(os.path.join(d, "отчёт.html"))]
    site = job.sites[0] if job.sites else job.site
    if job.was_stopped:
        title = f"⏹ Проверка остановлена: {_e(site)}"
    elif getattr(job, "site_down", ""):
        title = (f"⚠️ Сайт перестал отвечать: {_e(site)} - {_e(job.site_down)}. "
                 "Обход прекращён, отчёт собран по тому, что успели")
    elif not ok:
        title = f"❌ Проверка не получилась: {_e(site)}"
    else:
        from .window.reports_list import read_check
        first = read_check(os.path.dirname(ok[0]), os.path.basename(ok[0])) or {}
        title = (f"🚨 Проверка закончена: {_e(site)} - что-то сломалось" if _broke(first.get("compare"))
                 else f"✅ Проверка закончена: {_e(site)}")
    parts = [title + (f"\nЗаняла: {took}" if took else "")]
    for i, d in enumerate(dirs):
        parts.append(_site_block(d, main=(i == 0), show_site=len(dirs) > 1))
    if not ok:
        errs = [ln for ln in job.lines if "шибка" in ln or "Traceback" in ln]
        tail = errs[-1] if errs else (job.lines[-1] if job.lines else "")
        if tail:
            parts.append("Последнее в журнале: " + _e(tail[:300]))
    if job.competitors_report and os.path.exists(job.competitors_report):
        parts.append("Сравнение с конкурентами готово.")
    return "\n\n".join(p for p in parts if p)


def notify_job(job):
    """Вызывается окном, когда проверка закончилась. Ошибки не мешают программе — только пишутся в журнал."""
    cur = _cfg()
    if not (cur.get("token") and cur.get("chat_id")) or not _opt(cur, "enabled"):
        return
    try:
        site = job.sites[0] if job.sites else job.site
        err = send(job_message(job), result_buttons(site) if job.sites else None)
        dirs = list(job.dirs) or ([job.out_dir] if job.out_dir else [])
        express = getattr(job, "express", False)
        pdf = os.path.join(dirs[0], "экспресс.pdf" if express else "аудит.pdf") if dirs else ""
        if not err and (_opt(cur, "pdf") or express) and pdf and os.path.exists(pdf):
            ferr = send_file(pdf, ("Экспресс-аудит (1 лист): " if express else "Аудит для клиента: ")
                             + (job.sites[0] if job.sites else job.site))
            if ferr:
                job.add("Аудит PDF в Telegram не отправился - " + ferr)
    except Exception as e:  # сообщение — не главное, проверку не роняем
        err = str(e)[:200]
    job.add("Сообщение в Telegram: " + ("не отправилось - " + err if err else "отправлено"))


# ---------- бот отвечает на команды и кнопки, пока окно программы открыто ----------

class Reply(str):
    """Ответ бота: текст (обычная строка) + кнопки под ним."""
    def __new__(cls, text, buttons=None):
        obj = super().__new__(cls, text)
        obj.buttons = buttons or []
        return obj


# меню внизу чата (постоянные кнопки вместо набора команд)
MENU = [["▶️ Проверить сайт", "📊 Что идёт"], ["📄 Последний итог", "👀 Мои сайты"], ["⏹ Стоп", "❓ Помощь"]]
MENU_CMD = {"▶️ Проверить сайт": "/check", "📊 Что идёт": "/status", "📄 Последний итог": "/last",
            "👀 Мои сайты": "/sites", "⏹ Стоп": "/stop", "❓ Помощь": "/help"}


def _host(url):
    from . import watch
    return watch._key(watch.norm_url(url) or url)


def _btn(label, action, url=""):
    data = f"{action}:{_host(url)}" if url else action
    return (label, data) if len(data.encode()) <= 64 else None


def _row(*buttons):
    return [b for b in buttons if b]


def _site_url(host):
    """Полный адрес сайта по домену из кнопки: как в наблюдении, иначе как в последней проверке."""
    from . import watch
    s = watch.find(host)
    if s:
        return s["url"]
    c = _last_check(host)
    return watch.norm_url(c["site"]) if c else watch.norm_url(host)


def _last_check(host=None):
    """Последняя готовая проверка (всех сайтов или одного)."""
    from .window import REPORTS
    from .window.reports_list import list_checks
    for c in list_checks(REPORTS):
        if host and c["key"] != host:
            continue
        if os.path.exists(os.path.join(REPORTS, c["folder"], "отчёт.html")):
            return dict(c, path=os.path.join(REPORTS, c["folder"]))
    return None


def result_buttons(url):
    """Кнопки под итогом проверки."""
    return [_row(_btn("📄 Аудит PDF", "pdf", url), _btn("🌐 Отчёт HTML", "html", url), _btn("📊 Excel", "xlsx", url)),
            _row(_btn("🔤 Семантика", "sem", url)),
            _row(_btn("🔁 Проверить ещё раз", "again", url), _btn("👀 Следить каждый час", "watch", url))]


def status_text(job):
    """Ответ на /status."""
    st = job.status()
    if not st["running"]:
        return Reply("Сейчас ничего не проверяется." + ("\nПоследняя: " + _e(st["site"]) if st.get("site") else ""),
                     [_row(("▶️ Проверить сайт", "ask"), ("📄 Последний итог", "last"))])
    from .duration import fmt
    lines = [f"🔄 Идёт проверка: {_e(st['site'])}", _e(st.get("step") or "запускаю")]
    if st.get("progress"):
        done, limit = st["progress"]
        lines.append(f"Страниц: {done} из {limit}")
    lines.append(f"Идёт уже: {fmt(st.get('elapsed') or 0)}")
    if (st.get("stuck") or 0) >= 300:
        lines.append(f"⚠️ Уже {fmt(st['stuck'])} не закончилась проверка ни одного адреса")
    elif st.get("idle_note") and st.get("pause_note"):
        lines.append(f"Новых страниц нет {st['idle_note']}, но работа идёт: {_e(st['pause_note'])}")
    elif st.get("idle_note"):
        lines.append(f"⚠️ Новых страниц нет уже {st['idle_note']}")
    return Reply("\n".join(lines), [_row(("🔄 Обновить", "status"), ("⏹ Остановить", "stop"))])


def last_text(host=None):
    """Ответ на /last: итог последней готовой проверки."""
    c = _last_check(host)
    if not c:
        return Reply("Готовых проверок пока нет.")
    return Reply(f"Последняя проверка: {_e(c['site'])}" + (f"\nЗакончена: {_e(c['finished'])}" if c["finished"] else "")
                 + "\n\n" + _site_block(c["path"], main=True, show_site=False), result_buttons(c["site"]))


HELP = ("Кнопки внизу чата - главное меню. Можно просто прислать адрес сайта - предложу, что с ним сделать.\n\n"
        "Команды:\n"
        "/check site.ru - проверить сайт (можно добавить число страниц: /check site.ru 2000)\n"
        "/express site.ru - экспресс-аудит: 300 страниц, итог - один лист PDF для потенциального клиента\n"
        "/stop - остановить проверку\n"
        "/status - что проверяется сейчас\n"
        "/last - итог последней проверки\n"
        "/sites - сайты под наблюдением\n"
        "/watch site.ru - следить за сайтом каждый час (тревога, если сломался)\n"
        "/unwatch site.ru - перестать следить\n"
        "/weekly site.ru пн 09:00 - проверять раз в неделю (/weekly site.ru выкл - отменить)\n"
        "/semantics site.ru - семантика: какие запросы ищут и какая страница нужна "
        "(/semantics site.ru заново - собрать снова, /semantics site.ru подробно - больше запросов, дольше)\n"
        "Работает, пока окно Clayler SEO открыто на компьютере.")
_starter = None  # запуск проверки: (адрес, страниц) → ошибка или "" — задаёт окно программы


def sites_text():
    from . import watch
    lst = watch.sites()
    if not lst:
        return Reply("Под наблюдением пока нет сайтов. Пришлите адрес сайта - предложу следить за ним.")
    lines, buttons = [], []
    for s in lst:
        m = watch.mon_state(s["url"])
        if not s.get("monitor"):
            mon = "выключен"
        elif not m:
            mon = "скоро первая проверка"
        else:
            mon = ("✅ в порядке" if m.get("ok") else "🚨 " + "; ".join(m.get("problems") or [])[:300]) \
                + f" (проверено {m['checked']})"
        lines.append(f"<b>{_e(s['url'])}</b>\nМониторинг: {_e(mon)}\nРаз в неделю: {watch.weekly_text(s.get('weekly'))}")
        h = _host(s["url"])
        buttons.append(_row(_btn(f"▶️ {h}", "again", s["url"]),
                            _btn("🔕 Не следить" if s.get("monitor") else "👀 Следить",
                                 "unwatch" if s.get("monitor") else "watch", s["url"])))
    return Reply("\n\n".join(lines), buttons)


def _start(url, pages=10000):
    err = _starter(url, pages) if _starter else "окно программы не запущено"
    if err:
        return Reply(f"❌ Не запустил: {_e(err)}", [_row(("📊 Что идёт", "status"))] if "уже идёт" in err else [])
    return Reply(f"▶️ Запустил проверку {_e(url)} (до {pages} страниц). Когда закончится, пришлю итог.",
                 [_row(("📊 Как идёт", "status"), ("⏹ Остановить", "stop"))])


def _watch_on(url):
    from . import watch
    s, err = watch.update(url, monitor=True)
    if err:
        return Reply(f"❌ {err}")
    return Reply(f"👀 Слежу за {_e(s['url'])}: раз в час проверяю главную и важные страницы, robots.txt и "
                 "сертификат. Если что-то сломается, напишу. Первая проверка - в течение пары минут.",
                 [_row(_btn("🗓 Ещё и раз в неделю", "weekly", s["url"]), _btn("🔕 Не следить", "unwatch", s["url"]))])


def _watch_off(url):
    from . import watch
    s = watch.find(url)
    if not s:
        return Reply("Такого сайта в наблюдении нет.")
    if s.get("weekly"):
        watch.update(s["url"], monitor=False)
    else:
        watch.remove(s["url"])
    return Reply(f"Больше не слежу за {_e(s['url'])}.", [_row(_btn("👀 Следить снова", "watch", s["url"]))])


def _weekly_on(url, weekly):
    from . import watch
    s, err = watch.update(url, weekly=weekly)
    if err:
        return Reply(f"❌ {err}")
    return Reply(f"🗓 {_e(s['url'])} буду проверять каждую неделю: {watch.weekly_text(weekly)}. Итог пришлю сюда. "
                 "Компьютер и окно программы в это время должны быть включены.\n"
                 f"Другой день или время: /weekly {_host(s['url'])} пт 18:00",
                 [_row(_btn("❌ Отменить расписание", "noweekly", s["url"]))])


def _weekly_off(url):
    from . import watch
    s = watch.find(url)
    if not s:
        return Reply("Такого сайта в наблюдении нет.")
    if s.get("monitor"):
        watch.update(s["url"], weekly=None)
    else:
        watch.remove(s["url"])
    return Reply(f"Проверка по расписанию для {_e(s['url'])} отменена.")


def _answer(text, job):
    from . import watch
    text = (text or "").strip()
    text = MENU_CMD.get(text, text)
    words = text.split()
    cmd = words[0].split("@")[0].lower() if words else ""
    arg = words[1] if len(words) > 1 else ""
    if cmd == "/status":
        return status_text(job)
    if cmd == "/last":
        return last_text()
    if cmd == "/check":
        if not arg:
            return Reply("Пришлите адрес сайта, например: gigas.su")
        url = watch.norm_url(arg)
        if not url:
            return Reply("Не понял адрес сайта.")
        return _start(url, int(words[2]) if len(words) > 2 and words[2].isdigit() else 10000)
    if cmd == "/express":
        if not arg:
            return Reply("Пришлите адрес сайта, например: /express gigas.su")
        url = watch.norm_url(arg)
        if not url:
            return Reply("Не понял адрес сайта.")
        r = _start(url, 300)
        if job.running:
            job.express = True  # по окончании пришлю экспресс.pdf
        return r
    if cmd == "/stop":
        if not job.status()["running"]:
            return Reply("Сейчас ничего не проверяется.")
        job.stop()
        return Reply("⏹ Останавливаю проверку. Отчёт по уже проверенным страницам соберётся и придёт сюда.")
    if cmd == "/sites":
        return sites_text()
    if cmd in ("/watch", "/unwatch"):
        if not arg:
            return Reply(f"Напишите адрес: {cmd} site.ru")
        return _watch_off(arg) if cmd == "/unwatch" else _watch_on(arg)
    if cmd == "/weekly":
        if not arg:
            return Reply("Напишите так: /weekly site.ru пн 09:00 (или /weekly site.ru выкл)")
        weekly, err = watch.parse_weekly(" ".join(words[2:]))
        if err:
            return Reply(err)
        return _weekly_on(arg, weekly) if weekly else _weekly_off(arg)
    if cmd in ("/semantics", "/sem"):
        if not arg:
            return Reply("Напишите адрес: /semantics site.ru")
        opts = {w.lower() for w in words[2:]}
        return semantics_reply(_host(arg), job, fresh=bool(opts & {"заново", "снова", "подробно"}), deep="подробно" in opts)
    if len(words) == 1 and not cmd.startswith("/") and watch.norm_url(cmd):
        # просто прислали адрес сайта — спросим, что с ним сделать
        url = watch.norm_url(cmd)
        return Reply(f"Что сделать с {_e(url)}?",
                     [_row(_btn("▶️ Проверить", "again", url), _btn("👀 Следить каждый час", "watch", url)),
                      _row(_btn("🗓 Раз в неделю (пн 09:00)", "weekly", url), _btn("📄 Последний итог", "last", url))])
    return Reply("Я присылаю итог, когда проверка сайта закончится.\n\n" + HELP)


def _on_button(data, job):
    """Нажата кнопка под сообщением. Возвращает ответ (Reply) или None, если ответ — файл."""
    from . import watch
    action, _, host = data.partition(":")
    if action == "status":
        return status_text(job)
    if action == "stop":
        return _answer("/stop", job)
    if action == "last":
        return last_text(host or None)
    if action == "sites":
        return sites_text()
    if action == "ask":
        return Reply("Пришлите адрес сайта, например: gigas.su")
    if not host:
        return Reply("Кнопка устарела.")
    url = _site_url(host)
    if action == "again":
        return _start(url, (watch.find(host) or {}).get("pages") or 10000)
    if action == "watch":
        return _watch_on(url)
    if action == "unwatch":
        return _watch_off(url)
    if action == "weekly":
        return _weekly_on(url, {"day": 0, "time": "09:00"})
    if action == "noweekly":
        return _weekly_off(url)
    if action == "mon":
        from .window import REPORTS
        state, _msg = watch.monitor(url, REPORTS, pause=0)
        return Reply(f"✅ {_e(url)} - всё в порядке ({state['pages']} стр.)" if state["ok"] else
                     f"🚨 {_e(url)} - всё ещё есть проблемы:\n" + "\n".join("• " + _e(p) for p in state["problems"]),
                     [] if state["ok"] else alert_buttons(url))
    if action in ("sem", "semnew"):
        return semantics_reply(host, job, fresh=action == "semnew")
    if action == "html":  # полный отчёт для клиента одним файлом
        c = _last_check(host)
        path = os.path.join(c["path"], "отчёт_для_клиента.html") if c else ""
        if not path or not os.path.exists(path):
            return Reply(f"Отчёта для клиента для {_e(host)} пока нет. Он появляется после проверки; у старых "
                         f"проверок - после «Ещё → Обновить отчёт» в окне программы.")
        err = send_file(path, "Полный отчёт для клиента (открывается в браузере): " + c["site"],
                        name=f"SEO-аудит {_host(c['site'])}.html")
        return Reply(f"Не отправился файл: {_e(err)}") if err else None
    if action in ("pdf", "xlsx"):
        c = _last_check(host)
        name = "аудит.pdf" if action == "pdf" else "отчёт.xlsx"
        path = os.path.join(c["path"], name) if c else ""
        if not path or not os.path.exists(path):
            return Reply(f"Файла {name} для {_e(host)} нет. Он появляется после проверки"
                         + (" (PDF - если в программе включено создание аудита)." if action == "pdf" else "."))
        err = send_file(path, ("Аудит для клиента: " if action == "pdf" else "Полный отчёт в Excel: ") + c["site"])
        return Reply(f"Не отправился файл: {_e(err)}") if err else None
    return Reply("Кнопка устарела.")


# ---------- семантика ----------

def _sem_data(folder):
    """Семантика с решениями человека - те же группы и числа, что на странице «Семантика» в окне."""
    from .semantics import export as SX, decisions as D, plan
    raw = SX.load(folder)
    return plan.enrich(D.apply(raw, folder), folder) if raw else None


def _sem_xlsx(folder, data):
    """«семантика с решениями.xlsx», как кнопка Excel в окне; не записался (открыт в Excel) - файл сбора."""
    from .semantics import export as SX, xlsx_dec
    try:
        return xlsx_dec.write(folder, data)
    except Exception:
        path = os.path.join(folder, SX.XLSX_NAME)
        return path if os.path.exists(path) else ""


def semantics_text(data):
    """Короткий итог семантики для сообщения (data - с решениями, _sem_data)."""
    from .semantics.export import summary
    from .semantics import labels as L
    from .fmt import num
    k = summary(data)
    create = sorted((g for g in data["groups"] if g["kind"] == "create"), key=lambda g: -g["score"])[:5]
    rivals = f" (с {_e(', '.join(data['competitors']))})" if data["competitors"] else ""
    lines = [f"🔤 <b>Семантика {_e(data['host'])}</b>{rivals}",
             f"{num(data['total'])} {L.plural(data['total'], 'query')} в {num(len(data['groups']))} группах, "
             f"отсеяно {num(sum(len(v) for v in (data.get('dropped') or {}).values()))}"
             + (f", город {_e(data['city'])}" if data.get("city") else ""),
             f"✅ {L.count('page', k['page'])}", f"🛠 {L.count('create', k['create'])}",
             f"➖ {L.count('absent', k['absent'])}"]
    nfix = sum(1 for g in data["groups"] if g.get("a") and g["a"]["problems"])
    ncann = len(data.get("cannibal") or [])
    if nfix or ncann:
        lines.append(f"📝 {L.count('fix', nfix)} (ТЗ в файле)")
        if ncann:
            lines.append(f"⚠️ Страницы мешают друг другу: {ncann}")
    geo = (data.get("geo") or {}).get("checks") or []
    if geo:
        bad = [c["name"] for c in geo if c["ok"] is False]
        nq = sum(1 for g in data["groups"] if g.get("faq"))
        lines.append(f"🤖 Готовность к нейросетям: {len(geo) - len(bad)} из {len(geo)}"
                     + (f" (поправить: {_e(', '.join(bad))})" if bad else "")
                     + (f"; вопросы для ответов - для {nq} страниц" if nq else ""))
    flt = sorted((f for g in data["groups"] for f in g.get("f") or [] if f["products"] >= 3), key=lambda f: -f["queries"])
    if flt:
        lines.append(f"🏷 Страниц-фильтров с товарами: {len(flt)}, например: "
                     + ", ".join(_e(f["name"]) for f in flt[:3]))
    if create:
        lines.append("\nГлавное создать: " + ", ".join(_e(g["name"]) for g in create))
    lines.append(f"\nСобрано {_e(data['made'])}. Всё по группам - в файле Excel и в программе: «Семантика».")
    return "\n".join(lines)


def _sem_folder(host):
    c = _last_check(host)
    return c["path"] if c else ""


def semantics_reply(host, job, fresh=False, deep=False):
    """/semantics site.ru и кнопка «Семантика»: готовая — итог и Excel; нет или «заново» — собрать."""
    folder = _sem_folder(host)
    if not folder:
        return Reply(f"Проверок {_e(host)} нет. Сначала проверьте сайт: /check {_e(host)}")
    data = _sem_data(folder)
    if data and not fresh:
        err = send(semantics_text(data), [_row(_btn("🔁 Собрать заново", "semnew", host))])
        xlsx = _sem_xlsx(folder, data)
        if not err and xlsx:
            err = send_file(xlsx, "Семантика: " + data["host"])
        return Reply(f"Не отправилось: {_e(err)}") if err else None
    if job.status()["running"]:
        return Reply("Сейчас идёт проверка. Семантику соберу, когда она закончится - нажмите кнопку ещё раз.",
                     [_row(("📊 Что идёт", "status"))])
    rivals = [f for f in (_sem_folder(h) for h in (data or {}).get("competitors") or []) if f]  # как в прошлый раз
    if not job.start([], [], semantics_folders=[folder] + rivals[:5], label="семантика " + os.path.basename(folder),
                     deep=deep):   # другая проверка успела начаться (очередь, наблюдение)
        return Reply("Сейчас идёт проверка. Семантику соберу, когда она закончится - нажмите кнопку ещё раз.",
                     [_row(("📊 Что идёт", "status"))])
    with_rivals = f" вместе с {_e(', '.join(data['competitors']))}" if rivals else ""
    long = "15–30 минут (подробно)" if deep else "несколько минут"
    return Reply(f"🔤 Собираю семантику {_e(host)}{with_rivals}. Это {long}, потом пришлю итог и файл Excel.")


def notify_semantics(job):
    """Окно: сбор семантики закончился — итог и Excel в Telegram (если бот настроен)."""
    cur = _cfg()
    if not (cur.get("token") and cur.get("chat_id")) or not _opt(cur, "enabled"):
        return
    data = _sem_data(job.semantics_dir)
    if not data:
        err = send("❌ Семантику собрать не получилось. Подробности - в журнале в окне программы.")
    else:
        err = send(semantics_text(data))
        xlsx = _sem_xlsx(job.semantics_dir, data)
        if not err and xlsx:
            err = send_file(xlsx, "Семантика: " + data["host"])
    job.add("Семантика в Telegram: " + ("не отправилась - " + err if err else "отправлена"))


def alert_buttons(url):
    return [_row(_btn("🔁 Перепроверить", "mon", url), _btn("🔕 Не следить", "unwatch", url))]


def _loop(job):
    offset, warned_for, bot = None, None, None
    while True:
        cur = _cfg()
        if not (cur.get("token") and cur.get("chat_id")):
            time.sleep(10)
            continue
        if bot != cur["token"]:  # новый бот (или первый запуск): старые сообщения пропускаем, отвечаем на новые
            try:
                old = _call(_token(), "getUpdates", {"offset": -1}, timeout=15)
                offset = old[-1]["update_id"] + 1 if old else None
                bot = cur["token"]
                _set_commands(_token())
            except Exception as e:
                _mark(False, e)
                time.sleep(30)
                continue
        # застряла ли проверка: больше 15 минут не закончился ни один адрес. Просто «нет новых страниц» —
        # не повод: в это время могут проверяться фото и ссылки (zoozavr.ru: тревога при идущей работе)
        try:
            st = job.status()
            if st["running"] and _opt(cur, "stuck") and _opt(cur, "enabled") and st.get("stuck", 0) > STUCK_SECONDS \
                    and warned_for != job.started:
                warned_for = job.started
                from .duration import fmt
                send(f"⚠️ Проверка {_e(st['site'])} застряла: уже {fmt(st['stuck'])} не закончилась "
                     "проверка ни одного адреса.\n"
                     "Сайт мог перестать отвечать или начал блокировать проверку. Посмотрите окно программы.",
                     [_row(("📊 Как идёт", "status"), ("⏹ Остановить", "stop"))])
        except Exception:
            pass
        try:
            fields = {"timeout": 25, "allowed_updates": '["message","callback_query"]'}
            if offset is not None:
                fields["offset"] = offset
            updates = _call(_token(), "getUpdates", fields, timeout=35)
            _mark(True)
        except Exception as e:
            _mark(False, e)
            time.sleep(30)
            continue
        for u in updates or []:
            offset = u["update_id"] + 1
            try:
                if u.get("callback_query"):
                    q = u["callback_query"]
                    if ((q.get("message") or {}).get("chat") or {}).get("id") != cur.get("chat_id"):
                        continue  # чужим бот не отвечает
                    try:
                        _call(_token(), "answerCallbackQuery", {"callback_query_id": q["id"]}, timeout=10)
                    except RuntimeError:
                        pass
                    r = _on_button(q.get("data") or "", job)
                    if r is not None:
                        send(r, r.buttons)
                    continue
                m = u.get("message") or {}
                if (m.get("chat") or {}).get("id") != cur.get("chat_id"):
                    continue
                r = _answer(m.get("text"), job)
                # меню внизу чата показываем с подсказкой (приветствие, /help), остальное — с кнопками под ответом
                send(r, r.buttons, menu=not r.buttons and r.startswith("Я присылаю итог"))
            except Exception:
                pass


def send_alert(text, url=None):
    """Сообщение от наблюдения (расписание, мониторинг): если бот настроен. url — кнопки под тревогой."""
    cur = _cfg()
    if cur.get("token") and cur.get("chat_id"):
        send(text, alert_buttons(url) if url and text.startswith("🚨") else None)


def start_bot(job, starter=None):
    """Запускается окном программы один раз. starter(адрес, страниц) — запуск проверки по команде /check."""
    global _starter
    _starter = starter
    threading.Thread(target=_loop, args=(job,), daemon=True).start()
