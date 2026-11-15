"""Одна проверка, запущенная из окна: процесс crawl.py, его вывод и состояние для окна."""
import json
import os
import re
import subprocess
import sys
import threading
import time

from . import HERE, REPORTS
from ..fmt import plural as _plural

PARALLEL = 3     # сколько сайтов (ваш и конкуренты) проверяется одновременно
PARALLEL_JS = 2  # с JavaScript: у каждого сайта свой браузер, это тяжело для компьютера
NEW_SITE_PAGES = 300  # семантика нового сайта: столько страниц конкурента хватает на разделы и тексты
_START = threading.Lock()  # «уже идёт?» и «занято» - одним шагом (Job.start)
BUSY = "Сейчас идёт проверка. Дождитесь окончания."                      # ответ окна (409)
BUSY_START = "Проверка уже идёт. Дождитесь окончания или остановите её."  # start_check: Telegram, наблюдение, очередь


def _host(url):
    from urllib.parse import urlsplit
    return urlsplit(url).netloc or url


def _fewer_threads(args):
    """Конкуренту при одновременной проверке - вдвое меньше потоков (не меньше 2), пауза та же."""
    a = list(args)
    if "--threads" in a:
        i = a.index("--threads")
        try:
            a[i + 1] = str(max(2, int(a[i + 1]) // 2))
        except (IndexError, ValueError):
            pass
    else:
        a += ["--threads", "2"]  # по умолчанию у crawl.py 4
    return a


class Job:
    """Одна проверка, запущенная из окна: процесс crawl.py и его вывод."""

    def __init__(self):
        self.proc = None
        self.lines = []
        self.out_dir = ""
        self.site = ""
        self.started = 0.0
        self.finished = 0.0
        self.stop_file = ""
        self.lock = threading.Lock()
        self.active = False
        self.dirs, self.competitors_report = [], ""
        self.sites = []
        self.subs = []  # при одновременной проверке нескольких сайтов - по Job на сайт (свой ход и журнал)
        self.reset_state()

    @property
    def running(self):
        return self.active

    def reset_state(self):
        # Состояние запоминается по мере поступления строк, а не ищется в хвосте журнала:
        # журнал обрезается, и строка «Сайт 2 из 2» из него выпадала — окно показывало первый сайт.
        self.cur_site = None          # (n, total, who, url) — какой сайт проверяется сейчас
        self.step_text = ""
        self.prog = None
        self.prog_changed_at = time.time()
        self.site_pages = []          # [(url, проверено страниц)] по каждому законченному сайту
        self.was_stopped = False
        self.site_down = ""           # «Сайт перестал отвечать: …» - обход прекращён сам (crawler/main_loop.py)
        self.comparing = False
        self.idle_note = ""
        self.shaky_said = False       # «Сайт отвечает через раз» - уведомление один раз на сайт (crawler/shaky.py)
        self.access_note = ""         # «Сайт не открывается: …» / «Сайт не пускает программы: …» (crawler/access.py)

    def add(self, line):
        # техническая ошибка в строке (urlopen error, JSON от Google, net::ERR_…) - простыми словами;
        # исходный текст - в «Журнал», «Подробнее» (plain_errors.humanize)
        try:
            from ..plain_errors import humanize
            plain = humanize(line)
            if plain != line:
                from .. import applog
                applog.write("event", plain.strip(), "", line.strip())
                line = plain
        except Exception:
            pass
        if "Сайт отвечает через раз:" in line and not self.shaky_said:
            self.shaky_said = True
            self._shaky_event()
        if line.startswith(("Сайт не открывается:", "Сайт не пускает программы:")):
            self._access_event(line)
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > 3000:
                self.lines = self.lines[-2000:]
            m = re.search(r"Результаты сохраняются в папку: (.+)$", line) or \
                re.search(r"Продолжаю прошлую проверку этого сайта\. Папка: (.+)$", line)
            if m:
                self.out_dir = m.group(1).strip()
            m = re.search(r"Шаг (\d) из 4\. (.+)", line)
            if m:
                self.step_text = f"Шаг {m.group(1)} из 4: {m.group(2).strip()}"
            if "Собираю отчёт" in line:
                self.step_text = "Собираю отчёт"
            m = re.search(r"Страниц сайта: ([\d ]+) из ([\d ]+)", line)
            if m:
                prog = [int(m.group(1).replace(" ", "")), int(m.group(2).replace(" ", ""))]
                if not self.prog or prog[0] != self.prog[0]:
                    self.prog_changed_at = time.time()
                self.prog = prog
                m2 = re.search(r"последняя страница (.+?) назад", line)
                self.idle_note = m2.group(1) if m2 else ""
            m = re.search(r"Проверено страниц сайта: (\d+)", line)
            if m:
                url = self.cur_site[3] if self.cur_site else self.site
                self.site_pages.append((url, int(m.group(1))))
            if "Получена команда «Стоп»" in line or "Обход остановлен вручную" in line:
                self.was_stopped = True
            m = re.search(r"Сайт перестал отвечать: (.+?), главная тоже", line)
            if m:
                self.site_down = m.group(1)
            m = re.search(r"Результат проверки списка: (.+)$", line)
            if m:
                self.result_html = m.group(1).strip()
            m = re.search(r"Проверено адресов: ([\d]+) из ([\d]+)", line)
            if m:
                self.prog = [int(m.group(1)), int(m.group(2))]
                self.step_text = "Проверяю адреса"
            if "===== Сравниваю с конкурентами" in line or line.startswith("Сравниваю сайты:"):
                self.comparing = True

    def _access_event(self, line):
        """Плашка со звуком: главная не открылась, и понятно почему (crawler/access.py, access_check.py)."""
        from ..plain_errors import explain
        url = self.cur_site[3] if self.cur_site else self.site
        e = explain(line)
        self.access_note = e["title"]
        try:
            from . import events
            host = _host(url).removeprefix("www.")
            if "Дальше проверяю как браузер Chrome" in line:
                events.push("info", f"Сайт не пускает программы: {host}",
                            "Браузеру сайт отвечает, программе - отказом. Проверка сама идёт как браузер Chrome, "
                            "делать ничего не нужно.", site=host, detail=line)
            else:
                events.push("warn", f"{e['title']}: {host}" if line.startswith("Сайт не пускает") else
                            f"Сайт не открывается: {host}", e["title"] + ". " + e["todo"], site=host,
                            detail=e["detail"])
        except Exception:
            pass

    def _shaky_event(self):
        """Плашка со звуком: сайт отвечает через раз, проверка сама поставила паузу и идёт медленнее."""
        url = self.cur_site[3] if self.cur_site else self.site
        try:
            from . import events
            host = _host(url).removeprefix("www.")
            events.push("warn", f"Сайт отвечает через раз: {host}",
                        "Проверка сама поставила паузу и дальше идёт медленнее, адреса без ответа проверит ещё раз. "
                        "Делать ничего не нужно. Если сайт так и не начнёт отвечать, обход закончится сам, "
                        "а отчёт соберётся по тому, что успели.", site=host)
        except Exception:
            pass

    def start(self, sites, args, compare_folders=None, report_folder=None, label="", semantics_folders=None, deep=False,
              list_args=None, semantics_hosts=None, crawl_hosts=None, masks_folder=None, from_queue=False,
              light=False):
        """sites — список адресов: первый ваш сайт, остальные — конкуренты (проверяются по очереди с теми же
        настройками, потом строится сравнение). compare_folders — только сравнить уже готовые проверки.
        report_folder — только пересобрать отчёт готовой проверки (новой версией программы).
        False - уже идёт другая проверка, ничего не тронуто: окно, Telegram, наблюдение и очередь запускают из разных
        потоков, и раньше две проверки в одну секунду затирали друг другу состояние."""
        with _START:
            if self.active:
                return False
            self.active = True
        started = False   # сбой подготовки или запуска потока - «занято» снимается
        try:
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            self.lines, self.out_dir, self.site = [], "", sites[0] if sites else (label or "сравнение отчётов")
            self.sites = list(sites or [])
            self.reset_state()
            self.dirs, self.competitors_report = [], ""
            self.subs = []
            self.semantics_dir = semantics_folders[0] if semantics_folders else ""
            self.masks_job = bool(masks_folder)
            self.result_html = ""
            self.rebuild = bool(report_folder)  # «Обновить отчёт»: в окне «Обновляю отчёт» и прогресс сборки, а не обхода
            # вид задачи: кнопку «Дообойти» / «Обновить отчёт ещё раз» окно показывает только у обхода и обновления отчёта
            # (у масок, семантики, сравнения и списка адресов тоже есть папка с отчётом, а дообходить там нечего)
            self.kind = ("rebuild" if report_folder else "list" if list_args else "semantics" if semantics_folders else
                         "masks" if masks_folder else "compare" if compare_folders else "crawl")
            if self.rebuild:
                self.step_text = "Обновляю отчёт"
            self.express = False  # бот /express: по окончании прислать экспресс.pdf
            self.from_queue = from_queue  # сайт из «Очереди сайтов»: итог - в очередь, без сообщения на каждый сайт
            self.started, self.finished = time.time(), 0.0
            self.stop_file = os.path.join(REPORTS, f".stop-{int(time.time())}")
            self.status_file = os.path.join(REPORTS, f".status-{int(time.time())}.json")
            crawl = [sys.executable, os.path.join(HERE, "crawl.py")]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            args = list(args)

            def run_cmd(cmd):
                self.proc = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, creationflags=flags)
                for raw in self.proc.stdout:
                    self.add(raw.decode("utf-8", "replace").rstrip("\r\n"))
                return self.proc.wait()

            def run():
                try:
                    if report_folder:
                        self.add("Пересобираю отчёт: " + os.path.basename(report_folder))
                        run_cmd(crawl + ["--report", report_folder, "--no-open", "--status-file", self.status_file])
                        self.out_dir = report_folder
                        return
                    if list_args:  # проверка списка адресов или переезда
                        run_cmd(crawl + list_args + ["--no-open", "--stop-file", self.stop_file])
                        return
                    if semantics_folders:
                        folders = list(semantics_folders)
                        # семантика нового сайта: конкурентов по адресу сначала быстро проверить (разделы, заголовки, текст)
                        for n, h in enumerate(crawl_hosts or [], 1):
                            if os.path.exists(self.stop_file):
                                return
                            self.add(f"===== Конкурент {n} из {len(crawl_hosts)}: {h}, до {NEW_SITE_PAGES} страниц =====")
                            self.step_text, self.out_dir = f"Проверяю конкурента {n} из {len(crawl_hosts)}: {h}", ""
                            run_cmd(crawl + [h if "://" in h else "https://" + h + "/", "--max-pages", str(NEW_SITE_PAGES), "--no-images",
                                             "--no-external", "--no-exposed", "--no-open", "--stop-file", self.stop_file,
                                             "--status-file", self.status_file])
                            if self.out_dir:
                                folders.append(self.out_dir)
                        if os.path.exists(self.stop_file):
                            return
                        self.step_text = "Собираю семантику"
                        self.add("Собираю семантику: " + os.path.basename(folders[0]))
                        run_cmd(crawl + ["--semantics"] + folders + (["--deep"] if deep else []) + (["--light"] if light else [])
                                + (["--rival-hosts"] + list(semantics_hosts) if semantics_hosts else [])
                                + ["--no-open", "--stop-file", self.stop_file])
                        self.out_dir = semantics_folders[0]
                        return
                    if masks_folder:   # маски семантики: только читает проверку, «Остановить» просто закрывает программу
                        self.step_text = "Предлагаю маски семантики"
                        self.add("Предлагаю маски семантики: " + os.path.basename(masks_folder))
                        self.out_dir = masks_folder   # без папки окно считало готовые маски ошибкой
                        run_cmd(crawl + ["--masks", masks_folder])
                        return
                    if compare_folders:
                        run_cmd(crawl + ["--competitors"] + compare_folders + ["--no-open"])
                        self.competitors_report = os.path.join(compare_folders[0], "конкуренты.html")
                        self.out_dir = compare_folders[0]
                        return
                    if "--js" in args:
                        self.add("Готовлю режим JavaScript (при первом запуске скачивается браузер Chromium)...")
                        if run_cmd(crawl + ["--setup-js"]) != 0:
                            self.add("Режим JavaScript включить не получилось - проверяю без него.")
                            args.remove("--js")
                    if len(sites) > 1:  # ваш сайт и конкуренты - одновременно, у каждого свой ход и журнал
                        self._run_parallel(sites, args, crawl, env, flags)
                        if len(self.dirs) >= 2 and self.subs[0].out_dir and not os.path.exists(self.stop_file):
                            with self.lock:
                                self.comparing = True
                            self.add("===== Сравниваю с конкурентами =====")
                            run_cmd(crawl + ["--competitors"] + self.dirs + ["--no-open"])
                            self.competitors_report = os.path.join(self.dirs[0], "конкуренты.html")
                        return
                    # один сайт (несколько - выше, одновременно; прежний обход сайтов по очереди убран)
                    if sites and not os.path.exists(self.stop_file):
                        self.out_dir = ""
                        try:
                            os.remove(self.status_file)
                        except OSError:
                            pass
                        run_cmd(crawl + [sites[0]] + args + ["--no-open", "--stop-file", self.stop_file,
                                                             "--status-file", self.status_file])
                        if self.out_dir:
                            self.dirs.append(self.out_dir)
                except Exception as e:
                    self.add("Ошибка запуска: " + str(e)[:200])
                finally:
                    self.finished = time.time()
                    self.active = False
                    for f in (self.stop_file, self.status_file):
                        try:
                            if os.path.exists(f):
                                os.remove(f)
                        except OSError:
                            pass
                    if from_queue:  # очередь сама решает, что писать в Telegram (пропущенный сайт, итог очереди)
                        try:
                            from .. import site_queue
                            site_queue.on_finished(self)
                        except Exception as e:
                            self.add("Очередь сайтов: ошибка - " + str(e)[:200])
                    elif sites or semantics_folders:  # проверка сайта или семантика — сообщение в Telegram
                        try:
                            from .. import telegram
                            (telegram.notify_job if sites else telegram.notify_semantics)(self)
                        except Exception:
                            pass
                    try:   # плашка в окне со звуком и запись в «Журнал» (window/events.py)
                        from . import events
                        events.job_finished(self, "rebuild" if report_folder else "list" if list_args else
                                            "semantics" if semantics_folders else "masks" if masks_folder else
                                            "compare" if compare_folders else "check")
                    except Exception:
                        pass

            threading.Thread(target=run, daemon=True).start()
            started = True
            return True
        finally:
            if not started:
                self.active = False

    def _run_parallel(self, sites, args, crawl, env, flags):
        """Ваш сайт и конкуренты проверяются одновременно, но не больше PARALLEL сразу (с JavaScript -
        PARALLEL_JS: каждый сайт открывает свой браузер). Остальные ждут, пока освободится место.
        У каждого сайта своя проверка crawl.py, свой файл состояния и журнал (self.subs) - окно показывает
        каждый отдельно. Пауза между запросами у каждого сайта своя, как в настройках: сайты разные,
        и каждый получает не чаще, чем при обычной проверке. У конкурентов потоков вдвое меньше (не меньше 2),
        чтобы общий поток через прокси и интернет не вырос втрое."""
        limit = PARALLEL_JS if "--js" in args else PARALLEL
        if "--js" in args:   # браузеров несколько: вкладок на каждый как раньше (crawler/common.JS_TABS_GENTLE)
            args = args + ["--js-tabs", "3"]
        total = len(sites)
        subs = []
        for n, site in enumerate(sites, 1):
            sub = Job()
            sub.site, sub.n, sub.who = site, n, ("ваш сайт" if n == 1 else "конкурент")
            sub.stop_file = self.stop_file  # «Остановить» останавливает все сайты сразу
            sub.status_file = self.status_file.replace(".json", f"-{n}.json")
            sub.skipped = False
            subs.append(sub)
        with self.lock:
            self.subs = subs
            self.status_file = subs[0].status_file  # паутина и бот смотрят на ваш сайт
        self.add(f"Проверяю {total} {_plural(total, 'сайт', 'сайта', 'сайтов')}: ваш и "
                 f"{total - 1} {_plural(total - 1, 'конкурент', 'конкурента', 'конкурентов')}, "
                 f"одновременно не больше {limit}. Пауза между запросами у каждого сайта своя, как в настройках.")
        gate = threading.Semaphore(limit)

        def one(sub):
            with gate:
                if os.path.exists(self.stop_file):
                    sub.skipped = True
                    self.add(f"Сайт {sub.n} из {total} ({sub.who}): {sub.site} - не начат, проверку остановили")
                    return
                a = list(args)
                if sub.n > 1:
                    a = _fewer_threads(a) + ["--no-exposed"]  # служебные файлы ищем только у своего сайта
                tag = "[" + _host(sub.site) + "] "
                sub.started, sub.active = time.time(), True
                self.add(f"Начинаю сайт {sub.n} из {total} ({sub.who}): {sub.site}")
                try:
                    proc = subprocess.Popen(crawl + [sub.site] + a + ["--no-open", "--stop-file", self.stop_file,
                                                                      "--status-file", sub.status_file],
                                            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, creationflags=flags)
                    sub.proc = proc
                    for raw in proc.stdout:
                        line = raw.decode("utf-8", "replace").rstrip("\r\n")
                        sub.add(line)
                        self._log(tag + line)
                    proc.wait()
                except Exception as e:
                    sub.add("Ошибка запуска: " + str(e)[:200])
                    self._log(tag + "Ошибка запуска: " + str(e)[:200])
                finally:
                    sub.finished, sub.active = time.time(), False
                    try:
                        os.remove(sub.status_file)
                    except OSError:
                        pass
                    pages = sub.site_pages[-1][1] if sub.site_pages else None
                    self.add(f"Сайт {sub.n} из {total} ({sub.who}): {sub.site} - "
                             + ("остановлен" if sub.was_stopped else "готово" if sub.out_dir else "не получилось")
                             + (f", страниц: {pages}" if pages is not None else ""))

        threads = [threading.Thread(target=one, args=(s,), daemon=True) for s in subs]
        for t in threads:  # по порядку: первым место получает ваш сайт
            t.start()
            time.sleep(0.05)
        for t in threads:
            t.join()
        with self.lock:
            self.dirs = [s.out_dir for s in subs if s.out_dir]  # ваш сайт первым: так строится сравнение
            self.out_dir = subs[0].out_dir
            self.site_pages = [(s.site, s.site_pages[-1][1]) for s in subs if s.site_pages]
            self.was_stopped = self.was_stopped or any(s.was_stopped or s.skipped for s in subs)

    def _log(self, line):
        """Строка в общий журнал без разбора (строки сайтов при одновременной проверке разбирает сам сайт)."""
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > 3000:
                self.lines = self.lines[-2000:]

    def busy_folders(self):
        """Папки проверок, с которыми сейчас работает программа: их нельзя переносить и удалять. И папки, с которыми
        работает процесс, оставшийся от закрытого окна (метка run/guard.py)."""
        from ..run import guard
        busy = set()
        try:
            for e in os.scandir(REPORTS):
                if e.is_dir() and guard.busy(e.path):
                    busy.add(e.name)
        except OSError:
            pass
        if not self.running:
            return busy
        subs = [s.out_dir for s in getattr(self, "subs", [])]
        return busy | {os.path.basename(d) for d in [self.out_dir] + list(self.dirs) + subs if d}

    def stop(self):
        if self.running and self.stop_file:
            open(self.stop_file, "w").close()
            # в «Подробном журнале» карточки видно, что остановили вручную и когда
            self.add(time.strftime("%H:%M:%S") + " Нажата кнопка «Остановить»: "
                     + ("отчёт обновлён не до конца" if getattr(self, "rebuild", False)
                        else "останавливаю, отчёт соберётся по тому, что успели проверить"))
            # маски только читают проверку, «Обновить отчёт» заново пишет файлы отчёта: прервать можно в любой
            # момент (файла «стоп» crawl.py --report не читает - раньше кнопка «Остановить» тут ничего не делала)
            if (getattr(self, "masks_job", False) or getattr(self, "rebuild", False)) and self.proc and self.proc.poll() is None:
                self.was_stopped = True
                self.proc.kill()

    def run_status(self, n):
        """Ход одного сайта при одновременной проверке (n - номер сайта с 1) или None."""
        subs = getattr(self, "subs", [])
        if not (1 <= n <= len(subs)):
            return None
        sub = subs[n - 1]
        st = sub.status()
        if sub.active:
            state = "run"
        elif sub.finished:
            state = "stopped" if (sub.was_stopped or sub.skipped) else ("done" if st["report"] else "fail")
        else:
            state = "skipped" if (sub.skipped or not self.running) else "wait"
        return dict(st, n=n, who=sub.who, site=sub.site, state=state, status_file=sub.status_file if sub.active else "",
                    overall=100.0 if state == "done" else st["overall"], log=st["log"][-40:])

    def _status_parallel(self):
        """Состояние для окна при одновременной проверке: главная карточка - ваш сайт, runs - все сайты."""
        runs = [self.run_status(i + 1) for i in range(len(self.subs))]
        own, running = runs[0], self.running
        with self.lock:
            comparing, lines, site_pages = self.comparing, list(self.lines), list(self.site_pages)
        out = dict(own)
        out.pop("status_file", None)
        others = [r for r in runs[1:] if r["state"] in ("run", "wait")]
        step = own["step"]
        if running and comparing:
            step = "Сравниваю сайты - читаю базы проверок, на больших сайтах это несколько минут"
        elif running and own["state"] != "run":
            step = ("Ваш сайт проверен" if own["state"] == "done" else "Ваш сайт: проверка закончилась") + \
                ", жду конкурентов: " + ", ".join(_host(r["site"]) for r in others) if others else "Собираю сравнение"
        comp = ""
        if self.competitors_report and os.path.exists(self.competitors_report) and not running:
            comp = os.path.basename(os.path.dirname(self.competitors_report))
        if own["state"] != "run":  # ваш сайт закончен, а конкуренты ещё идут: тревоги и паузы - не про него
            out.update(stuck=0, idle=0, idle_note="", pause_note="", waiting=None, speed=None, limit_hit=False,
                       shaky_note="")
            if own.get("done_pages") is not None and own.get("progress"):  # итог обхода, а не последний замер
                out["progress"] = [own["done_pages"], own["progress"][1]]
        alive = [r for r in runs if r["state"] in ("run", "wait", "done")]
        keep = ("n", "who", "site", "state", "step", "progress", "overall", "unit", "stuck", "idle", "elapsed",
                "report", "log", "limit_hit", "waiting", "speed", "done_pages", "shaky_note")
        out.update(
            running=running, step=step, competitors=comp, sites=list(self.sites), started=True,
            site=self.sites[0] if running else self.sites[0] + f" и конкурентов: {len(self.sites) - 1}",
            elapsed=round((self.finished or time.time()) - self.started) if self.started else 0,
            stopped=self.was_stopped or any(r["state"] == "stopped" for r in runs),
            # «Остановить» нажата: кнопка «Останавливаю…», пока конкуренты и сравнение не закончатся (файл «стоп» общий)
            stopping=bool(running and self.stop_file and os.path.exists(self.stop_file)),
            overall=own["overall"] if own["state"] in ("run", "done") else None,
            overall_all=round(sum(r["overall"] or 0 for r in alive) / len(alive), 1) if alive and running else None,
            log=own["log"][-60:] if running and own["state"] == "run" else lines[-60:],
            site_pages=site_pages or [(r["site"], r["done_pages"]) for r in runs if r.get("done_pages") is not None],
            report=own["report"] if own["state"] != "run" else "", rebuild=False, kind="crawl", result="", semantics="",
            runs=[{k: r.get(k) for k in keep} for r in runs],
            # плитки ваших цифр - из строки прогресса вашего сайта: в общем журнале после вашего сайта пишут
            # конкуренты, и окно показывало их картинки, ссылки и очередь как ваши (woodhousedog.kz 16.10)
            prog_line=self.subs[0].prog_line(), own_done=own["state"] != "run")
        return out

    def prog_line(self):
        """Последняя строка прогресса обхода этого сайта («Страниц сайта: … | картинок и файлов: …»)."""
        with self.lock:
            return next((ln for ln in reversed(self.lines) if "Страниц сайта:" in ln), "")

    def status(self):
        if getattr(self, "subs", None):
            return self._status_parallel()
        with self.lock:
            lines = list(self.lines)
            cur, step, prog = self.cur_site, self.step_text, self.prog
            site_pages, idle_note = list(self.site_pages), self.idle_note
            idle = round(time.time() - self.prog_changed_at) if prog else 0
        stuck, pause_note, shaky_note = None, "", ""
        running = self.running
        unit = "pages"
        # Главный источник — файл состояния, который пишет сама проверка; журнал — запасной вариант
        st = None
        if running and getattr(self, "status_file", "") and os.path.exists(self.status_file):
            try:
                with open(self.status_file, encoding="utf-8") as f:
                    st = json.load(f)
            except (OSError, ValueError):
                st = None
        if st:
            step = st.get("step") or step
            if st.get("pages") is not None and st.get("limit"):
                prog = [st["pages"], st["limit"]]
            unit = st.get("unit", "pages")
            if st.get("last_page_ago") is not None and (st.get("step") or "").startswith("Шаг 3"):
                idle = st["last_page_ago"]
                a = int(idle)
                idle_note = (f"{a // 60} мин {a % 60} с" if a >= 60 else f"{a} с") if a > 30 else ""
                pause_note = st.get("pause_note") or ""
                # по-настоящему застряла — когда не заканчивается ни один адрес (или проверка перестала
                # писать о себе), а не когда просто нет новых страниц: в это время могут проверяться фото
                stuck = (st.get("last_done_ago") or 0) + max(0, time.time() - (st.get("updated") or time.time()))
            if (st.get("step") or "").startswith("Шаг"):
                shaky_note = st.get("shaky_note") or ""   # сайт отвечает через раз (crawler/shaky.py)
        overall = _overall(st, prog) if (running and st) else None
        report_pct = None
        if running and st and (step or "").startswith(("Собираю отчёт", "Обновляю отчёт")):
            # сборка отчёта: своя доля, а счётчик прошлого шага («600 из 600 медленных страниц») ни о чём не говорит
            report_pct = int(100 * max(0.0, min(1.0, st.get("report_frac") or 0)))
            prog = None
        if not (step or "").startswith("Шаг 3"):
            # после обхода (перемер скорости, дубли, отчёт) новых страниц и не должно прибавляться — не тревожим
            idle, idle_note, pause_note, stuck = 0, "", "", 0
        if stuck is None:  # без файла состояния: судим по числу страниц
            stuck = idle
        report = ""
        if self.out_dir and os.path.exists(os.path.join(self.out_dir, "отчёт.html")) and not running:
            report = os.path.basename(self.out_dir)
        sem = ""
        sem_dir = getattr(self, "semantics_dir", "")
        if sem_dir and not running and os.path.exists(os.path.join(sem_dir, "семантика.xlsx")):
            sem, report = os.path.basename(sem_dir), ""
        comp = ""
        if self.competitors_report and os.path.exists(self.competitors_report) and not running:
            comp = os.path.basename(os.path.dirname(self.competitors_report))
        site = self.site
        if running and cur:
            n, total, who, url = cur
            site = url
            step = f"Сайт {n} из {total} ({who}): {url} - " + (step or "запускаю")
        if running and self.comparing:
            step = "Сравниваю сайты - читаю базы проверок, на больших сайтах это несколько минут"
        if not running and len(self.sites) > 1:
            site = self.sites[0] + f" и конкурентов: {len(self.sites) - 1}"
        res = getattr(self, "result_html", "")
        result = ""
        if res and not running and os.path.exists(res):
            result = os.path.relpath(res, REPORTS).replace("\\", "/")
            report = ""
        if not running or not st:
            unit = "pages"
        if not running and site_pages and prog:
            # итог проверки, а не последняя строка обхода: она пишется раз в несколько секунд, последние страницы
            # (и страницы после обхода) в неё не попадают - vsekuhni.ru: в окне 2 061, в отчёте 2 064
            prog = [site_pages[0][1], prog[1]]
        return {"running": running, "unit": unit, "result": result, "site": site, "log": lines[-60:], "step": step, "progress": prog,
                "elapsed": round((self.finished or time.time()) - self.started) if self.started else 0,
                "report": report, "competitors": comp, "semantics": sem, "started": bool(self.started), "stopped": self.was_stopped,
                # «Остановить» уже нажата, проверка дособирает отчёт: кнопка остаётся «Останавливаю…»
                "stopping": bool(running and self.stop_file and os.path.exists(self.stop_file)),
                "done_pages": site_pages[0][1] if site_pages else None,
                "site_pages": site_pages, "idle": idle, "idle_note": idle_note,
                "stuck": round(stuck), "pause_note": pause_note, "overall": overall, "shaky_note": shaky_note,
                "report_pct": report_pct,
                "waiting": (st or {}).get("waiting") if running else None, "rebuild": getattr(self, "rebuild", False),
                "kind": getattr(self, "kind", ""),
                "limit_hit": bool((st or {}).get("limit_hit")) if running else False,
                "speed": (st or {}).get("speed") if running else None, "sites": list(self.sites),
                # память и процессор проверки (seocrawler/memory.py) - строкой в карточке проверки
                "res": (st or {}).get("res") if running else None}


# Общая полоса прогресса на всю проверку: обход — основная часть, но после него ещё sitemap,
# дополнительные проверки и отчёт. Раньше полоса показывала только «страниц из лимита» и
# заполнялась до конца, пока программа ещё допроверяла картинки и ссылки (exist.ru, 9 980 из 10 000).
_AFTER = ["Проверяю закрытую", "Сравниваю, что сайт отдаёт роботу", "Сравниваю, что сайт отдаёт телефону",
          "Открываю страницы как на телефоне", "Замеряю скорость", "Проверяю картинки для превью",
          "Проверяю устойчивость", "Перепроверяю адреса", "Перемеряю скорость"]
_REPORT = ["Собираю отчёт", "Определяю движок", "Загружаю данные Яндекс Вебмастера",
           "Загружаю данные Google", "Загружаю данные Яндекс Метрики", "Готово"]


def _overall(st, prog):
    """Сколько процентов всей проверки сделано (0–100) по файлу состояния."""
    step = st.get("step") or ""

    def part(a, b, frac):
        return round(a + (b - a) * max(0.0, min(1.0, frac)), 1)
    frac = prog[0] / prog[1] if prog and prog[1] else 0
    if step.startswith("Шаг 1") or step.startswith("Шаг 2") or step == "Запускаю":
        return 1.0 if step.startswith("Шаг 2") else 0.0
    if step.startswith("Шаг 3"):
        f = st.get("frac")
        return part(2, 85, f if f is not None else frac)
    if step.startswith("Шаг 4"):
        return part(85, 90, frac)
    for i, s in enumerate(_AFTER):
        if step.startswith(s):
            a = 90 + 6 * i / len(_AFTER)
            return part(a, a + 6 / len(_AFTER), frac if st.get("unit") in ("probe", "slow") else 0.5)
    rf = st.get("report_frac")
    if step.startswith("Обновляю отчёт"):  # «Обновить отчёт»: вся полоса — сборка отчёта
        return round(100 * max(0.0, min(1.0, rf or 0)), 1)
    if step.startswith("Собираю отчёт"):  # конец обычной проверки
        return round(96 + 3.5 * max(0.0, min(1.0, rf or 0)), 1)
    for i, s in enumerate(_REPORT):
        if step.startswith(s):
            return round(96 + 3.5 * i / len(_REPORT), 1)
    return None


JOB = Job()
