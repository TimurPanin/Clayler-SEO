"""Дополнительные проходы после обхода: склейка домена, закрытая навигация, устойчивость к дублям, роботу/браузеру, перепроверка ошибок и скорости."""
import re
import time
from .. import mirror_copy, urls as U
from ..fetcher import Fetcher, UA_PRESETS
from ..parser import parse_html
from .common import _n, _plural


class ExtraPassesMixin:
    # ---------- склейка домена: все варианты адреса должны одним 301 вести на главный
    def _get(self, url, **kw):
        """Загрузка для дополнительных проверок. Сертификат не прошёл проверку - берём без проверки, как обход
        (crawler/page.py): сам сертификат - отдельная проблема, а склейка, 404, служебные файлы и остальное
        должны проверяться как обычно, а не пропадать или дублировать ошибку SSL (timurpanin.ru)."""
        r = self.fetcher.fetch(url, **kw)
        if r.error.startswith("SSL: ошибка сертификата"):
            r2 = self.insecure.fetch(url, **kw)
            if not r2.error:
                r2.ssl_note = "Сертификат не прошёл проверку, но сайт отвечает"
                return r2
        return r

    def _follow(self, url, max_hops=6):
        from urllib.parse import urljoin
        chain = []
        for _ in range(max_hops):
            self.limiter.wait()
            r = self._get(url, read_body=False)
            chain.append([url, r.status or r.error])
            if r.error or not (300 <= r.status < 400) or not r.location:
                break
            nxt = urljoin(url, r.location)
            if nxt in (c[0] for c in chain):
                chain.append([nxt, "цикл"])
                break
            url = nxt
        return chain

    def check_exposed(self, main, bare):
        """Открытые служебные файлы: копия кода (.git), пароли (.env), архивы и дампы базы. Файл считается
        найденным, только если его содержимое похоже на настоящее (иначе «200 на всё» дало бы ложную тревогу)."""
        base = main.rstrip("/")
        name = bare.split(".")[0]
        text = lambda b: b[:2000].decode("utf-8", "replace")
        not_html = lambda b: not re.search(r"<(html|body|head|!doctype)", text(b), re.I)
        probes = [
            ("/.git/HEAD", "копия кода сайта (.git)", lambda b: re.match(r"(ref: refs/|[0-9a-f]{40})", text(b))),
            ("/.git/config", "копия кода сайта (.git)", lambda b: "[core]" in text(b)),
            ("/.svn/entries", "копия кода сайта (.svn)", lambda b: not_html(b) and re.match(r"\d+\s", text(b))),
            ("/.env", "файл с паролями и ключами (.env)",
             lambda b: not_html(b) and len(re.findall(r"(?m)^[A-Z][A-Z0-9_]*=", text(b))) >= 2),
            ("/.htpasswd", "пароли доступа (.htpasswd)", lambda b: not_html(b) and re.match(r"[\w.-]+:\S{6,}", text(b))),
            ("/.DS_Store", "список файлов папки (.DS_Store)", lambda b: b[4:8] == b"Bud1"),
            ("/phpinfo.php", "настройки сервера (phpinfo)", lambda b: "phpinfo()" in text(b) and "PHP Version" in text(b)),
        ]
        for fn in ("backup.zip", "site.zip", "www.zip", f"{name}.zip", f"{bare}.zip", "backup.tar.gz", "site.tar.gz",
                   f"{name}.tar.gz"):
            probes.append((f"/{fn}", "архив сайта (бэкап)", lambda b: b[:4] == b"PK\x03\x04" or b[:2] == b"\x1f\x8b"))
        for fn in ("dump.sql", "db.sql", "database.sql", "backup.sql", f"{name}.sql"):
            probes.append((f"/{fn}", "дамп базы данных",
                           lambda b: not_html(b) and re.search(r"CREATE TABLE|INSERT INTO|-- MySQL dump", text(b), re.I)))
        found = []
        for path, what, ok in probes:
            if self.stopped():
                break
            self.limiter.wait()
            binary = path.endswith((".zip", ".gz", ".DS_Store"))
            r = (self._get(base + path, read_body=False, peek=64) if binary
                 else self._get(base + path, any_type=True))
            if r.status == 200 and r.body and ok(r.body):
                found.append({"url": base + path, "what": what})
        if found:
            self.log(f"   ВНИМАНИЕ: открыты служебные файлы: {len(found)}")
        return {"checked": len(probes), "found": found}

    def check_mirrors(self):
        from urllib.parse import urlsplit
        # склейку смотрим по главной: адрес проверки может быть разделом (site.ru/catalog/) или первым адресом списка
        main_chain = self._follow("/".join(self.start.split("/", 3)[:3]) + "/")
        main = main_chain[-1][0]
        sp = urlsplit(main)
        host = sp.hostname or ""
        bare = host[4:] if host.startswith("www.") else host
        hosts = [bare, "www." + bare]
        port = f":{sp.port}" if sp.port else ""
        variants = []
        for scheme in ("https", "http"):
            for h in hosts:
                u = f"{scheme}://{h}{port}/"
                if u != main:
                    variants.append(u)
        variants += [main + "index.php", main + "index.html"]
        out = []
        for v in variants:
            chain = self._follow(v)
            # 502-504 без редиректа, а такого адреса нет в DNS - ответил прокси (VPN), а не сайт: варианта нет
            # (www.127.0.0.1 и несуществующий www у сайта под VPN давали ложное «перенаправляет неправильно»)
            if len(chain) == 1 and chain[0][1] in (502, 503, 504):
                import socket
                from urllib.parse import urlsplit
                try:
                    socket.getaddrinfo(urlsplit(v).hostname, None)
                except OSError:
                    chain = [[v, "нет в DNS (ответил прокси)"]]
            item = {"variant": v, "chain": chain}
            if chain[0][1] == 200:  # открылся сам: указан ли canonical на главный адрес (тогда это не копия)
                self.limiter.wait()
                r = self._get(v)
                m = re.search(r"<link[^>]+rel=[\"']?canonical[\"']?[^>]*href=[\"']?([^\"' >]+)|"
                              r"<link[^>]+href=[\"']?([^\"' >]+)[\"']?[^>]*rel=[\"']?canonical",
                              (r.body or b"")[:300_000].decode("utf-8", "replace"), re.I)
                item["canonical"] = (m.group(1) or m.group(2)) if m else ""
            out.append(item)
        self.store.set_meta("mirrors", {"main": main, "variants": out})
        # Несуществующая страница: сервер должен ответить 404/410, а не 200 или редиректом на главную
        import random
        fake = main.rstrip("/") + f"/clayler-test-404-{random.randint(100000, 999999)}/"
        f404 = {"url": fake, "chain": self._follow(fake)}
        if f404["chain"] and f404["chain"][-1][1] == 200:   # «не найдено» с кодом 200: запомнить, как она выглядит,
            try:                                            # чтобы найти такие же страницы среди обычных (мягкие 404)
                self.limiter.wait()
                rb = self._get(f404["chain"][-1][0])
                pt = parse_html(rb.body or b"", rb.headers.get("content-type", ""))
                f404["title"] = (pt["titles"] or [""])[0][:300]
                f404["h1"] = " | ".join(pt["h1"])[:300]
            except Exception as e:   # без title и H1 не найдётся «сайт на любой адрес отдаёт главную»
                self.log(f"   Несуществующая страница не разобралась: {str(e)[:120]}")
        self.store.set_meta("fake404", f404)
        # Ответ 304: если сервер отдаёт Last-Modified или ETag, на повторный запрос «изменилась ли?» он должен
        # ответить 304 — тогда Яндекс не перекачивает страницы зря
        try:
            import urllib.request, urllib.error
            r0 = self._get(main, read_body=False)
            lm, et = r0.headers.get("last-modified", ""), r0.headers.get("etag", "")
            res304 = {"url": main, "last_modified": lm, "etag": et, "status": None}
            if lm or et:
                h = {"User-Agent": self.fetcher.user_agent}
                if lm:
                    h["If-Modified-Since"] = lm
                if et:
                    h["If-None-Match"] = et
                try:
                    resp = self.fetcher.opener.open(urllib.request.Request(main, headers=h), timeout=self.cfg.timeout)
                    res304["status"] = resp.status
                    resp.close()
                except urllib.error.HTTPError as e:
                    res304["status"] = e.code
            self.store.set_meta("check304", res304)
        except Exception as e:
            self.store.set_meta("check304", {"url": main, "error": str(e)[:120]})
        if self.cfg.check_exposed:
            self.store.set_meta("exposed", self.check_exposed(main, bare))
        # Срок SSL-сертификата
        if sp.scheme == "https":
            try:
                import socket, ssl
                try:   # как в fetcher.py: проверка средствами Windows, как браузер (докачивает промежуточные)
                    import truststore
                    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                except Exception:
                    ctx = ssl.create_default_context()
                with socket.create_connection((host, sp.port or 443), timeout=self.cfg.timeout) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host) as ss:
                        na = ss.getpeercert().get("notAfter")
                if na:
                    days = int((ssl.cert_time_to_seconds(na) - time.time()) // 86400)
                    self.store.set_meta("cert", {"host": host, "not_after": na, "days_left": days})
            except Exception as e:
                self.store.set_meta("cert", {"host": host, "error": str(e)[:120]})
        bad = 0
        for m in out:
            ch = m["chain"]
            last = ch[-1]
            if len(ch) == 2 and ch[0][1] in (301, 308) and last[0] == main and last[1] == 200:
                continue
            if isinstance(ch[0][1], int) and ch[0][1] in (404, 410) and len(ch) == 1:
                continue
            if not isinstance(ch[0][1], int):
                continue  # не открывается вовсе (нет www в DNS) — не ошибка
            bad += 1
        self.log(f"   Склейка домена: проверено вариантов адреса - {len(out)}, "
                 + ("все ведут на главный адрес одним 301." if not bad else f"с замечаниями - {bad} (подробно в отчёте)."))

    # ---------- закрытая в robots.txt постраничная навигация
    _PAGER_KEYS = re.compile(r"^(pagen_\d+|page|p|pg|paged|pagenum|start|offset|from|nav|pn)$", re.I)
    _PAGER_PATH = re.compile(r"/(page|p|str|stranitsa)[-/_]?\d+/?$", re.I)

    def _is_pager(self, url):
        from urllib.parse import urlsplit, parse_qsl
        sp = urlsplit(url)
        keys = [k for k, _ in parse_qsl(sp.query, keep_blank_values=True)]
        if keys:
            return all(self._PAGER_KEYS.match(k) for k in keys)
        return bool(self._PAGER_PATH.search(sp.path))

    def probe_blocked_pagination(self, limit=3000, hidden_max=20000):
        """Сироты из sitemap часто на самом деле стоят в списках на 2-й, 3-й… странице каталога, а постраничная
        навигация закрыта в robots.txt — поэтому по открытым ссылкам до них не дойти (и поисковику тоже).
        Открываем только такие закрытые страницы навигации, ничего с них не обходим, а лишь записываем,
        на какие сироты они ссылаются (связь kind='via_blocked').
        С 30.10.2026 и без sitemap (vsekuhni.ru: sitemap нет, Disallow: /*PAGEN): адреса со страниц навигации,
        которых обход не встретил вовсе и которых нет в sitemap, - поисковик их не находит. Они не открываются,
        список - в meta «blocked_probe» (hidden: [адрес, где стоит ссылка])."""
        self.st(step="Проверяю закрытую в robots.txt навигацию")
        orphans = {r[0] for r in self.store.db.execute(
            "SELECT u.url FROM urls u JOIN pages p ON p.url=u.url WHERE u.kind='sitemap' AND p.status=200")}
        todo = [r[0] for r in self.store.db.execute(
            "SELECT url FROM urls WHERE state='skipped' AND internal=1 AND skip_reason LIKE 'Закрыт в robots%'")
                if self._is_pager(r[0])]
        if not todo:
            return 0, 0
        self.log(f"\n   Постраничная навигация (каталог, стр. 2, 3, 4…) закрыта в robots.txt: робот не видит ссылки на ней.")
        self.log(f"   Проверяю такие закрытые страницы (найдено {_n(len(todo))}, открою не больше {_n(limit)}): "
                 "только смотрю ссылки, в отчёт как страницы они не попадут.")
        seen, found, opened = set(todo), set(), 0
        hidden, n_hidden = {}, set()   # адрес → закрытая страница навигации (первые hidden_max); все адреса
        # адреса из sitemap поисковик знает, даже если в проверку они не попали (лимит страниц)
        in_sm = {r[0] for r in self.store.db.execute("SELECT url FROM sitemap")}
        from concurrent.futures import ThreadPoolExecutor as TPE
        with TPE(max_workers=self.cfg.threads) as pool:
            while todo and opened < limit and not self.stop_flag:
                if self.stopped():
                    break
                self.st(pages=opened, limit=min(limit, opened + len(todo)), unit="probe")
                k = min(self.cfg.threads * 4, limit - opened)
                batch, todo = todo[:k], todo[k:]

                def get(u):
                    self.limiter.wait()
                    return u, self._get(u, read_body=True)
                results = list(pool.map(get, batch))
                for u, r in results:
                    opened += 1
                    if r.status != 200 or not r.is_html or not r.body:
                        continue
                    ph = parse_html(r.body, r.headers.get("content-type", ""))
                    base = U.normalize(ph["base"], u) if ph["base"] else u
                    rows = []
                    # nofollow - как при обходе (crawler/page.handle): по таким ссылкам обход не шёл, и «не нашёл»
                    # тут не значит «поисковик не найдёт» (кнопки «в сравнение» Битрикса)
                    bot = "yandex" if self.cfg.robots_for.startswith("yandex") else "googlebot"
                    rmeta = " ".join(c for nm, c in ph["robots"] if nm in ("robots", bot))
                    page_nofollow = ("nofollow" in rmeta or "none" in rmeta) and not self.cfg.follow_nofollow
                    for a in ph["links"]:
                        n = U.normalize(a["href"], base)
                        if not n:
                            continue
                        if self.cfg.strip_tracking and U.same_site(n, self.root_host, True):
                            n = U.strip_params(n, self.clean_rules(n))[0]   # как при обходе (crawler/page.py)
                        if n in orphans:
                            rows.append((u, n, a["href"][:500], a["anchor"][:300], int(a["nofollow"]), "via_blocked", 1))
                            found.add(n)
                            continue
                        if page_nofollow or (a["nofollow"] and not self.cfg.follow_nofollow):
                            continue
                        if n in seen or not U.same_site(n, self.root_host, self.cfg.crawl_subdomains):
                            continue
                        seen.add(n)   # меню и подвал повторяются на всех страницах - каждый адрес смотрим один раз
                        if n in in_sm or self.store.seen(n) or U.is_file_url(n) or not self.in_scope(n) \
                                or mirror_copy.is_twin(n, self.twin_host()):
                            continue
                        why = self.skip_reason(n, 0)   # те же правила, что при обходе (crawler/queue.consider)
                        if why and why.startswith("Закрыт в robots") and self._is_pager(n):
                            todo.append(n)
                            # это тоже закрытый адрес — пусть будет в списке «закрыто в robots.txt»
                            self.store.enqueue(n, 99, True, "page", u, "skipped", why)
                        elif not why and not self._is_pager(n):
                            n_hidden.add(n)
                            if len(hidden) < hidden_max:
                                hidden[n] = u
                    self.store.add_links(rows)
                self.store.commit()
                if opened % 100 < self.cfg.threads * 4:
                    self.log(f"   Закрытых страниц навигации открыто: {_n(opened)}, на них сирот из sitemap: {_n(len(found))}, "
                             f"страниц, которых нет ни в ссылках сайта, ни в sitemap: {_n(len(n_hidden))}")
        self.store.set_meta("blocked_probe", {"opened": opened, "found": len(found), "orphans": len(orphans),
                                              "hidden": [[k, v] for k, v in hidden.items()], "hidden_total": len(n_hidden)})
        self.log(f"   Итог: открыто {_n(opened)} закрытых страниц навигации."
                 + (f" Из {_n(len(orphans))} сирот sitemap {_n(len(found))} стоят на них." if orphans else "")
                 + (f" Страниц, ссылки на которые есть только там (поисковик их не находит): {_n(len(n_hidden))}." if n_hidden else ""))
        return opened, len(found)

    # ---------- устойчивость к дублям: «испорченные» варианты настоящих адресов
    def check_dup_variants(self, n_pages=15):
        """Каждый вариант должен дать 301 на настоящий адрес, 404 или canonical на настоящий адрес.
        Если открывается сам по себе (200 без canonical на оригинал) — это дубль страницы."""
        import random
        from urllib.parse import urlsplit, urlunsplit, urljoin
        rows = [r[0] for r in self.store.db.execute(
            "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE p.status=200 AND p.indexable=1 "
            "AND p.content_type IN ('text/html','application/xhtml+xml') AND u.depth>=1 AND u.internal=1 "
            "AND u.kind='page' AND p.url NOT LIKE '%?%' ORDER BY p.url")]  # порядок не зависит от потоков обхода
        if not rows:
            return
        self.st(step="Проверяю устойчивость к дублям")
        random.Random(1).shuffle(rows)
        # по страницам из разных разделов
        seen_sec, pick = set(), []
        for u in rows:  # сначала по одной странице из каждого раздела
            sec = urlsplit(u).path.strip("/").split("/")[0]
            if sec not in seen_sec:
                seen_sec.add(sec)
                pick.append(u)
        pick = pick[:n_pages]
        for u in rows:  # потом добираем до n_pages
            if len(pick) >= n_pages:
                break
            if u not in pick:
                pick.append(u)
        self.log(f"\n   Проверяю устойчивость к дублям: {len(pick)} страниц, у каждой - несколько «испорченных» адресов.")
        out = []
        for u in pick:
            if self.stopped():
                break
            sp = urlsplit(u)
            path = sp.path
            variants = []
            if any(c.isalpha() and c.isascii() for c in path):
                variants.append(("заглавные буквы", path.upper()))
            segs = path.strip("/").split("/")
            if len(segs) >= 2:
                variants.append(("двойной слеш", "/" + segs[0] + "//" + "/".join(segs[1:]) + ("/" if path.endswith("/") else "")))
            variants.append(("без слеша в конце" if path.endswith("/") else "слеш в конце",
                             path[:-1] if path.endswith("/") else path + "/"))
            if path.endswith("/"):
                variants.append(("index.php", path + "index.php"))
            variants.append(("лишний параметр", path + ("&" if sp.query else "?") + "clayler=1"))
            for kind, vpath in variants:
                if kind == "лишний параметр":
                    v = urlunsplit((sp.scheme, sp.netloc, path, "clayler=1", ""))
                else:
                    v = urlunsplit((sp.scheme, sp.netloc, vpath, sp.query, ""))
                if not self.pace(0.3):
                    break
                r = self._get(v, read_body=True)
                verdict, detail = "ok", ""
                if r.error:
                    verdict, detail = "?", r.error
                elif 300 <= r.status < 400:
                    loc = U.normalize(urljoin(v, r.location)) if r.location else ""
                    if loc != u:
                        # один шаг дальше: бывает редирект через промежуточный адрес
                        r2 = self._get(loc, read_body=False) if loc else None
                        loc2 = U.normalize(urljoin(loc, r2.location)) if r2 is not None and r2.location else ""
                        if loc2 != u:
                            verdict, detail = "bad", f"редирект {r.status} на {loc or '-'}"
                        else:
                            detail = f"через 2 редиректа"
                elif r.status == 200:
                    canon = ""
                    if r.is_html and r.body:
                        ph = parse_html(r.body, r.headers.get("content-type", ""))
                        if ph["canonicals"]:
                            canon = U.normalize(ph["canonicals"][0], v) or ""
                    if canon != u:
                        verdict = "bad"
                        detail = "открывается (200), canonical " + (f"на {canon}" if canon else "не указан")
                    else:
                        detail = "200, но canonical на настоящий адрес - нормально"
                elif r.status in (404, 410, 400):
                    detail = f"{r.status}"
                else:
                    verdict, detail = "?", f"{r.status}"
                out.append({"url": u, "kind": kind, "variant": v, "status": r.status or r.error,
                            "verdict": verdict, "detail": detail})
        self.store.set_meta("dup_variants", out)
        bad = sum(1 for x in out if x["verdict"] == "bad")
        self.log(f"   Итог: проверено вариантов {len(out)}, открываются как отдельные страницы - {bad}.")

    # ---------- картинки Open Graph: открываются ли и не слишком ли маленькие (превью ссылки в мессенджерах)
    def check_og_images(self, limit=25):
        """Самые частые картинки og:image (обычно одна-две из шаблона и по одной на товар): код ответа, тип и размер.
        Если такая картинка уже проверялась при обходе — берём результат оттуда."""
        import json
        from collections import Counter
        from urllib.parse import urljoin
        from ..imgsize import image_info
        cnt, raw_of = Counter(), {}
        for url, og in self.store.db.execute(
                "SELECT p.url, p.og FROM pages p JOIN urls u ON u.url=p.url WHERE p.status=200 AND u.internal=1 "
                "AND u.kind='page' AND p.og IS NOT NULL AND p.og<>'{}'"):
            try:
                src = (json.loads(og).get("og:image") or "").strip()
            except ValueError:
                continue
            if not src:
                continue
            full = U.normalize(src, url) or src
            cnt[full] += 1
            raw_of.setdefault(full, src)
        if not cnt:
            return
        self.st(step="Проверяю картинки для превью ссылок (Open Graph)")
        out = []
        for img, n in cnt.most_common(limit):
            if self.stopped():
                break
            row = {"url": img, "pages": n, "relative": not raw_of[img].lower().startswith(("http://", "https://", "//"))}
            known = self.store.db.execute("SELECT status, error, content_type, img_width, img_height, size FROM pages "
                                          "WHERE url=?", (img,)).fetchone()
            if known and known[0] == 200 and known[3]:
                row.update(status=200, type=known[2] or "", w=known[3], h=known[4], size=known[5])
            else:
                u = img
                for _ in range(4):  # редиректы — до конца
                    self.pace(0.2)
                    r = self._get(u, read_body=False, peek=65536)
                    if r.status and 300 <= r.status < 400 and r.location:
                        u = urljoin(u, r.location)
                        continue
                    break
                fmt, w, h = image_info(r.body or b"", r.content_type) if r.status == 200 else ("", None, None)
                row.update(status=r.status or r.error, type=r.content_type or "", w=w, h=h,
                           size=int(r.headers.get("content-length") or 0) or None, final=u if u != img else "")
            out.append(row)
        self.store.set_meta("og_images", out)
        bad = sum(1 for x in out if x.get("status") != 200)
        self.log(f"   Картинки для превью (og:image): проверено {len(out)}, не открываются - {bad}.")

    # ---------- роботу и браузеру отдаётся разное?
    def _sample_pages(self, n_pages):
        """Страницы для выборочных проверок: три самые близкие к главной и случайные из первых 300 (всегда одни и те же)."""
        from ..mobile_view import sample_pages
        return sample_pages(self.store.db, n_pages)

    def check_ua_diff(self, n_pages=10):
        """Каждую страницу открываем: как робот, как браузер Chrome, снова как робот. Различие засчитываем, только если
        оба «роботских» ответа совпали, а «браузерный» отличается, — так случайное содержимое не даёт ложных тревог."""
        from urllib.parse import urlsplit
        pick = self._sample_pages(n_pages)
        if not pick:
            return
        self.st(step="Сравниваю, что сайт отдаёт роботу и браузеру")
        browser = Fetcher(UA_PRESETS["chrome"], timeout=self.cfg.timeout, verify_ssl=self.cfg.verify_ssl,
                          total_timeout=self.cfg.total_timeout)
        browser.extra_headers = {"Accept-Language": "ru-RU,ru;q=0.9"}
        browser.host_headers.update(self.auth or {})
        # сертификат не прошёл проверку: обход берёт страницы без проверки (crawler/page.py), так же открываем
        # и как браузер - иначе каждая страница «отличается» ошибкой SSL (timurpanin.ru), а сам
        # сертификат и так отдельная проблема
        browser_insecure = Fetcher(UA_PRESETS["chrome"], timeout=self.cfg.timeout, verify_ssl=False,
                                   total_timeout=self.cfg.total_timeout)
        browser_insecure.extra_headers = dict(browser.extra_headers)
        browser_insecure.host_headers.update(self.auth or {})
        no_check = {self.fetcher: self.insecure, browser: browser_insecure}

        def snap(f, u):
            self.pace(0.3)
            r = f.fetch(u, read_body=True)
            if r.error.startswith("SSL: ошибка сертификата"):
                r = no_check[f].fetch(u, read_body=True)
            if r.error or not r.body or not r.is_html:
                return {"status": r.status or r.error}
            ph = parse_html(r.body, r.headers.get("content-type", ""))
            img_hosts = sorted({urlsplit(U.normalize(i["src"], u) or "").hostname or "" for i in ph["images"]} - {""})
            return {"status": r.status, "title": (ph["titles"] or [""])[0], "h1": (ph["h1"] or [""])[0],
                    "canonical": U.normalize(ph["canonicals"][0], u) if ph["canonicals"] else "",
                    "robots": "; ".join(f"{n}: {c}" for n, c in ph["robots"]),
                    "img_hosts": ", ".join(img_hosts), "links": len(ph["links"])}
        out = []
        labels = {"status": "код ответа", "title": "title", "h1": "H1", "canonical": "canonical",
                  "robots": "meta robots", "img_hosts": "адреса картинок (домены)", "links": "число ссылок"}
        for u in pick:
            if self.stopped():
                break
            a, b, a2 = snap(self.fetcher, u), snap(browser, u), snap(self.fetcher, u)
            for k in labels:
                va, vb, va2 = a.get(k), b.get(k), a2.get(k)
                if k == "links":
                    if va is None or vb is None or va2 is None or abs(va - va2) > 0.05 * max(va, 1):
                        continue
                    if abs(va - vb) <= 0.2 * max(va, vb, 1):
                        continue
                elif va != va2 or va == vb:
                    continue
                out.append({"url": u, "field": labels[k], "bot": va, "browser": vb})
        self.store.set_meta("ua_diff", {"checked": len(pick), "diffs": out})
        self.log(f"   Сравнил ответы роботу и браузеру на {len(pick)} страницах: различий - {len(out)}.")

    # ---------- телефону и компьютеру отдаётся одно и то же?
    def check_mobile(self, n_pages=20):
        """Каждую страницу открываем как Chrome на компьютере, как Chrome на телефоне и снова как компьютер. Отличие
        засчитываем, только если оба «компьютерных» ответа совпали. Редиректы проходим до конца: так видно, что
        телефон уводят на отдельный мобильный адрес (m.сайт), и проверяем, правильно ли он связан с основным."""
        from urllib.parse import urljoin, urlsplit
        pick = self._sample_pages(n_pages)
        if not pick:
            return
        self.st(step="Сравниваю, что сайт отдаёт телефону и компьютеру")
        mk = lambda ua: Fetcher(ua, timeout=self.cfg.timeout, verify_ssl=self.cfg.verify_ssl,
                                total_timeout=self.cfg.total_timeout, extra_headers={"Accept-Language": "ru-RU,ru;q=0.9"})
        desk, phone = mk(UA_PRESETS["chrome"]), mk(UA_PRESETS["phone"])
        for f in (desk, phone):
            f.host_headers.update(self.auth or {})

        def snap(f, u):
            for _ in range(6):
                self.pace(0.3)
                r = f.fetch(u, read_body=True)
                if r.error or not (300 <= r.status < 400) or not r.location:
                    break
                u = urljoin(u, r.location)
            if r.error or not r.body or not r.is_html:
                return {"final": u, "status": r.status or r.error}
            ph = parse_html(r.body, r.headers.get("content-type", ""))
            return {"final": u, "status": r.status, "title": (ph["titles"] or [""])[0], "h1": (ph["h1"] or [""])[0],
                    "canonical": U.normalize(ph["canonicals"][0], u) if ph["canonicals"] else "",
                    "robots": "; ".join(f"{n}: {c}" for n, c in ph["robots"]),
                    "viewport": ph["viewport"] or "нет", "words": ph["word_count"], "links": len(ph["links"]),
                    "alt_media": [U.normalize(h, u) for _, h in ph["alt_media"]],
                    "vary": r.headers.get("vary", "").lower()}
        labels = {"status": "код ответа", "final": "адрес после редиректов", "title": "title", "h1": "H1",
                  "canonical": "canonical", "robots": "meta robots", "viewport": "meta viewport",
                  "words": "слов на странице", "links": "число ссылок"}
        diffs, msite, no_vary = [], [], 0
        for u in pick:
            if self.stopped():
                break
            a, m, a2 = snap(desk, u), snap(phone, u), snap(desk, u)
            if a["final"] == a2["final"] and m["final"] != a["final"]:
                # отдельная мобильная версия: содержимое не сравниваем, проверяем, как связаны адреса
                murl, durl = m["final"], a["final"]
                bad = []
                if m["status"] != 200:
                    bad.append(f"мобильный адрес отвечает {m['status']}")
                if urlsplit(murl).path in ("", "/") and urlsplit(durl).path not in ("", "/"):
                    bad.append("телефон попадает на главную, а не на эту же страницу")
                if a["status"] == 200 and murl not in a.get("alt_media", []):
                    bad.append('на основной странице нет <link rel="alternate" media=…> на мобильный адрес')
                if m["status"] == 200 and m.get("canonical") != durl:
                    bad.append("canonical мобильной страницы не ведёт на основную"
                               + (f" (ведёт на {m['canonical']})" if m.get("canonical") else " (его нет)"))
                msite.append({"url": durl, "mobile": murl, "problems": bad})
                continue
            changed = False
            for k in labels:
                va, vm, va2 = a.get(k), m.get(k), a2.get(k)
                if k in ("words", "links"):
                    if va is None or vm is None or va2 is None or abs(va - va2) > 0.05 * max(va, 1):
                        continue
                    if abs(va - vm) <= 0.2 * max(va, vm, 1):
                        continue
                elif va != va2 or va == vm:
                    continue
                changed = True
                diffs.append({"url": u, "field": labels[k], "desktop": va, "phone": vm})
            if changed and "user-agent" not in (m.get("vary") or ""):
                no_vary += 1
        self.store.set_meta("mobile_diff", {"checked": len(pick), "diffs": diffs, "msite": msite, "no_vary": no_vary})
        self.log(f"   Сравнил ответы телефону и компьютеру на {len(pick)} страницах: различий - {len(diffs)}"
                 + (f", уводят на отдельный мобильный адрес - {len(msite)}" if msite else "") + ".")

    # ---------- как страницы выглядят на телефоне (встроенный браузер, 375 px)
    def check_speed_lab(self, n_pages=5):
        """Скорость на телефоне с медленным 4G — как PageSpeed, но своим браузером (без ключа Google)."""
        import os
        from .. import mobile_view as MV, speed_lab as SL
        if os.environ.get("CLAYLER_NO_SPEED_LAB") == "1" or not MV.available():
            return
        pick = self._sample_pages(n_pages)
        if not pick:
            return
        self.st(step="Замеряю скорость на телефоне (медленный 4G)")
        self.log(f"\nЗамеряю скорость {len(pick)} страниц как на телефоне с медленным 4G (как PageSpeed)...")
        try:
            rows = SL.measure(pick, log=self.log, stopped=self.stopped)
        except Exception as e:
            self.log("   Замер скорости не получился: " + (str(e).strip().splitlines() or [type(e).__name__])[0][:160])
            return
        self.store.set_meta("speed_lab", {"pages": rows, "profile": "медленный 4G, процессор ×4"})

    def check_mobile_view(self, n_pages=15):
        import os
        from .. import mobile_view as MV
        if os.environ.get("CLAYLER_NO_MOBILE_VIEW") == "1" or not MV.available():
            return
        pick = self._sample_pages(n_pages)
        if not pick:
            return
        self.st(step="Открываю страницы как на телефоне")
        self.log(f"\nСмотрю, как {len(pick)} страниц выглядят на телефоне (ширина экрана {MV.WIDTH} px), и делаю снимки...")
        shots = os.path.join(os.path.dirname(os.path.abspath(self.store_path)), "мобильная")
        try:
            rows = MV.check_pages(pick, shots, log=self.log, stopped=self.stopped)
        except Exception as e:
            msg = str(e).strip().splitlines()[0][:160] if str(e).strip() else type(e).__name__
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                msg = "не скачан браузер Chromium (нужно: python -m playwright install chromium)"
            self.log("   Не получилось открыть страницы в браузере: " + msg)
            return
        res = {"width": MV.WIDTH, "pages": rows}
        if any(r.get("shot") for r in rows) and not self.stopped():   # и главная на компьютере - для карточки сайта
            res["desktop"] = MV._desktop(self.store.get_meta("start", "") or pick[0], shots, self.log)
        self.store.set_meta("mobile_view", res)

    # ---------- перепроверка случайных ошибок
    TRANSIENT = (408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524)   # 408 - с 04.11.2026

    def recheck_errors(self, limit=400):
        """Ошибки сервера (500, 503, 429) и обрывы связи во время обхода часто случайны: сервер устал от
        параллельных запросов самой проверки. Перепроверяем такие адреса по одному, с паузой. Если адрес
        открылся — записываем новый результат, а старая ошибка в отчёт не попадает."""
        self.st(step="Перепроверяю адреса с ошибками")
        q = ",".join(str(c) for c in self.TRANSIENT)
        rows = self.store.db.execute(
            f"""SELECT p.url, u.depth, u.internal, u.kind, p.status, p.error FROM pages p JOIN urls u ON u.url=p.url
                WHERE p.status IN ({q}) OR (p.error<>'' AND (p.error LIKE 'Таймаут%' OR p.error LIKE 'Соединение сброшено%'
                OR p.error LIKE 'Ошибка соединения%' OR p.error LIKE 'Загрузка дольше%' OR p.error LIKE 'Программа не дождалась%'))
                ORDER BY u.internal DESC, u.kind='page' DESC LIMIT ?""", (limit,)).fetchall()
        if not rows:
            return
        self.log(f"\n   Перепроверяю адреса с ошибками сервера и обрывами связи ({_n(len(rows))}) - по одному, с паузой:")
        self.log("   во время обхода сервер мог отвечать с ошибкой из-за нагрузки от самой проверки.")
        fixed, host_fails, skipped = 0, {}, 0
        repeated = {}  # свой адрес, где ошибка повторилась: в отчёте «Ошибки сервера 5xx» - «повторилась»
        for i, row in enumerate(rows, 1):
            url, depth, internal, kind = row[0], row[1], bool(row[2]), row[3]
            host = U.host_of(url)
            # чужой сайт, который и при перепроверке не отвечает дважды, дальше не ждём: на zoozavr.ru
            # 103 ссылки на два медленных сайта перепроверялись по минуте каждая (с повторами), полтора часа
            if not internal and host_fails.get(host, 0) >= 2:
                skipped += 1
                continue
            if not self.pace(1.0):
                break
            try:
                r, parsed = self.work(url, internal, kind, retries=None if internal else 0)
            except Exception:
                continue
            if self.stop_flag:
                break   # «Стоп» во время загрузки: ответ неполный, в «повторилась» его не пишем
            ok = not r.error and r.status and r.status not in self.TRANSIENT
            if not ok and not internal:
                host_fails[host] = host_fails.get(host, 0) + 1
            if not ok and internal:
                repeated[url] = r.status or (r.error or "")[:60]
            if ok:
                fixed += 1
                self.store.forget_page_data(url)
                self.handle(url, depth, internal, kind, r, parsed)
            if i % 25 == 0:
                self.store.commit()
                self.log(f"   Перепроверено: {_n(i)} из {_n(len(rows))}, ошибка оказалась случайной: {_n(fixed)}")
        self.store.set_meta("errors_rechecked", {"checked": len(rows), "fixed": fixed, "limit": limit,
                                                 "repeated": repeated})
        self.store.commit()
        self.log(f"   Итог: из {_n(len(rows))} ошибок случайными оказались {_n(fixed)}, остальные повторились."
                 + (f" Ещё {_n(skipped)} {_plural(skipped, 'ссылку', 'ссылки', 'ссылок')} на сайты, которые не ответили "
                    "и при перепроверке, повторно не открывал." if skipped else ""))

    # ---------- страницы, которые браузер не открыл (полнота отчёта)
    def recheck_js(self, timeout=60, limit=400, give_up=10):
        """Свои страницы, которые открылись (200), а в браузере с JavaScript - нет (не дождался загрузки, сбой
        вкладки): ещё раз по одной, с ожиданием подольше. Без этого для них в отчёте только исходный HTML, а в
        «Что не проверено и почему» их не было (thehome.ru 01.11: 15 страниц, «Timeout 20000ms exceeded»).
        Открылась - новый результат вместо старого; нет - остаётся с ошибкой и попадает в «Что не проверено».
        Не больше limit страниц, как у перепроверки ошибок; give_up подряд не открылись и сейчас - браузер на этом
        сайте не справляется, дальше не ждём по минуте на страницу (ревью)."""
        rd = self.renderer
        if not rd or rd.start_error:
            return
        rows = self.store.db.execute(
            "SELECT p.url, u.depth, u.kind FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND "
            "u.kind IN ('page', 'sitemap') AND p.status=200 AND COALESCE(p.js_error, '')<>'' ORDER BY u.id LIMIT ?", (limit,)).fetchall()
        if not rows:
            return
        self.st(step="Открываю ещё раз страницы, которые браузер не открыл")
        self.log(f"\n   Открываю в браузере ещё раз страницы, которые он не открыл ({_n(len(rows))}) - по одной, "
                 f"ожидание до {timeout} с.")
        old, rd.timeout = rd.timeout, max(rd.timeout, timeout)
        fixed = tried = miss = 0
        try:
            for i, (url, depth, kind) in enumerate(rows, 1):
                if miss >= give_up:
                    self.log(f"   {_n(give_up)} страниц подряд не открылись и сейчас - остальные не открываю.")
                    break
                if not self.pace(0.5):
                    break
                try:
                    r, parsed = self.work(url, True, kind)
                except Exception:
                    continue
                if self.stop_flag:
                    break   # «Стоп» во время загрузки: ответ неполный
                tried += 1
                js = (parsed or {}).get("js")
                miss += 1
                if r.status == 200 and not r.error and js is not None and not js.error:
                    fixed, miss = fixed + 1, 0
                    self.store.forget_page_data(url)
                    self.handle(url, depth, True, kind, r, parsed)
                if i % 25 == 0:
                    self.store.commit()
                    self.log(f"   Открыто ещё раз: {_n(i)} из {_n(len(rows))}, в этот раз открылись: {_n(fixed)}")
        finally:
            rd.timeout = old
        self.store.set_meta("js_rechecked", {"checked": tried, "fixed": fixed})
        self.store.commit()
        self.log(f"   Итог: со второго раза в браузере открылись {_n(fixed)} из {_n(tried)}.")

    # ---------- повторный замер медленных страниц
    def recheck_slow(self, limit=600):
        """Во время обхода сервер нагружен самой проверкой, и одиночный замер бывает случайным.
        Медленные страницы (ответ дольше 1 с) перемеряем по одной, без параллельных запросов."""
        self.st(step="Перемеряю скорость медленных страниц")
        rows = [r[0] for r in self.store.db.execute(
            "SELECT p.url FROM pages p JOIN urls u ON u.url=p.url WHERE u.internal=1 AND p.status=200 "
            "AND p.content_type IN ('text/html','application/xhtml+xml') AND COALESCE(p.ttfb, p.elapsed) > 1 "
            "ORDER BY COALESCE(p.ttfb, p.elapsed) DESC LIMIT ?", (limit,))]
        if not rows:
            return
        self.log(f"\n   Перемеряю скорость ответа у медленных страниц ({_n(len(rows))}) - по одной, без нагрузки на сервер.")
        still = 0
        for i, u in enumerate(rows, 1):
            if not self.pace(0.3):
                break
            self.st(pages=i, limit=len(rows), unit="slow")
            r = self._get(u, read_body=False)
            t = round(r.ttfb, 3) if r.ttfb and not r.error else None
            self.store.db.execute("UPDATE pages SET ttfb_recheck=? WHERE url=?", (t, u))
            if t and t > 1:
                still += 1
            if i % 50 == 0:
                self.store.commit()
                self.log(f"   Перемерено: {_n(i)} из {_n(len(rows))}, по-прежнему медленных: {_n(still)}")
        self.store.set_meta("slow_rechecked", True)
        self.store.commit()
        self.log(f"   Итог: медленными остались {_n(still)} из {_n(len(rows))}.")
