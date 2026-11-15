"""Очередь адресов и robots.txt: что обходить, что пропустить и почему."""
import os
from urllib.parse import urlsplit
from .. import mirror_copy, urls as U
from ..robots import Robots, is_html_page
from .common import _n

# Картинок и файлов с одного чужого сайта (CDN) проверяем столько; если среди них нашлись битые — все.
EXT_FILES_CAP = int(os.environ.get("CLAYLER_EXT_FILES_CAP") or 1000)  # переменная — для автотеста
EXT_SKIP = "Фото или файл с другого сайта"
# Ссылок на один чужой сайт проверяем столько, и столько — на один адрес, который отличается только параметрами.
# На ochkarik.ru кнопки «Поделиться» (vk.com/share.php?url=…, t.me/share?url=…) — своя ссылка на каждой странице,
# 18 тыс. одинаковых проверок; на 1001tur.ru поддомены городов и отелей — 92 тыс. ссылок, проверка шла часами.
EXT_LINKS_CAP = int(os.environ.get("CLAYLER_EXT_LINKS_CAP") or 300)
EXT_PATH_CAP = int(os.environ.get("CLAYLER_EXT_PATH_CAP") or 20)
EXT_LINK_SKIP = "Ссылка на другой сайт"


class QueueMixin:
    # ---------- robots.txt
    def robots_for(self, url, verbose=False):
        p = url.split("/", 3)
        origin = p[0] + "//" + p[2]
        if origin not in self.robots:
            text, status, err = "", 0, ""
            target = origin + "/robots.txt"
            again = 2   # ошибка сервера или обрыв у robots.txt - ещё две попытки с паузой: от него зависит весь обход
            for _ in range(5 + again):
                self.limiter.wait()
                r = self.fetcher.fetch(target, any_type=True)
                if r.error.startswith("SSL: ошибка сертификата"):
                    r = self.insecure.fetch(target, any_type=True)
                status, err = r.status, r.error
                if r.status in (301, 302, 303, 307, 308) and r.location:
                    target = U.normalize(r.location, target) or target
                    continue
                if again and (r.status in (408, 429) or r.status >= 500 or r.retryable) and self.pace(3):
                    again -= 1
                    continue
                if r.status == 200:
                    text = r.body.decode("utf-8", "replace")
                break
            html = is_html_page(text)
            if html:
                text = ""
            token = "yandex" if self.cfg.robots_for.startswith("yandex") else "googlebot"
            rb = self.robots[origin] = Robots(text, token)
            hosts = self.store.get_meta("robots", {})
            # error - для пункта «robots.txt не открывается» (analyze/checks/indexing.py)
            hosts[origin] = {"status": status, "text": text[:20000], "error": err, "html": html}
            self.store.set_meta("robots", hosts)
            if verbose:
                who = "Яндекса" if token == "yandex" else "Google"
                if status == 200:
                    self.log(f"   Найден. Запретов для {who}: {sum(1 for a, _, _ in rb.rules if not a)}, "
                             f"sitemap указано: {len(rb.sitemaps)}, правил Clean-param: {len(rb.clean_params)}.")
                elif status == 404:
                    self.log("   Файла нет (404) - значит, сайт разрешает обходить всё.")
                elif not status or status >= 500 or status == 429:
                    self.log(f"   Не открылся ({status or err}). Обхожу, как будто запретов нет, но Google при такой "
                             "ошибке на время перестаёт обходить весь сайт - в отчёте будет пункт.")
                else:
                    self.log(f"   Не удалось прочитать ({status or err}). Считаю, что запретов нет.")
        return self.robots[origin]

    def clean_rules(self, url):
        if not self.cfg.use_clean_param:
            return None
        return self.robots_for(url).clean_params if U.same_site(url, self.root_host, True) else None

    def twin_host(self):
        """Копия сайта с www или без, которая открывается без редиректа (seocrawler/mirror_copy.py). Узнаём на шаге 1
        (check_mirrors), до первой ссылки; при продолжении проверки - из базы."""
        t = getattr(self, "_twin", None)
        if t is None:
            m = self.store.get_meta("mirrors", None)
            t = mirror_copy.twin_host(m)
            if m is not None:
                self._twin = t
        return t

    # ---------- решение: что делать с найденным URL
    def consider(self, url, depth, found_on, kind_hint="page", follow=False):
        """follow — адрес, куда ведёт редирект или canonical проверяемой страницы: его открываем, даже если
        он вне выбранного раздела или списка (иначе не узнать, куда ведёт страница)."""
        internal = U.same_site(url, self.root_host, self.cfg.crawl_subdomains)
        if self.store.seen(url):
            return
        if not internal:
            # чужой сайт может редиректить сам на себя бесконечно (ozon: ?__rr=1, 2, 3… с растущим адресом) —
            # по цепочке редиректов внутри чужого сайта идём не дальше 5 шагов
            hops, f = 0, found_on
            while f and hops < 6 and not U.same_site(f, self.root_host, self.cfg.crawl_subdomains):
                r = self.store.db.execute("SELECT found_on FROM urls WHERE url=?", (f,)).fetchone()
                f = r[0] if r else None
                hops += 1
            if hops >= 5 or len(url) > 2000:
                self.store.enqueue(url, depth, False, "external", found_on, "skipped",
                                   "Чужой сайт перенаправляет по кругу - дальше не проверяли")
                return
            if kind_hint == "resource" or U.is_file_url(url):  # картинка или файл на другом сайте (CDN)
                why = self.ext_file_skip(url) if self.cfg.check_resources else "Проверка картинок выключена"
                self.store.enqueue(url, depth, False, "resource", found_on, *(("skipped", why) if why else ()))
            elif self.cfg.check_external:
                why = self.ext_link_skip(url)
                self.store.enqueue(url, depth, False, "external", found_on, *(("skipped", why) if why else ()))
            else:
                self.store.enqueue(url, depth, False, "external", found_on, "skipped", "Внешняя ссылка не проверялась")
            return
        kind = kind_hint if kind_hint in ("resource", "sitemap") else "page"
        if kind == "page" and U.is_file_url(url):
            kind = "resource"  # ссылка на картинку или архив (например, «увеличить фото») — это файл, а не страница
        if kind != "resource" and not follow and not self.in_scope(url):
            return  # страница вне раздела или списка: не проверяем и не записываем (иначе попадёт в «пропущенные»)
        if kind == "page" and mirror_copy.is_twin(url, self.twin_host()):
            # копия сайта с www (или без), открытая без редиректа: иначе обходим весь сайт второй раз
            self.store.enqueue(url, depth, True, "page", found_on, "skipped", mirror_copy.SKIP)
            return
        reason = self.skip_reason(url, depth, kind)
        if reason:
            self.store.enqueue(url, depth, True, kind, found_on, "skipped", reason)
        else:
            self.store.enqueue(url, depth, True, kind, found_on)

    def skip_reason(self, url, depth, kind="page"):
        """Почему адрес своего сайта не открываем (None - открываем). Общее для обхода и проверки закрытой
        навигации (extra_passes.probe_blocked_pagination), чтобы правила не расходились."""
        if kind == "resource" and not self.cfg.check_resources:
            return "Проверка картинок выключена"
        # глубина - защита от бесконечных ссылок (календарь, листание без конца). Адрес из sitemap - не ловушка: сайт
        # сам назвал его своей страницей. 05.11.2026: на oidbearing.ru так отбрасывались 50 настоящих карточек товаров
        # из sitemap - цепочка товаров длиннее 50 кликов, а шаг «sitemap без ссылок» уже виденные адреса не открывает
        if depth > self.cfg.max_depth and kind == "page" and not self.store.in_sitemap(url):
            return f"Глубина больше {self.cfg.max_depth}"
        if U.param_count(url) > self.cfg.max_params and kind == "page":
            return f"Больше {self.cfg.max_params} параметров в URL"
        if len(url) > 2000:
            return "URL длиннее 2000 символов"
        if U.has_repetitive_path(url):
            return "Повторяющийся путь (ловушка)"
        if any(rx.search(url) for rx in self.exclude):
            return "Исключён правилом"
        if self.cfg.respect_robots:
            ok, rule = self.robots_for(url).allowed(url)
            if not ok:
                return "Закрыт в robots.txt (" + rule + ")"
        return None

    # ---------- картинки и файлы на других сайтах (CDN): выборка, а не всё подряд
    def _ext_files(self):
        """{сайт: [поставлено в проверку, пропущено, битых]}. На zoozavr.ru фото товаров лежат на detmir.st:
        150 тыс. фото против 20 тыс. страниц, ни одного битого, а проверка шла 10+ часов. При продолжении
        прерванной проверки считается по базе один раз, лишние фото из очереди снимаются (старые проверки
        записывали их как внешние ссылки — узнаём по расширению файла)."""
        d = getattr(self, "_ext_files_d", None)
        if d is not None:
            return d
        d = self._ext_files_d = {}
        rows = self.store.db.execute(
            "SELECT u.url, u.kind, u.state, u.skip_reason, p.status FROM urls u LEFT JOIN pages p ON p.url=u.url "
            "WHERE u.internal=0 AND u.state<>'skipped' OR u.skip_reason LIKE ? ORDER BY u.id",
            (EXT_SKIP + "%",)).fetchall()
        rows = [r for r in rows if r[1] == "resource" or U.is_file_url(r[0])]
        for url, kind, state, reason, status in rows:
            if (status or 0) >= 400:
                d.setdefault(U.host_of(url), [0, 0, 0])[2] += 1
        drop = []
        for url, kind, state, reason, status in rows:
            v = d.setdefault(U.host_of(url), [0, 0, 0])
            if state == "skipped":
                v[1] += 1
                continue
            if state == "queued" and v[0] >= EXT_FILES_CAP and not v[2]:
                drop.append(url)
                v[1] += 1
                continue
            v[0] += 1
        if drop:
            self.store.db.executemany("UPDATE urls SET state='skipped', skip_reason=? WHERE url=?",
                                      [(self._ext_reason(U.host_of(u)), u) for u in drop])
            self.store.commit()
            self.log(f"   Фото и файлы с других сайтов проверяю выборкой ({_n(EXT_FILES_CAP)} с каждого сайта, "
                     f"если среди них нет битых): из очереди снято {_n(len(drop))}.")
        return d

    @staticmethod
    def _ext_reason(host):
        return f"{EXT_SKIP} ({host}): проверены первые {_n(EXT_FILES_CAP)}, остальные не открывали"

    def ext_file_skip(self, url):
        """Причина не проверять картинку с другого сайта (или None — проверить)."""
        host = U.host_of(url)
        v = self._ext_files().setdefault(host, [0, 0, 0])
        if v[0] >= EXT_FILES_CAP and not v[2]:
            v[1] += 1
            return self._ext_reason(host)
        v[0] += 1
        return None

    def ext_file_result(self, url, status):
        """Битая картинка на другом сайте: с этого сайта проверяем всё, и уже отложенные тоже."""
        if (status or 0) < 400:
            return
        host = U.host_of(url)
        v = self._ext_files().setdefault(host, [0, 0, 0])
        v[2] += 1
        if v[1]:
            back = self.store.db.execute("UPDATE urls SET state='queued', skip_reason=NULL WHERE skip_reason=?",
                                         (self._ext_reason(host),)).rowcount
            v[0], v[1] = v[0] + back, 0
            self.log(f"   На {host} нашлась битая картинка - проверяю все картинки оттуда, ещё {_n(back)}.")

    # ---------- ссылки на другие сайты: выборка с каждого сайта
    def _ext_link_keys(self, url):
        """(сайт, сайт+путь без параметров). Поддомены проверяемого сайта (на 1001tur.ru — 72 поддомена городов
        и отелей) — одна выборка на все: обычно это тот же сервер, а не 72 разных сайта."""
        host = U.host_of(url)
        root = getattr(self, "root_host", "")
        root = root[4:] if root.startswith("www.") else root
        key = f"поддомены {root}" if root and host.endswith("." + root) else host
        return key, host + urlsplit(url).path

    def _ext_links(self):
        """[{сайт: поставлено}, {сайт+путь: поставлено}, {сайт: не открывали}]. При продолжении прерванной
        проверки считается по базе один раз, лишние ссылки из очереди снимаются."""
        d = getattr(self, "_ext_links_d", None)
        if d is not None:
            return d
        hosts, paths, skipped = d = self._ext_links_d = ({}, {}, {})
        rows = self.store.db.execute(
            "SELECT url, state, skip_reason FROM urls WHERE internal=0 AND kind='external' AND "
            "(state<>'skipped' OR skip_reason LIKE ?) ORDER BY id", (EXT_LINK_SKIP + "%",)).fetchall()
        drop = []
        for url, state, reason in rows:
            if U.is_file_url(url):
                continue  # фото, записанные старой проверкой как ссылки, — в выборке фото
            h, p = self._ext_link_keys(url)
            if state == "skipped":
                skipped[h] = skipped.get(h, 0) + 1
                continue
            if state == "queued" and (hosts.get(h, 0) >= EXT_LINKS_CAP or paths.get(p, 0) >= EXT_PATH_CAP):
                drop.append((self._ext_link_reason(h, hosts.get(h, 0) >= EXT_LINKS_CAP), url))
                skipped[h] = skipped.get(h, 0) + 1
                continue
            hosts[h] = hosts.get(h, 0) + 1
            paths[p] = paths.get(p, 0) + 1
        if drop:
            self.store.db.executemany("UPDATE urls SET state='skipped', skip_reason=? WHERE url=?", drop)
            self.store.commit()
            self.log(f"   Ссылки на другие сайты проверяю выборкой (до {_n(EXT_LINKS_CAP)} с каждого сайта): "
                     f"из очереди снято {_n(len(drop))}.")
        return d

    @staticmethod
    def _ext_link_reason(host, by_host):
        if by_host:
            return f"{EXT_LINK_SKIP} ({host}): проверены первые {_n(EXT_LINKS_CAP)} ссылок на этот сайт"
        return (f"{EXT_LINK_SKIP} ({host}): такой же адрес, только с другими параметрами, "
                f"проверены первые {_n(EXT_PATH_CAP)}")

    def ext_link_skip(self, url):
        """Причина не проверять ссылку на другой сайт (или None — проверить)."""
        hosts, paths, skipped = self._ext_links()
        h, p = self._ext_link_keys(url)
        if hosts.get(h, 0) >= EXT_LINKS_CAP or paths.get(p, 0) >= EXT_PATH_CAP:
            skipped[h] = skipped.get(h, 0) + 1
            return self._ext_link_reason(h, hosts.get(h, 0) >= EXT_LINKS_CAP)
        hosts[h] = hosts.get(h, 0) + 1
        paths[p] = paths.get(p, 0) + 1
        return None

    def ext_links_sample(self):
        """{сайт: [проверено, не открывали]} — для отчёта."""
        hosts, _, skipped = self._ext_links()
        return {h: [hosts.get(h, 0), n] for h, n in skipped.items() if n}

    # ---------- JavaScript: сравнение исходного HTML и страницы после скриптов
    def robots_cached(self, url):
        """Для браузера: закрыт ли скрипт/стиль в robots.txt. Только для уже прочитанных robots.txt."""
        if not self.cfg.respect_robots:
            return True, ""
        p = url.split("/", 3)
        if len(p) < 3:
            return True, ""
        rb = self.robots.get(p[0] + "//" + p[2])
        return rb.allowed(url) if rb else (True, "")
