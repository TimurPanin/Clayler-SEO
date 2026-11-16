"""Очередь сайтов: список сайтов проверяется по одному, сам, без человека (например, на ночь).

Человек вставляет список (или загружает готовый файл из папки «очередь»), задаёт лимит страниц на сайт и жмёт
«Запустить». Пока окно программы открыто, очередь каждые несколько секунд смотрит: свободна ли программа - и
запускает следующий сайт обычной проверкой (как кнопка «Начать проверку»: та же паутина и журнал в окне).

- Сайт, который не открылся, закрыт от проверки или упал, помечается и пропускается; очередь идёт дальше,
  в Telegram приходит короткое сообщение. Когда очередь кончилась, приходит итог. Про каждый удачный сайт
  отдельное сообщение не шлётся (их могут быть десятки за ночь).
- «Пауза» - текущий сайт доделывается, следующий не начинается. «Остановить» - текущий сайт останавливается
  (отчёт собирается по тому, что успели), очередь на паузе; при продолжении этот сайт идёт с того же места.
- Очередь хранится в «очередь.json» в папке «data»: переживает перезапуск. Сайт, прерванный закрытием
  программы, после запуска продолжается с того же места (--continue).
- Пока идёт другая проверка (запущенная руками, ботом или по расписанию), очередь ждёт.
- Галочка «После проверки собрать семантику» (10.10): после удачного сайта очередь сразу собирает его семантику
  быстрым сбором - главная и разделы, без Вордстата (лимит 1 000 фраз в сутки не тратится, crawl.py --light).
  Пары «похоже на синонимы» из неё копятся в «Словарь → Ждут подтверждения». Строка очереди «семантика» (kind
  "sem") - сбор семантики готовой проверки, её ставит кнопка «Собрать семантику» в «Отчётах» для выбранных сайтов.
- Оставшееся время - по тому, сколько шли и сколько страниц набрали уже проверенные сайты (eta), история
  очередей (страницы и время по каждому сайту) - в «очередь история.json».
"""
import os
import re
import sqlite3
import json
import threading
import time

from . import jsonfile, paths
from .fmt import plural as _plural

FILE = paths.data("очередь.json")
HISTORY = paths.data("очередь история.json")
HISTORY_RUNS = 30
_HISTORY_DEFAULT = HISTORY
LISTS = paths.data("списки сайтов")   # готовые списки сайтов (.txt), кнопки «Загрузить» в окне
DEFAULT_PAGES = 5000
TICK = 5
BIG_WORDS = ("большой", "big")   # слово после адреса (не в заметке после #)

_LOCK = threading.RLock()
_current = {"url": "", "stopping": False, "sem": False}   # что очередь запустила в этом запуске программы


def _host(url):
    from urllib.parse import urlsplit
    return (urlsplit(url).netloc or url).lower()


def _key(url):
    h = _host(url)
    return h[4:] if h.startswith("www.") else h


def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("pages", DEFAULT_PAGES)
    d.setdefault("paused", True)
    d.setdefault("items", [])
    d.setdefault("sem_after", False)
    return d


def save(d):
    jsonfile.save(FILE, d, indent=1)


def parse(text):
    """Строки «site.ru», «https://site.ru/ 2000», «site.ru большой # заметка» -> [{url, limit, big, note}].
    Число после адреса - свой лимит страниц для этого сайта, слово «большой» - пометка «очень большой сайт»."""
    out = []
    for line in (text or "").splitlines():
        line, _, note = line.partition("#")
        parts = line.replace(",", " ").replace(";", " ").split()
        if not parts:
            continue
        url = parts[0].strip()
        if not re.match(r"^(https?://)?(localhost|[\w.-]+\.[a-zа-яё]{2,}|\d{1,3}(\.\d{1,3}){3})(:\d+)?(/|$)", url, re.I):
            continue
        if "://" not in url:
            url = "https://" + url
        if url.count("/") == 2:
            url += "/"
        rest = " ".join(parts[1:]).lower()
        m = re.search(r"\b(\d[\d ]*)\b", rest)
        pages = int(m.group(1).replace(" ", "")) if m else None
        out.append({"url": url, "limit": pages if pages and pages > 0 else None,
                    "big": any(w in rest for w in BIG_WORDS), "note": note.strip()})
    return out


def add(text, pages=None):
    """Добавить сайты в конец очереди. Сайт, который уже ждёт в очереди, второй раз не добавляется."""
    new = parse(text)
    if not new:
        return 0, "Не нашёл адресов сайтов. Пример: site.ru или https://site.ru/"
    with _LOCK:
        d = load()
        if pages:
            d["pages"] = max(1, int(pages))
        have = {_key(i["url"]) for i in d["items"] if i["state"] in ("wait", "run") and i.get("kind") != "sem"}
        n = 0
        for x in new:
            k = _key(x["url"])
            if k in have:
                continue
            have.add(k)
            d["items"].append(dict(x, state="wait", added=time.time()))
            n += 1
        save(d)
    return n, ""


def add_sem(checks):
    """«Собрать семантику» для выбранных в «Отчётах»: [(папка проверки, адрес сайта)] - в конец очереди строками
    «семантика». Быстрый сбор без Вордстата; сайт, который уже ждёт семантику, второй раз не ставится."""
    with _LOCK:
        d = load()
        have = {_key(i["url"]) for i in d["items"] if i["state"] in ("wait", "run") and i.get("kind") == "sem"}
        n = 0
        for folder, url in checks:
            k = _key(url)
            if not folder or k in have:
                continue
            have.add(k)
            d["items"].append({"url": url, "kind": "sem", "folder": folder, "state": "wait", "added": time.time(),
                               "note": "", "limit": None, "big": False})
            n += 1
        save(d)
    return n


def ready_lists():
    """Готовые списки в папке «очередь»: [{name, file, count}]."""
    out = []
    if os.path.isdir(LISTS):
        for name in sorted(os.listdir(LISTS)):
            if name.lower().endswith(".txt"):
                with open(os.path.join(LISTS, name), encoding="utf-8") as f:
                    n = len(parse(f.read()))
                out.append({"name": os.path.splitext(name)[0], "file": name, "count": n})
    return out


def add_list(file, pages=None):
    path = os.path.join(LISTS, os.path.basename(file or ""))
    if not os.path.isfile(path):
        return 0, "Нет такого списка."
    with open(path, encoding="utf-8") as f:
        return add(f.read(), pages)


def _find(d, url, kind=None):
    for i in d["items"]:
        if i["url"] == url and (i.get("kind") or "") == (kind or ""):
            return i
    return None


def _waiting(d):
    """Есть что делать: сайт ждёт проверки или готовый сайт ждёт семантику."""
    return any(i["state"] == "wait" or i.get("sem") == "wait" for i in d["items"])


def action(act, data, job=None):
    """Кнопки окна. Возвращает текст ошибки или ""."""
    with _LOCK:
        d = load()
        if act == "pages":
            d["pages"] = max(1, int(data.get("pages") or DEFAULT_PAGES))
        elif act == "start":
            if not _waiting(d):
                return "В очереди нет сайтов, которые ждут проверки."
            if d.get("notified") or not d.get("began"):   # новый заход (прошлый закончился) - итог считать с этого места
                d["began"] = time.time()
            d.update(paused=False, notified=False)
        elif act == "pause":
            d["paused"] = True
        elif act == "stop":
            d["paused"] = True
            if job is not None and _current["url"] and job.running:
                _current["stopping"] = "stop"
                job.stop()
        elif act == "skip":   # «Пропустить»: текущий сайт останавливается (отчёт по тому, что успели), очередь идёт дальше
            if not (job is not None and _current["url"] and job.running):
                return "Сейчас очередь ничего не проверяет."
            _current["stopping"] = "skip"
            d["paused"] = False   # и после «Остановить» тоже: пропустить - значит идти дальше
            job.stop()
        elif act == "sem_after":   # галочка «После проверки собрать семантику»
            d["sem_after"] = bool(data.get("on"))
        elif act in ("remove", "retry", "up", "sem_retry"):
            i = _find(d, data.get("url"), data.get("kind"))
            if not i:
                return "Такого сайта в очереди нет."
            if i["state"] == "run" or i.get("sem") == "run":
                return "Этот сайт сейчас проверяется. Сначала остановите очередь."
            if act == "sem_retry":
                if i["state"] != "done" or not i.get("folder"):
                    return "Семантику можно собрать только у готового сайта."
                i.update(sem="wait", sem_reason="")
                save(d)
                return ""
            if act == "remove":
                d["items"].remove(i)
            elif act == "retry":
                i.update(state="wait", reason="", finished=0)
                if i.get("kind") != "sem":
                    i.pop("sem", None)
                d["items"].remove(i)   # повторить - в конец очереди
                d["items"].append(i)
            else:   # «Следующим»: поставить первым среди ждущих
                d["items"].remove(i)
                pos = next((n for n, x in enumerate(d["items"]) if x["state"] == "wait"), len(d["items"]))
                d["items"].insert(pos, i)
        elif act == "clear_done":
            d["items"] = [i for i in d["items"] if i["state"] in ("wait", "run")]
        elif act == "clear_all":
            d["items"] = [i for i in d["items"] if i["state"] == "run" or i.get("sem") == "run"]
            d["paused"] = True
        else:
            return "нет такого действия"
        save(d)
    return ""


def status(job=None):
    d = load()
    items = d["items"]
    cnt = {s: sum(1 for i in items if i["state"] == s) for s in ("wait", "run", "done", "fail")}
    cnt["sem_wait"] = sum(1 for i in items if i.get("sem") in ("wait", "run"))
    try:
        _hist_seed(d)
    except OSError:
        pass
    other = bool(job is not None and job.running and not _current["url"])
    return {"pages": d["pages"], "paused": d["paused"], "items": items, "counts": cnt, "other_job": other,
            "lists": ready_lists(), "current": _current["url"], "sem_after": d["sem_after"],
            "eta": eta(d, job), "history": history_view()}


# ---------- сколько ещё ждать

def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _finished_runs(d):
    """Законченные сайты этой очереди и прошлых (из истории): для оценки времени."""
    seen, out = set(), []
    for i in list(d["items"]) + [x for r in _hist_load().get("runs") or [] for x in r.get("items") or []]:
        k = (i.get("url"), i.get("kind") or "", i.get("finished"))
        if k in seen or not i.get("finished"):
            continue
        seen.add(k)
        out.append(i)
    return out


def eta(d, job=None):
    """Оценка, сколько ещё будет идти очередь: {"seconds", "per_site", ...} или None, пока не с чем сравнить.
    Раньше прогноза не было, а на глаз выходило далеко от дела: очередь 07.10-09.10 - в среднем 49 мин на сайт
    при лимите 10 000 (от 4 мин до 2 ч 16 мин). Время сайта не пропорционально страницам: у маленького сайта
    свои 10-15 минут на начало и конец (robots, sitemap, скорость, отчёт). Поэтому по уже проверенным сайтам -
    прямая «время = начало + секунды × страницы», а страниц у следующего сайта - сколько в среднем набирали
    проверенные при таком лимите (сайт, упёршийся в свой лимит, считается не меньше лимита). Семантика - по
    среднему времени сбора."""
    fin = _finished_runs(d)
    crawl = [i for i in fin if i.get("kind") != "sem" and i.get("state") == "done" and i.get("pages") and i.get("took")]
    if not crawl:
        return None
    xs, ys = [i["pages"] for i in crawl], [i["took"] for i in crawl]
    rate = sum(ys) / sum(xs)
    base = 0.0
    if len(crawl) >= 3 and max(xs) > min(xs):
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        if b > 0 and my - b * mx > 0:
            rate, base = b, my - b * mx

    def pages_at(limit):
        out = []
        for i in crawl:
            cap = i.get("pages_limit") or limit
            out.append(min(limit, cap) if i["pages"] >= cap else min(limit, i["pages"]))
        return sum(out) / len(out)
    share = pages_at(d["pages"]) / max(1, d["pages"])
    fails = [i["took"] for i in fin if i.get("kind") != "sem" and i.get("state") == "fail" and i.get("took")]
    fail_share = (len(fails) / (len(fails) + len(crawl)))
    fail_took = _median(fails) or 0
    sems = [i["sem_took"] for i in fin if i.get("sem_took")] + [i["took"] for i in fin if i.get("kind") == "sem"
                                                                and i.get("state") == "done" and i.get("took")]
    sem_took = _median(sems) or 300

    def one(limit):
        ok = base + rate * pages_at(limit)
        return ok * (1 - fail_share) + fail_took * fail_share

    total = 0.0
    for i in d["items"]:
        limit = i.get("limit") or d["pages"]
        if i["state"] == "wait":
            total += sem_took if i.get("kind") == "sem" else one(limit) + (sem_took if d["sem_after"] else 0)
        elif i.get("sem") == "wait":
            total += sem_took
        elif i["state"] == "run" or i.get("sem") == "run":
            ran = time.time() - (i.get("sem_started") if i.get("sem") == "run" else i.get("started") or time.time())
            whole = sem_took if (i.get("sem") == "run" or i.get("kind") == "sem") else one(i.get("pages_limit") or limit)
            pct = None
            if job is not None and job.running and i["state"] == "run" and i.get("kind") != "sem":
                try:
                    pct = (job.status() or {}).get("overall")
                except Exception:
                    pct = None
            if pct and pct >= 10:   # своя доля сделанного у текущего сайта точнее средней
                whole = ran / (pct / 100)
            total += max(60, whole - ran) + (sem_took if d["sem_after"] and i["state"] == "run" else 0)
    return {"seconds": round(total), "per_site": round(one(d["pages"])), "sites": len(crawl),
            "rate": round(rate, 2), "base": round(base), "share": round(share, 2)}


# ---------- история очередей

def _hist_file():
    """Файл истории. Если очередь перенесли в другую папку (автотест подменяет FILE), а историю нет - история рядом
    с очередью: автотест очереди 30 раз записал свои прогоны в настоящую историю и испортил оценку времени."""
    if HISTORY == _HISTORY_DEFAULT and os.path.dirname(os.path.abspath(FILE)) != os.path.abspath(paths.DATA):
        return os.path.join(os.path.dirname(os.path.abspath(FILE)), "очередь история.json")
    return HISTORY


def _hist_load():
    try:
        with open(_hist_file(), encoding="utf-8") as f:
            h = json.load(f)
        return h if isinstance(h, dict) else {}
    except (OSError, ValueError):
        return {}


def _hist_add(d, i):
    """Законченный сайт - в историю очереди, которая сейчас идёт (её начало - d["began"]). Кнопка «Убрать всё»
    чистит очередь, а история остаётся."""
    began = d.get("began") or i.get("started") or time.time()
    h = _hist_load()
    runs = h.setdefault("runs", [])
    run = next((r for r in runs if r.get("began") == began), None)
    if not run:
        run = {"began": began, "items": []}
        runs.append(run)
    keep = ("url", "kind", "state", "reason", "pages", "pages_limit", "took", "finished", "folder", "sem", "sem_took",
            "sem_reason", "sem_queries")
    row = {k: i.get(k) for k in keep if i.get(k) not in (None, "")}
    run["items"] = [x for x in run["items"] if not (x.get("url") == i["url"] and (x.get("kind") or "") == (i.get("kind") or ""))]
    run["items"].append(row)
    run["ended"] = max(run.get("ended") or 0, i.get("finished") or time.time())
    h["runs"] = sorted(runs, key=lambda r: r.get("began") or 0)[-HISTORY_RUNS:]
    jsonfile.save(_hist_file(), h, indent=0)


def _hist_seed(d):
    """Истории ещё нет (очередь шла до 10.10): законченные сайты текущей очереди - первой записью."""
    if os.path.exists(_hist_file()):
        return
    done = [i for i in d["items"] if i.get("finished")]
    if not done:
        return
    began = d.get("began") or min(i.get("started") or i["finished"] for i in done)
    for i in sorted(done, key=lambda x: x["finished"]):
        _hist_add(dict(d, began=began), i)


def history_view():
    """Прошлые и текущая очередь: новые сверху, по каждому сайту страницы и время."""
    out = []
    for r in reversed(_hist_load().get("runs") or []):
        items = r.get("items") or []
        crawl = [x for x in items if x.get("kind") != "sem"]
        out.append({"began": r.get("began"), "ended": r.get("ended"), "items": items,
                    "done": sum(1 for x in crawl if x.get("state") == "done"),
                    "fail": sum(1 for x in crawl if x.get("state") == "fail"),
                    "sem": sum(1 for x in items if x.get("sem") == "done" or (x.get("kind") == "sem" and x.get("state") == "done")),
                    "pages": sum(x.get("pages") or 0 for x in crawl),
                    "took": sum((x.get("took") or 0) + (x.get("sem_took") or 0) for x in items)})
    return out


# ---------- итог одного сайта ----------

def _crash_line(lines):
    """Последняя строка трассировки Python («KeyError: 'x'») — сама ошибка. Раньше в причину попадала первая
    строка «Traceback (most recent call last):», и по klimat-primer (08.10, упал за 6 с) понять ничего было нельзя."""
    lines = list(lines)
    at = max((i for i, ln in enumerate(lines) if ln.startswith("Traceback")), default=-1)
    if at < 0:
        return ""
    for ln in reversed(lines[at + 1:]):
        if ln.strip() and not ln.startswith((" ", "\t")):
            return ln.strip()
    return "Traceback"


def _save_crash_log(lines, folder):
    """Журнал упавшей проверки — в «очередь\\сбои\\сайт_время.txt», чтобы потом найти причину."""
    try:
        d = os.path.join(LISTS, "сбои")
        os.makedirs(d, exist_ok=True)
        name = (os.path.basename(folder) if folder else time.strftime("%Y-%m-%d_%H-%M-%S")) + ".txt"
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write("\n".join(ln.rstrip("\n") for ln in list(lines)[-300:]) + "\n")
    except OSError:
        pass


def _outcome(job):
    """(состояние, причина, страниц, папка) по законченной проверке."""
    folder = job.out_dir or ""
    rep = folder and os.path.exists(os.path.join(folder, "отчёт.html"))
    summary, first, html_ok, robots_ok, access = {}, None, 0, False, {}
    if folder and os.path.exists(os.path.join(folder, "crawl.db")):
        try:
            con = sqlite3.connect(f"file:{os.path.join(folder, 'crawl.db')}?mode=ro", uri=True, timeout=2)
            try:
                row = con.execute("SELECT value FROM meta WHERE key='summary'").fetchone()
                summary = json.loads(row[0]) if row else {}
                first = con.execute("SELECT status, error FROM pages ORDER BY rowid LIMIT 1").fetchone()
                html_ok = con.execute("SELECT COUNT(*) FROM pages WHERE status BETWEEN 200 AND 299 "
                                      "AND content_type LIKE '%html%'").fetchone()[0]
                row = con.execute("SELECT value FROM meta WHERE key='robots'").fetchone()
                robots_ok = any((v or {}).get("status") for v in (json.loads(row[0]) if row else {}).values())
                row = con.execute("SELECT value FROM meta WHERE key='access'").fetchone()
                access = json.loads(row[0]) if row else {}   # почему главная не открылась (crawler/access.py)
            finally:
                con.close()
        except Exception:
            pass
    pages = summary.get("pages")
    if pages is None and job.site_pages:
        pages = job.site_pages[-1][1]
    why = ""
    if first:
        st, err = first
        why = f"сайт ответил кодом {st}" if st and st >= 400 else (f"ошибка: {err[:120]}" if err else "")
        if err and err.startswith("Соединение сброшено") and robots_ok:
            # kamen-primer.ru 09.10: robots.txt открылся, главная - сброс за 0,13 с, через сутки открывается
            why = ("robots.txt открылся, а главную сайт не отдал - соединение сброшено даже через минуту. "
                   "Похоже на защиту сайта от частых запросов или на блокировку адреса VPN, попробуйте позже")
        from .access_check import short
        if short(access) and access.get("kind") != "bots_blocked":
            why = short(access)   # «соединение режут по дороге на шаге https (…), попробуйте через VPN»
    if not rep:
        crash = _crash_line(job.lines)
        if crash:
            _save_crash_log(job.lines, folder)
            return "fail", f"сбой программы: {crash[:150]} (журнал - в «очередь\\сбои»)", pages, folder
        errs = [ln.strip() for ln in job.lines if "шибка" in ln or "Не понял адрес" in ln]
        tail = errs[-1] if errs else (job.lines[-1].strip() if job.lines else "")
        return "fail", why or ("проверка не закончилась" + (f": {tail[:150]}" if tail else "")), pages, folder
    if not html_ok:   # отчёт есть, но ни одной рабочей страницы: сайт не открылся или не пустил
        return "fail", "не открылся или закрыт от проверки" + (f" ({why})" if why else ""), pages, folder
    return "done", "", pages, folder


def _sem_outcome(job, folder):
    """(состояние, причина, запросов) по законченному сбору семантики очереди."""
    path = os.path.join(folder, "семантика.json")
    try:
        fresh = os.path.getmtime(path) >= (job.started or 0) - 1
    except OSError:
        fresh = False
    if fresh:
        try:
            with open(path, encoding="utf-8") as f:
                sem = json.load(f)
            return "done", "", sum(len(g.get("q") or []) for g in sem.get("groups") or [])
        except (OSError, ValueError):
            pass
    crash = _crash_line(job.lines)
    if crash:
        _save_crash_log(job.lines, folder)
        return "fail", f"сбой программы: {crash[:150]} (журнал - в «очередь\\сбои»)", None
    errs = [ln.strip() for ln in job.lines if "шибка" in ln or "не собран" in ln.lower()]
    return "fail", (errs[-1][:150] if errs else "семантика не собралась"), None


def _sem_finished(job, d, url, stopping):
    i = next((x for x in d["items"] if x["url"] == url and (x.get("sem") == "run" or
                                                          (x.get("kind") == "sem" and x["state"] == "run"))), None)
    if not i:
        return
    own = i.get("kind") == "sem"   # строка «семантика», а не семантика после проверки сайта
    folder = os.path.join(_reports(), i.get("folder") or "")
    took = round((job.finished or time.time()) - job.started)
    if job.was_stopped and stopping != "skip":   # остановили: очередь на паузу, семантика соберётся при продолжении
        i.update(state="wait") if own else i.update(sem="wait")
        i["sem_reason" if not own else "reason"] = "остановлено вручную, соберётся заново"
        d["paused"] = True
        save(d)
        return
    if job.was_stopped:
        state, why, nq = "fail", "пропущено вручную", None
    else:
        state, why, nq = _sem_outcome(job, folder)
    if own:
        i.update(state=state, reason=why, finished=time.time(), took=took, sem_queries=nq)
    else:
        i.update(sem=state, sem_reason=why, sem_took=took, sem_queries=nq)
    save(d)
    _hist_add(d, i)
    job.add(f"Очередь сайтов: семантика {_host(url)} - " + ("готово" if state == "done" else "не собрана, " + why))


def _reports():
    from .window import REPORTS
    return REPORTS


def on_finished(job):
    """Окно (job.py) зовёт это, когда закончилась проверка (или сбор семантики), запущенная очередью."""
    with _LOCK:   # под замком: иначе ход очереди увидит «идёт» без хозяина и сочтёт сайт прерванным
        url, sem = _current["url"], _current["sem"]
        stopping, _current["url"], _current["stopping"], _current["sem"] = _current["stopping"], "", False, False
        if not url:
            return
        d = load()
        if sem:
            _sem_finished(job, d, url, stopping)
            return
        i = _find(d, url)
        if not i:
            return
        if job.was_stopped and stopping == "skip":
            state, why, pages, folder = _outcome(job)
            i.update(state="fail", reason="пропущен вручную" + (", отчёт по тому, что успели" if state == "done" else ""),
                     pages=pages, folder=os.path.basename(folder) if state == "done" and folder else "",
                     finished=time.time(), took=round((job.finished or time.time()) - job.started), resume=False)
            save(d)
            _hist_add(d, i)
            job.add("Очередь сайтов: сайт пропущен, иду дальше.")
            return
        if job.was_stopped:   # остановили руками (в очереди, в окне или ботом): очередь на паузу, сайт - сначала
            i.update(state="wait", resume=True, reason="остановлен вручную, продолжится с того же места")
            d["paused"] = True
            save(d)
            if not stopping:
                job.add("Очередь сайтов на паузе: проверку остановили.")
            return
        state, why, pages, folder = _outcome(job)
        if getattr(job, "site_down", "") and state == "done":   # упал посреди обхода: отчёт есть, но неполный
            state, why = "fail", f"сайт перестал отвечать ({job.site_down}), отчёт по тому, что успели"
        i.update(state=state, reason=why, pages=pages, folder=os.path.basename(folder) if folder else "",
                 finished=time.time(), took=round((job.finished or time.time()) - job.started), resume=False)
        if state == "done" and d["sem_after"] and i.get("folder"):   # «После проверки собрать семантику»
            i.update(sem="wait", sem_reason="")
        save(d)
        _hist_add(d, i)
        left = sum(1 for x in d["items"] if x["state"] == "wait")
    job.add(f"Очередь сайтов: {_host(url)} - " + ("готово" if state == "done" else "пропущен, " + why)
            + f". Осталось: {left}")
    if state == "fail":
        _tg(f"⚠️ Очередь: <b>{_esc(_host(url))}</b> пропущен - {_esc(why)}.\n"
            + (f"Иду дальше, осталось {left} {_plural(left, 'сайт', 'сайта', 'сайтов')}." if left else "Это был последний сайт."))


def _esc(s):
    import html
    return html.escape(str(s or ""), quote=False)


def _tg(text):
    try:   # то же - плашкой в окне программы (window/events.py)
        from .window import events
        events.from_telegram(text)
    except Exception:
        pass
    try:
        from . import telegram
        cur = telegram._cfg()
        if cur.get("token") and cur.get("chat_id") and telegram._opt(cur, "enabled"):
            telegram.send(text)
    except Exception:
        pass


def _final_message(d):
    from .duration import fmt
    items = [i for i in d["items"] if i.get("finished") and i["finished"] >= (d.get("began") or 0) - 1]
    sems = [i for i in items if i.get("kind") == "sem"]
    items = [i for i in items if i.get("kind") != "sem"]
    done = [i for i in items if i["state"] == "done"]
    fail = [i for i in items if i["state"] == "fail"]
    took = fmt(time.time() - d["began"]) if d.get("began") else ""
    lines = [(f"🏁 Очередь сайтов закончилась: проверено {len(done)} из {len(items)}" if items else
              "🏁 Очередь сайтов закончилась") + (f", заняла {took}" if took else "")]
    if fail:
        lines.append("\nПропущены:")
        lines += [f"• {_esc(_host(i['url']))} - {_esc(i.get('reason'))}" for i in fail[:30]]
    if done:
        tot = sum(i.get("pages") or 0 for i in done)
        lines.append(f"\nСтраниц во всех готовых: {tot:,}".replace(",", " "))
    sem_ok = sum(1 for i in done if i.get("sem") == "done") + sum(1 for i in sems if i["state"] == "done")
    sem_all = sum(1 for i in done if i.get("sem")) + len(sems)
    if sem_all:
        lines.append(f"Семантика собрана: {sem_ok} из {sem_all}. Пары слов ждут в «Словарь → Ждут подтверждения».")
    return "\n".join(lines)


# ---------- сам ход очереди ----------

def tick(job, start_check, start_sem=None):
    with _LOCK:
        d = load()
        changed = False
        for i in d["items"]:   # «идёт», но не нами в этом запуске: программу закрыли посреди сайта
            if i["state"] == "run" and (i["url"] != _current["url"] or _current["sem"] != (i.get("kind") == "sem")):
                if i.get("kind") == "sem":
                    i.update(state="wait", reason="программу закрыли посреди сбора, соберётся заново")
                else:
                    i.update(state="wait", resume=True, reason="программу закрыли посреди проверки, продолжится с того же места")
                changed = True
            if i.get("sem") == "run" and not (i["url"] == _current["url"] and _current["sem"]):
                i.update(sem="wait", sem_reason="программу закрыли посреди сбора, соберётся заново")
                changed = True
        if changed:
            save(d)
        if d["paused"] or job.running or _current["url"]:
            return
        # сначала семантика только что проверенного сайта, потом следующий сайт
        sem = next((i for i in d["items"] if i.get("sem") == "wait" and i["state"] == "done"), None)
        nxt = sem or next((i for i in d["items"] if i["state"] == "wait"), None)
        if not nxt:
            if not d.get("notified") and d.get("began"):
                d["notified"], d["paused"] = True, True
                save(d)
                _tg(_final_message(d))
            return
        if sem or nxt.get("kind") == "sem":
            if not start_sem:
                return
            _current.update(url=nxt["url"], stopping=False, sem=True)
            err = start_sem(nxt.get("folder") or "")
            if err:
                _current.update(url="", sem=False)
                if job.running:
                    return
                if sem:
                    nxt.update(sem="fail", sem_reason="не запустилась: " + err)
                else:
                    nxt.update(state="fail", reason="не запустилась: " + err, finished=time.time())
                save(d)
                return
            if sem:
                nxt.update(sem="run", sem_started=time.time(), sem_reason="")
            else:
                nxt.update(state="run", started=time.time(), reason="")
            save(d)
            return
        pages = nxt.get("limit") or d["pages"]
        _current.update(url=nxt["url"], stopping=False, sem=False)
        err = start_check({"site": nxt["url"], "pages": pages, "robots": "yandex", "ua": "yandexbot",
                           "resume": bool(nxt.get("resume")), "queue": True})
        if err:
            _current["url"] = ""
            if job.running:   # кто-то успел запустить свою проверку - подождать
                return
            nxt.update(state="fail", reason="не запустился: " + err, finished=time.time())
            save(d)
            _tg(f"⚠️ Очередь: <b>{_esc(_host(nxt['url']))}</b> не запустился - {_esc(err)}. Иду дальше.")
            return
        nxt.update(state="run", started=time.time(), reason="", pages_limit=pages)
        save(d)


def start(job, start_check, start_sem=None):
    """Вызывается при запуске окна: очередь сама берёт сайты, пока окно открыто."""
    def loop():
        while True:
            try:
                tick(job, start_check, start_sem)
            except Exception:
                pass
            time.sleep(TICK)
    threading.Thread(target=loop, daemon=True).start()
