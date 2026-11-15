"""Главный цикл обхода: потоки, сторож зависших адресов, строка прогресса, шаги 1–4."""
import os
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from ..fetcher import UA_PRESETS
from .. import renderer as R
from .. import urls as U
from .common import _ago, _n, _plural

PAGE_QUEUED = "state='queued' AND kind='page' AND internal=1"
SPEED_POINTS = 21        # столько отметок раз в 3 с: скорость «сейчас» - за последнюю минуту
JOURNAL_EVERY = 300      # раз в столько секунд строка в файл «ход проверки.txt»
JOURNAL_FILE = "ход проверки.txt"


def speed_now(points) -> float:
    """Скорость за последние отметки [(время, сколько проверено)]. Раньше в окне было среднее с начала шага, и оно
    сползало медленно: thehome.ru показывал 2,4 адр/с, когда шло 1,5, и обещал 41 минуту вместо 97."""
    if len(points) < 2:
        return 0.0
    (t0, n0), (t1, n1) = points[0], points[-1]
    return (n1 - n0) / max(t1 - t0, 0.1)


class MainLoopMixin:
    # ---------- городские версии сайта
    def find_regions(self):
        """Найти городские версии по переключателю города на главной (seocrawler/regions.py) и поставить их в обход."""
        import re
        from urllib.parse import urljoin
        from .. import regions
        self.log("\nИщу городские версии сайта (переключатель города на главной)...")
        r = self.fetcher.fetch(self.start)
        if r.status != 200 or not r.body:
            self.log("   Главная не открылась - города не ищу.")
            return []
        html = r.body.decode("utf-8", "replace") if isinstance(r.body, bytes) else str(r.body)
        links = [urljoin(self.start, h) for h in re.findall(r"href\s*=\s*[\"']([^\"'#]+)", html)]

        def fetch(u):
            self.limiter.wait()
            x = self.fetcher.fetch(u, read_body=False)
            return x.status, x.url
        step = "Шаг 1 из 4: Ищу городские версии сайта (переключатель города на главной)"
        found = regions.discover(self.start, html, links, fetch, log=self.log, stop=self.stopped,
                                 progress=lambda i, n: self.st(step=step, unit="regions", pages=i, limit=n))
        if self.stop_flag:
            return []
        names = regions.city_names(html)
        if names and not found:  # переключатель есть, а своих адресов у городов нет (город — в cookie, как у gigas.su)
            self.store.set_meta("regions_no_urls", [n for n, _ in names])
            self.log("   У городов нет своих адресов: при выборе города адрес страницы не меняется.")
        if not self.cfg.regions:  # режим «Сайт с городами» выключен: только сообщим, что города есть
            self.store.set_meta("regions_seen", found)
            return []
        self.store.set_meta("regions", found)
        self.apply_regions(found)
        for x in found:
            if not x["main"]:
                self.store.enqueue(x["url"], 0, True, "page", "переключатель города")
        return found

    def apply_regions(self, found):
        """Поддомены городов — часть сайта (остальные поддомены, например shop., по-прежнему чужие)."""
        hosts = {U.host_of(x["url"]) for x in found if U.host_of(x["url"]) != self.root_host}
        if hosts and self.cfg.crawl_subdomains is not True:
            self.cfg.crawl_subdomains = frozenset(hosts)

    # ---------- чем занята программа, пока число страниц стоит
    @staticmethod
    def pause_kind(url, internal, kind):
        if not internal:
            return "f:" + U.host_of(url) if kind == "resource" or U.is_file_url(url) else "ext"
        return "sitemap" if kind == "sitemap" else "res"

    @staticmethod
    def pause_note(pause):
        """«проверено 2 400 адресов, из них: фото и файлы с других сайтов - 2 350 (в основном img.detmir.st), …»"""
        total = sum(pause.values())
        if not total:
            return ""
        files = sorted(((n, k[2:]) for k, n in pause.items() if k.startswith("f:")), reverse=True)
        parts = []
        if files:
            parts.append(f"фото и файлы с других сайтов - {_n(sum(n for n, _ in files))} "
                         f"(в основном {', '.join(h for _, h in files[:2])})")
        for k, name in (("res", "картинки и файлы сайта"), ("ext", "ссылки на другие сайты"), ("sitemap", "адреса из sitemap")):
            if pause.get(k):
                parts.append(f"{name} - {_n(pause[k])}")
        return f"проверено {_n(total)} {_plural(total, 'адрес', 'адреса', 'адресов')}, из них: " + ", ".join(parts)

    # ---------- строка прогресса
    def progress_line(self, pages_done, speed):
        pr = self.store.progress()

        def g(k, st):
            return pr.get(k, {}).get(st, 0)
        parts = [f"Страниц сайта: {_n(pages_done)} из {_n(self.cfg.max_pages)}"]
        if self.cfg.check_resources:
            parts.append(f"картинок и файлов: {_n(g('resource', 'done'))}")
        if g("ext_file", "done"):  # в продолженной старой проверке прежние фото записаны как внешние ссылки
            parts.append(f"фото с других сайтов: {_n(g('ext_file', 'done'))}")
        if self.cfg.check_external:
            parts.append(f"внешних ссылок: {_n(g('external', 'done'))}")
        if g("sitemap", "done") or g("sitemap", "queued"):
            parts.append(f"из sitemap: {_n(g('sitemap', 'done'))}")
        limit_hit = pages_done >= self.cfg.max_pages
        waiting = sum(v.get("queued", 0) for k, v in pr.items() if not (limit_hit and k == "page"))
        parts.append(f"ждут проверки: {_n(waiting)}")
        self._waiting = waiting
        # доля сделанного в обходе: страницы до лимита + картинки и ссылки, которые ещё ждут
        # (после лимита страниц обход продолжается — допроверяются картинки и внешние ссылки)
        page_q = g("page", "queued")
        other_done = sum(v.get("done", 0) for k, v in pr.items() if k != "page")
        other_wait = waiting - (0 if limit_hit else page_q)
        target = min(self.cfg.max_pages, pages_done + page_q)
        # Адреса весят по времени, которое они занимают: страница с JavaScript — секунд 15, фото — 1–3 с.
        # Раньше все адреса считались одинаково, и доля на zoozavr.ru была далека от того, сколько осталось ждать.
        dur = getattr(self, "_dur", {})
        wp, wo = (dur["page"], dur["other"]) if dur.get("page") and dur.get("other") else (1.0, 1.0)
        self._frac = min(1.0, (pages_done * wp + other_done * wo) /
                         max(1e-9, target * wp + (other_done + other_wait) * wo))
        parts.append(f"{speed:.1f} адр/с")
        line = "   " + " | ".join(parts)
        if limit_hit and not getattr(self, "_limit_said", False):
            self._limit_said = True
            line += "\n   Лимит страниц достигнут - допроверяю картинки и ссылки с уже обойдённых страниц."
        return line

    # ---------- ход проверки на диске: строки журнала живут только в памяти окна, и после проверки не понять, сколько
    # шли страницы и картинки по часам (thehome.ru: скорости пришлось восстанавливать по порядку записей в
    # базе)
    def note_progress(self, label, pages_done, speed, force=False):
        now = time.time()
        if not force and now - getattr(self, "_journal_at", 0) < JOURNAL_EVERY:
            return
        pr = self.store.progress()
        res = pr.get("resource", {}).get("done", 0)
        waiting = sum(v.get("queued", 0) for v in pr.values())
        p0, r0, t0 = getattr(self, "_journal_last", (pages_done, res, now))
        secs = max(now - t0, 0.1)
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {label} | "
                f"страниц {pages_done} ({(pages_done - p0) / secs:.2f}/с) | "
                f"картинок и файлов {res} ({(res - r0) / secs:.2f}/с) | ждут {waiting} | сейчас {speed:.1f} адр/с\n")
        self._journal_at, self._journal_last = now, (pages_done, res, now)
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(self.store_path)), JOURNAL_FILE), "a",
                      encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            self.log(f"   Ход проверки не записан в файл: {e}")

    # ---------- сайт перестал отвечать (упал посреди обхода)
    # Столько страниц сайта подряд с ошибкой 5xx или без ответа - и ни одной нормальной страницы столько секунд
    # (картинки не в счёт: их часто отдаёт отдельный сервер, и он работает, когда сам сайт лежит): тогда ещё раз открываем главную, и если не открылась и она - обход
    # прекращается, отчёт собирается по тому, что успели. Раньше проверка часами крутила ошибки (domeo.ru: 502,
    # два часа без новых страниц). Короткий сбой на минуту-другую обход не прерывает.
    DOWN_STREAK = int(os.environ.get("CLAYLER_DOWN_STREAK") or 40)
    DOWN_SECONDS = float(os.environ.get("CLAYLER_DOWN_SECONDS") or 600)
    # срок сторожа зависших адресов, с; 0 - по настройкам (_drain). Меньше - только для автотеста сторожа
    WATCHDOG = float(os.environ.get("CLAYLER_WATCHDOG") or 0)

    def note_health(self, is_page, code):
        """Учесть ответ страницы сайта; True - пора проверить, не упал ли сайт."""
        if not is_page:
            return False
        now = time.time()
        d = getattr(self, "_down", None)
        if d is None:
            d = self._down = {"streak": 0, "ok_at": now, "codes": Counter()}
        if code and code < 500:
            d["streak"], d["ok_at"] = 0, now
            d["codes"].clear()
            return False
        d["streak"] += 1
        d["codes"][code or 0] += 1
        return d["streak"] >= self.DOWN_STREAK and now - d["ok_at"] >= self.DOWN_SECONDS

    def site_is_down(self):
        """Много ошибок подряд: открыть главную ещё раз. Не открылась - сайт перестал отвечать, обход прекращается."""
        d = self._down
        r = self.fetcher.fetch(self.start, read_body=False)
        if r.status and r.status < 500:
            d["streak"], d["ok_at"] = 0, time.time()
            d["codes"].clear()
            self.log("   Много ошибок подряд, но главная открывается - продолжаю обход.")
            return False
        top = d["codes"].most_common(1)[0][0] if d["codes"] else 0
        what = f"ошибка {top}" if top else "нет ответа"
        mins = max(1, round((time.time() - d["ok_at"]) / 60))
        self.site_down = (f"{what} на {_n(d['streak'])} {_plural(d['streak'], 'адрес', 'адреса', 'адресов')} подряд, "
                          f"нормальных ответов нет {mins} мин")
        why = self.access_reason(r)
        if why:
            self.site_down += "; " + why
        self.store.set_meta("site_down", self.site_down)
        self.log(f"\nСайт перестал отвечать: {self.site_down}, главная тоже не открывается "
                 f"({r.status or r.error or 'нет ответа'}). Обход прекращаю, отчёт соберу по тому, что успели проверить.")
        self.stop_flag = True
        return True

    # ---------- памяти компьютера почти не осталось: остановиться самим, а не упасть (thehome.ru)
    def low_memory(self):
        """Раз в 5 с смотрим, сколько памяти ещё можно выделить (seocrawler/memory.py). Мало - обход
        останавливается, как по «Остановить»: всё проверенное в базе, «Продолжить прошлую проверку» доделает."""
        now = time.time()
        if now - getattr(self, "_mem_at", 0) < 5:
            return False
        self._mem_at = now
        from .. import memory
        low, free = memory.is_low()
        if not low:
            return False
        self.low_mem = free
        self.store.set_meta("low_memory", {"free_mb": free, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
        self.log(f"\nПамяти компьютера почти не осталось (можно занять ещё {_n(free)} МБ) - останавливаю обход, "
                 "всё проверенное сохранено.")
        self.log("   Закройте лишние программы и запустите проверку снова с галочкой «Продолжить прошлую проверку»: "
                 "обход продолжится с этого места.")
        self.stop_flag = True
        return True

    # ---------- один проход по очереди
    def _drain(self, pages_done, label):
        cfg = self.cfg
        last_log, checked = time.time(), 0
        recent = deque([(last_log, 0)], maxlen=SPEED_POINTS)
        last_done_at = last_page_at = time.time()
        stall_warned = False
        # Сторож: адрес, который не закончился за это время, бросаем (поток дорабатывает сам по себе,
        # результат не ждём). Запас на повторы: каждая попытка — до total_timeout + timeout.
        watchdog = self.WATCHDOG or max(120.0, (cfg.total_timeout + cfg.timeout) * (cfg.retries + 1) + 30)
        spare = 8  # запасные потоки на случай брошенных адресов
        live_max = cfg.threads + 2
        other_slots = max(1, live_max // 3)  # потоков за картинками и ссылками, даже когда ждут страницы
        inflight, abandoned = {}, 0
        pause, pause_said = Counter(), 0  # что проверено после последней страницы — для журнала и бота
        if not hasattr(self, "_dur"):
            self._dur = {}
        pool = ThreadPoolExecutor(max_workers=cfg.threads + spare)
        try:
            while not self.stop_flag:
                if self.cfg.stop_file and os.path.exists(self.cfg.stop_file):
                    self.log("\nПолучена команда «Стоп». Останавливаю обход, всё проверенное сохранено.")
                    self.stop_flag = True
                    break
                if self.low_memory():
                    break
                # сайт отвечает через раз (shaky.py): на паузе новых адресов не берём, потом - меньше потоков
                calm = self.shaky_left()
                if self.stop_flag:
                    break
                live_max = self.shaky_cap(cfg.threads + 2)
                other_slots = max(1, live_max // 3) if live_max > 1 else 0
                room = live_max - len(inflight) if not calm else 0
                if room > 0:
                    busy_pages = sum(1 for v in inflight.values() if v[3] == "page" and v[2])
                    allowed = pages_done + busy_pages < cfg.max_pages
                    taken = {v[0] for v in inflight.values()}
                    pages, other = self.store.next_batch(room + len(inflight), allowed)
                    self.pages_idle = not pages and not busy_pages   # страниц нет - картинкам обе очереди пауз (base.limiter_for)
                    # страницы сайта — вперёд, но пара потоков всегда за картинками и ссылками, если они есть:
                    # иначе на большом сайте они копились бы до конца обхода
                    want_other = max(0, other_slots - (len(inflight) - busy_pages)) if other else 0
                    for row in other[:want_other] + pages + other[want_other:]:
                        if row["url"] in taken:
                            continue
                        if row["kind"] == "page" and row["internal"]:
                            if pages_done + busy_pages >= cfg.max_pages:
                                continue
                            busy_pages += 1
                        self.store.mark(row["url"], "fetching")
                        f = pool.submit(self.work, row["url"], bool(row["internal"]), row["kind"])
                        inflight[f] = (row["url"], row["depth"], bool(row["internal"]), row["kind"], time.time())
                        taken.add(row["url"])
                        if len(inflight) >= live_max:
                            break
                if not inflight and not calm:
                    break
                if inflight:
                    done, _ = wait(list(inflight), timeout=1, return_when=FIRST_COMPLETED)
                else:  # пауза из-за сбоев сайта, загружать нечего - ждём
                    done = ()
                    time.sleep(0.5)
                for f in done:
                    url, depth, internal, kind, t_start = inflight.pop(f)
                    try:
                        r, parsed = f.result()
                        if self.shaky_note(url, internal, r):
                            # сайт отвечает через раз: адрес без ответа - в очередь ещё раз, не ошибкой в отчёт
                            self.store.mark(url, "queued")
                            if self.note_health(kind == "page" and internal, r.status or 0) and not self.stop_flag:
                                self.site_is_down()
                            checked += 1
                            last_done_at = time.time()
                            continue
                        self.handle(url, depth, internal, kind, r, parsed)
                        # для живой паутины в окне: сколько адресов с ошибкой и с переадресацией
                        code = r.status or 0
                        if code == 0 or code >= 400:
                            self._web_bad = getattr(self, "_web_bad", 0) + 1
                        elif code >= 300:
                            self._web_warn = getattr(self, "_web_warn", 0) + 1
                        if self.note_health(kind == "page" and internal, code) and not self.stop_flag:
                            self.site_is_down()
                    except Exception as e:
                        self.store.mark(url, "done", "Сбой обработки: " + str(e)[:100])
                        self.log_failure(url, e)
                    checked += 1
                    last_done_at = time.time()
                    is_page = kind == "page" and internal
                    # сколько в среднем занимает страница и остальной адрес: для честной доли сделанного
                    k = "page" if is_page else "other"
                    d = last_done_at - t_start
                    self._dur[k] = d if self._dur.get(k) is None else self._dur[k] * 0.98 + d * 0.02
                    if is_page:
                        pages_done += 1
                        last_page_at = last_done_at
                        pause.clear()
                    else:
                        pause[self.pause_kind(url, internal, kind)] += 1
                # сторож: зависшие адреса
                now = time.time()
                for f, v in list(inflight.items()):
                    if now - v[4] > watchdog:
                        url, depth, internal, kind = v[:4]
                        inflight.pop(f)
                        abandoned += 1
                        err = f"Программа не дождалась ответа за {watchdog:.0f} с"
                        self.store.save_page({"url": url, "status": 0, "error": err, "indexable": 0,
                                              "indexability": "Нет ответа", "elapsed": round(now - v[4], 1)})
                        self.store.mark(url, "done", err)
                        self.log(f"   Адрес не ответил за {watchdog:.0f} с, пропускаю: {url}")
                        if kind == "page" and internal:
                            pages_done += 1
                        if self.note_health(kind == "page" and internal, 0) and not self.stop_flag:
                            self.site_is_down()
                        if abandoned == spare:
                            self.log("   Внимание: много зависших адресов - сервер, похоже, перегружен. "
                                     "Попробуйте запустить проверку с меньшей скоростью.")
                self.store.commit()
                if time.time() - last_log > 3:
                    last_log = time.time()
                    recent.append((last_log, checked))
                    speed = speed_now(recent)
                    line = self.progress_line(pages_done, speed)
                    self.note_progress(label, pages_done, speed)
                    idle_page = time.time() - last_page_at
                    if label in ("sitemap", "search"):
                        # адреса из поиска лежат в очереди так же, как из sitemap: считаем только добавленные сейчас
                        sm = self.store.progress().get("sitemap", {})
                        b_done, b_all = getattr(self, "_search_base", (0, 0)) if label == "search" else (0, 0)
                        self.st(pages=sm.get("done", 0) - b_done, limit=(sum(sm.values()) - b_all) or 1, unit=label)
                    else:
                        self.st(pages=pages_done, limit=cfg.max_pages, unit="pages")
                    paused = idle_page > 30 and pages_done < cfg.max_pages and label not in ("sitemap", "search")
                    note = self.pause_note(pause) if paused else ""
                    self.st(waiting=getattr(self, "_waiting", None), frac=round(getattr(self, "_frac", 0), 4),
                            limit_hit=pages_done >= cfg.max_pages,
                            speed=round(speed, 1),
                            last_page_ago=round(idle_page), last_done_ago=round(time.time() - last_done_at),
                            pause_note=note, web_bad=getattr(self, "_web_bad", 0), web_warn=getattr(self, "_web_warn", 0))
                    if paused:
                        line += f" | последняя страница {_ago(idle_page)} назад"
                    if calm or self.shaky_cap(0):
                        line += " | " + self._shaky_status()
                    self.log(line)
                    # раз в 5 минут без новых страниц — чем занята программа (а не только «число стоит»)
                    if paused and note and idle_page // 300 > pause_said:
                        pause_said = idle_page // 300
                        self.log(f"   Новых страниц нет {_ago(idle_page)}: {note}. "
                                 f"Страниц сайта в очереди: {_n(self.store.count(PAGE_QUEUED))}.")
                    elif not paused:
                        pause_said = 0
                    idle = time.time() - last_done_at
                    if idle > 300 and not stall_warned:
                        stall_warned = True
                        self.log(f"\n   Внимание: уже {_ago(idle)} не закончился ни один адрес. Сейчас загружаются:")
                        for v in sorted(inflight.values(), key=lambda v: v[4])[:8]:
                            self.log(f"     {v[0]} - {_ago(time.time() - v[4])}")
                        self.log("   Если так и останется, нажмите «Остановить»: отчёт соберётся по уже проверенному.\n")
                    elif idle < 60:
                        stall_warned = False
        except KeyboardInterrupt:
            self.log("\nОстанавливаю обход... Всё, что успели проверить, сохранено.")
            self.stop_flag = True
        finally:
            for f in inflight:
                f.cancel()
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # Python до 3.9
                pool.shutdown(wait=False)
        self.store.db.execute("UPDATE urls SET state='queued' WHERE state='fetching'")
        self.store.commit()
        self.note_progress(label, pages_done, speed_now(recent), force=True)   # конец шага - всегда отдельной строкой
        return pages_done

    def save_timings(self, times):
        """Время по этапам - в meta timings (при продолжении проверки складывается) и строкой в журнал:
        «Время по этапам: обход 1 ч 10 мин, страницы на телефоне 12 мин...». Этапы меньше 30 с не пишутся."""
        old = self.store.get_meta("timings", {}) or {}
        for k, v in times.items():
            old[k] = round(old.get(k, 0) + v, 1)
        self.store.set_meta("timings", old)
        from ..duration import fmt
        parts = [f"{k} {fmt(v) if v >= 90 else _ago(v)}" for k, v in old.items() if v >= 30]
        if parts:
            self.log("\nВремя по этапам: " + "; ".join(parts) + ".")

    # ---------- главный цикл
    def run(self):
        cfg = self.cfg
        if cfg.extract is None:   # «Свои данные со страниц»: при продолжении проверки - те же правила, что в начале
            from .. import extract
            saved = self.store.get_meta("extract_rules")
            cfg.extract = saved if saved is not None and self.store.seen(self.start) else extract.for_site(self.start)
        self.store.set_meta("extract_rules", cfg.extract or [])
        self.store.set_meta("config", cfg.__dict__)
        self.store.set_meta("start", self.start)
        self.store.set_meta("scope", self.scope_meta())
        t_run = time.time()  # время работы — для «Проверка заняла» (при продолжении проверки складывается)
        # время по этапам: куда уходят часы проверки (обход, картинки, телефон, скорость...) - в журнал и meta timings
        times, mark = {}, [t_run]

        def lap(name):
            now = time.time()
            times[name] = times.get(name, 0) + now - mark[0]
            mark[0] = now
        from .. import VERSION
        if not self.store.get_meta("app_version"):  # при продолжении проверки — версия, которой её начали
            self.store.set_meta("app_version", VERSION)
        self.log(f"Проверка SSL-сертификатов: {self.fetcher.ssl_backend}")
        resumed = self.store.seen(self.start)
        if not resumed:
            self.store.set_meta("started_at", time.strftime("%Y-%m-%d %H:%M:%S"))
            if self.list_urls is None:
                try:
                    self.check_access()   # главная не открылась - почему (crawler/access.py)
                except Exception as e:
                    self.log("   Выяснить, почему сайт не открывается, не удалось: " + str(e)[:100])
            self.log("\nШаг 1 из 4. Читаю robots.txt - правила сайта для поисковых роботов.")
            self.robots_for(self.start, verbose=True)
            try:
                self.check_mirrors()
            except Exception as e:
                self.log("   Склейку домена проверить не удалось: " + str(e)[:100])
            if self.list_urls is not None:  # «Мой список адресов»: в очередь сразу все адреса списка
                for u in self.list_urls:
                    self.consider(u, 0, "")
            else:
                self.store.enqueue(self.start, 0, True, "page", "")
            try:
                regions = [] if self.partial else self.find_regions()
            except Exception as e:
                regions = []
                self.log("   Города найти не удалось: " + str(e)[:120])
            if self.stopped():   # «Остановить» во время поиска городов: sitemap уже не читаем
                pass
            elif cfg.use_sitemap:
                self.log("\nШаг 2 из 4. Читаю sitemap - список страниц, который сайт отдаёт поисковикам.")
                self.load_sitemaps()
                for r in regions:
                    if not r["main"] and U.host_of(r["url"]) != self.root_host:
                        self.load_sitemaps(r["url"])
            else:
                self.log("\nШаг 2 из 4. Sitemap пропускаю (выключено в настройках).")
        else:
            self.apply_regions(self.store.get_meta("regions", None) or [])
            self.log("\nПродолжаю прерванный обход с того места, где он остановился.")
            self.store.db.execute("UPDATE urls SET state='queued' WHERE state='fetching'")
            self._ext_files()  # фото с других сайтов сверх выборки — из очереди
            if self.cfg.check_external:
                self._ext_links()  # и ссылки на другие сайты сверх выборки
        self.store.commit()
        lap("подготовка: robots.txt, зеркала, города, sitemap")

        if cfg.render_js:
            ok, why = R.available()
            if ok:
                self.log(f"\nВключаю JavaScript: запускаю встроенный браузер Chromium (вкладок: {cfg.render_tabs})...")
                ua = UA_PRESETS.get(cfg.user_agent, cfg.user_agent)
                self.renderer = R.Renderer(ua, tabs=cfg.render_tabs, wait_seconds=cfg.render_wait,
                                           timeout=max(cfg.timeout, 20), robots_check=self.robots_cached)
                if self.renderer.start():
                    self.log("   Браузер запущен. Каждая страница открывается дважды: как простой HTML и в браузере")
                    self.log("   с JavaScript. Это в несколько раз медленнее обычной проверки.")
                else:
                    self.log(f"   Браузер не запустился ({self.renderer.start_error}). Проверяю без JavaScript.")
                    self.renderer = None
            else:
                self.log(f"\nJavaScript включить не получилось: {why}. Проверяю без JavaScript.")
            self.store.set_meta("render_js", bool(self.renderer))
            lap("запуск браузера для JavaScript")

        if self.list_urls is not None:
            self.log(f"\nШаг 3 из 4. Проверяю адреса из списка: {_n(len(self.list_urls))}. По ссылкам на другие "
                     f"страницы сайта не иду, только туда, куда ведут редиректы.")
        elif self.scope_prefix:
            self.log(f"\nШаг 3 из 4. Обхожу только раздел {self.scope_prefix} по ссылкам"
                     + (", с того места, где остановился." if resumed else "."))
            self.log("   Страницы вне раздела не проверяются, ссылки на них не считаются битыми.")
        else:
            self.log("\nШаг 3 из 4. Обхожу сайт по ссылкам" + (", с того места, где остановился." if resumed else ", начиная с главной."))
        self.log("   Вместе со страницами проверяются картинки и внешние ссылки. Если число страниц")
        self.log("   какое-то время стоит на месте, в журнале будет видно, что программа проверяет в это время.")
        pages_done = self.store.count("state='done' AND kind='page' AND internal=1")
        pages_done = self._drain(pages_done, "обход")
        left = self.store.count("state='queued' AND kind='page' AND internal=1")
        lap("обход: страницы, картинки, ссылки")

        if not self.stop_flag and cfg.use_sitemap and not cfg.crawl_sitemap:
            has_sm = self.store.db.execute("SELECT COUNT(*) FROM sitemap").fetchone()[0]
            if has_sm and left == 0:
                n = self.queue_sitemap_check()
                if n:
                    self.log(f"\nШаг 4 из 4. В sitemap есть {_n(n)} {_plural(n, 'адрес', 'адреса', 'адресов')}, "
                             f"на которые при обходе не нашлось ни одной ссылки.")
                    self.log("   Проверяю их отдельно: это забытые страницы или устаревшие адреса." if not self.partial else
                             "   Проверяю их отдельно: нет ли в sitemap ошибок и редиректов.")
                    self._drain(pages_done, "sitemap")
                else:
                    self.log("\nШаг 4 из 4. Все адреса из sitemap уже встретились при обходе - проверять нечего.")
            elif has_sm:
                self.log("\nШаг 4 из 4. Проверку sitemap пропускаю: сайт обойдён не полностью, поэтому")
                self.log("   нельзя сказать, какие страницы из sitemap действительно без ссылок.")
            # часть сайта: страница из sitemap без ссылок из раздела может быть связана с остальным сайтом —
            # «сирот» не ищем
            self.store.set_meta("sitemap_checked", bool(has_sm and left == 0 and not self.partial))
        lap("адреса из sitemap без ссылок")

        # закрытая в robots.txt навигация - и без sitemap: что за ней спрятано (vsekuhni.ru)
        if not self.stop_flag and left == 0 and cfg.respect_robots and not self.partial:
            try:
                self.probe_blocked_pagination()
            except Exception as e:
                self.log("   Проверить закрытую навигацию не удалось: " + str(e)[:120])
            lap("закрытая в robots.txt навигация")

        if not self.stop_flag and cfg.use_search_urls and self.list_urls is None:
            try:
                self.check_search_urls(pages_done, left)
            except Exception as e:
                self.log("   Адреса из Яндекс Вебмастера и Search Console проверить не удалось: " + str(e)[:120])
        lap("адреса из Вебмастера и Search Console")

        if not self.stop_flag:
            try:
                self.check_ua_diff()
            except Exception as e:
                self.log("   Сравнение ответов роботу и браузеру не удалось: " + str(e)[:120])
            lap("роботу и браузеру")
            try:
                self.check_mobile()
            except Exception as e:
                self.log("   Сравнение ответов телефону и компьютеру не удалось: " + str(e)[:120])
            lap("телефону и компьютеру")
            try:
                self.check_mobile_view()
            except Exception as e:
                self.log("   Проверка страниц на телефоне не удалась: " + str(e)[:120])
            lap("страницы на телефоне")
            try:
                self.check_speed_lab()
            except Exception as e:
                self.log("   Замер скорости на телефоне не удался: " + str(e)[:120])
            lap("скорость на телефоне")
            try:
                self.check_og_images()
            except Exception as e:
                self.log("   Проверка картинок для превью ссылок не удалась: " + str(e)[:120])
            lap("картинки для превью ссылок")
            try:
                self.check_dup_variants()
            except Exception as e:
                self.log("   Проверка устойчивости к дублям не удалась: " + str(e)[:120])
            lap("устойчивость к дублям")
            try:
                self.recheck_errors()
                # на страницах, которые открылись со второго раза, могли найтись новые ссылки — обходим их
                if self.store.count("state='queued'") and not self.stop_flag:
                    pages_done = self._drain(pages_done, "после перепроверки")
            except Exception as e:
                self.log("   Перепроверка ошибок не удалась: " + str(e)[:120])
            lap("перепроверка ошибок")
            try:
                self.recheck_js()
                if self.store.count("state='queued'") and not self.stop_flag:
                    pages_done = self._drain(pages_done, "после браузера")
            except Exception as e:
                self.log("   Повторное открытие в браузере не удалось: " + str(e)[:120])
            lap("повторно в браузере")
        # браузер с JavaScript нужен и перепроверке ошибок: раньше он закрывался до неё, и каждая
        # перепроверяемая страница ждала закрытый браузер почти минуту, а данные JavaScript у неё терялись
        if self.renderer:
            self.renderer.stop()
            self.renderer = None
        if not self.stop_flag:
            try:
                self.recheck_slow()
            except Exception as e:
                self.log("   Повторный замер скорости не удался: " + str(e)[:120])
            lap("повторный замер времени ответа")
        self.save_timings(times)
        left = self.store.count("state='queued' AND kind='page' AND internal=1")
        self.store.set_meta("finished_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        self.shaky_meta()
        self.store.set_meta("work_seconds", round(float(self.store.get_meta("work_seconds", 0) or 0) + time.time() - t_run))
        self.store.set_meta("pages_left_in_queue", left)
        # с каких чужих сайтов фото проверены выборкой: {сайт: [проверено, не открывали]} — для отчёта
        self.store.set_meta("ext_files_sample", {h: v[:2] for h, v in self._ext_files().items() if v[1]})
        self.store.set_meta("ext_links_sample", self.ext_links_sample())
        self.store.set_meta("max_pages", cfg.max_pages)
        self.store.commit()
        self.log("")
        if getattr(self, "site_down", None):
            self.log(f"Обход прекращён: сайт перестал отвечать. Проверено страниц: {_n(pages_done)}, "
                     f"ещё ждут проверки: {_n(left)}.")
        elif getattr(self, "low_mem", None) is not None:
            self.log(f"Обход остановлен: мало памяти компьютера. Проверено страниц: {_n(pages_done)}, "
                     f"ещё ждут проверки: {_n(left)}.")
        elif self.stop_flag:
            self.log(f"Обход остановлен вручную. Проверено страниц: {_n(pages_done)}, ещё ждут проверки: {_n(left)}.")
        elif left:
            self.log(f"Обход дошёл до лимита: проверено {_n(pages_done)} {_plural(pages_done, 'страница', 'страницы', 'страниц')}, "
                     f"ещё {_n(left)} {_plural(left, 'ждёт', 'ждут', 'ждут')} в очереди.")
        else:
            self.log(f"Обход закончен: сайт обойдён целиком, страниц - {_n(pages_done)}.")
        return pages_done
