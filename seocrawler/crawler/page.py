"""Одна страница: загрузка (с повторами), разбор, запись в базу, сравнение с JavaScript."""
import json
import re
import threading
import time
from .. import urls as U
from .. import extract
from .. import calltrack as CT
from ..parser import parse_html
from ..imgsize import image_info
from ..fetcher import Response
from ..robots import says_none
from .common import retry_after

STOPPED = "Проверка остановлена"   # ответ work() после «Стоп»: главный цикл его уже не ждёт
_JS_NOTE_LOCK = threading.Lock()   # js_state_note из нескольких потоков


class PageMixin:
    # ---------- поток-загрузчик
    def work(self, url, internal, kind, retries=None):
        retries = self.cfg.retries if retries is None else retries
        read = internal and kind in ("page", "sitemap")
        attempt = 0
        lim = self.limiter_for(url, internal, kind)
        # перегрузку своего сервера видно и по картинкам: тормозим и страницы, и файлы
        slow_down = (self.limiter, self.res_limiter) if internal else (lim,)
        r = None
        while True:
            # «Стоп» прерывает и паузу, и повторы: после него к сайту не идёт ни одного нового запроса
            if not lim.wait(lambda: self.stop_flag):
                if r is None:
                    return Response(url=url, error=STOPPED), None
                break
            r = self.fetcher.fetch(url, read_body=read, peek=65536 if internal and kind == "resource" else 0)
            if r.status in (429, 503) and attempt < retries:
                wait_s = retry_after(r.headers.get("retry-after", ""))
                for x in slow_down:
                    x.backoff(wait_s)
            elif r.retryable and attempt < retries:
                # сброс соединения или таймаут: чаще всего сервер просто перегружен
                for x in slow_down:
                    x.backoff(2 * (attempt + 1))
            else:
                break
            attempt += 1
        if url == self.start and r.error.startswith("Соединение сброшено") and retries \
                and not getattr(self, "_start_waited", False) and self._site_answered():
            r = self._start_wait(url, read) or r
        if r.error.startswith("SSL: ошибка сертификата"):
            # Проверяем, открывается ли адрес без проверки сертификата
            r2 = self.insecure.fetch(url, read_body=read)
            if not r2.error:
                r2.ssl_note = "Сертификат не прошёл проверку, но сайт отвечает"
                r = r2
        if r.status and r.status < 400:
            lim.success(r.ttfb or r.elapsed)
        elif (r.status or 0) >= 500:
            for x in slow_down:
                x.server_error()
        parsed = None
        if kind == "resource" and r.status == 200 and r.body and \
                (r.content_type.startswith("image/") or not r.content_type or r.content_type == "application/octet-stream"):
            r.img = image_info(r.body, r.content_type)
        if read and r.status == 200 and r.is_html and r.body:
            ct = r.headers.get("content-type", "")
            rd = self.renderer.render(url, r.body, ct) if self.renderer and not self.stop_flag else None
            if self.renderer:
                self.js_state_note()
            # страница после скриптов на своём адресе - она и будет страницей (compare_js), исходник нужен только для
            # сравнения: облегчённый разбор (parser.parse_html light). Иначе - полный, как без JavaScript.
            final = U.normalize(rd.final_url) if rd and rd.final_url else ""
            parsed = parse_html(r.body, ct, light=bool(rd and rd.html and not (final and final != url)))
            if rd is not None:
                parsed["js"] = rd
                if rd.html:
                    parsed["rendered"] = parse_html(rd.html.encode("utf-8"), "text/html; charset=utf-8")
            if self.cfg.extract and kind == "page":   # свои правила: в режиме JavaScript - по странице после скриптов
                parsed["extract"] = json.dumps(extract.apply(self.cfg.extract, rd.html) if rd and rd.html else
                                               extract.apply_bytes(self.cfg.extract, r.body, r.headers.get("content-type", "")),
                                               ensure_ascii=False)
        return r, parsed

    def js_state_note(self):
        """Браузер для JavaScript не запустился заново или выключен после 5 неудач (renderer._recycle) - строка в
        журнале один раз на каждое изменение: раньше это было видно только по отчёту."""
        r = self.renderer
        state = ("off", r.start_error) if r.start_error else ("retry", r.launch_error) if r.launch_error else ("ok", "")
        with _JS_NOTE_LOCK:   # зовут сразу несколько потоков: без замка одна строка писалась по нескольку раз
            prev = getattr(self, "_js_state", ("ok", ""))
            if state[0] == prev[0]:
                return
            self._js_state = state
        why = state[1].split(": ", 1)[-1]   # «браузер не запустился заново: <причина>» - только причина
        if state[0] == "off":
            self.log(f"   Браузер для JavaScript не запускается ({why}) - дальше проверяю без JavaScript.")
        elif state[0] == "retry":
            self.log(f"   Браузер для JavaScript не запустился заново ({why}) - попробую снова через минуту, "
                     "пока страницы без JavaScript.")
        else:
            self.log("   Браузер для JavaScript снова работает.")

    START_WAITS = (20, 60)  # сколько ждать перед новыми попытками открыть главную, с

    def _site_answered(self):
        """Сайт уже отвечал (robots.txt открылся): значит, он жив, а сброс - не «сайта нет»."""
        return any((v or {}).get("status") for v in (self.store.get_meta("robots", {}) or {}).values())

    def _start_wait(self, url, read):
        """Главная сбрасывает соединение, хотя robots.txt и зеркала только что открылись: так ведёт себя защита от
        частых запросов (kamen-primer.ru 09.10: сброс за 0,13 с на каждую попытку, через сутки открывается). Ждём и
        пробуем ещё, иначе весь сайт пропускается по одной главной. Возвращает удачный ответ или None."""
        self._start_waited = True
        self.limiter.backoff(5)
        for wait_s in self.START_WAITS:
            self.log(f"   Главная не открылась (соединение сброшено или нет ответа) - жду {wait_s} с и пробую ещё раз: "
                     "похоже на защиту сайта от частых запросов.")
            end = time.time() + wait_s
            while time.time() < end:
                if self.stopped():
                    return None
                time.sleep(0.5)
            r = self.fetcher.fetch(url, read_body=read)
            if not r.retryable:
                # ответ без ошибки соединения - ещё не «открылась»: 403 или 500 тоже приходят без неё
                if not r.error and 200 <= r.status < 400:
                    self.log("   Главная открылась - продолжаю бережнее.")
                elif r.status:
                    self.log(f"   Главная ответила кодом {r.status}.")
                return r
        self.start_blocked = True
        return None

    # ---------- обработка результата (главный поток, пишет в базу)
    def handle(self, url, depth, internal, kind, r, parsed):
        row = {"url": url, "status": r.status, "reason": r.reason, "error": r.error,
               "content_type": r.content_type, "size": r.size, "elapsed": round(r.elapsed, 3),
               "ttfb": round(r.ttfb, 3) if r.ttfb else None,
               "last_modified": r.headers.get("last-modified", ""),
               "content_encoding": r.headers.get("content-encoding", ""),
               "x_robots": r.headers.get("x-robots-tag", ""), "truncated": int(r.truncated),
               "ssl_note": r.ssl_note, "size_measured": int(r.size_measured)}
        if kind == "resource" and r.status == 200:  # картинки, стили, скрипты: велено ли браузеру их запоминать
            cc = r.headers.get("cache-control", "")
            exp = r.headers.get("expires", "")
            row["cache_control"] = cc or (f"Expires: {exp}" if exp else "") or "-"
        img = getattr(r, "img", None)
        if img:
            row["img_format"], row["img_width"], row["img_height"] = img
        links, rel_links = [], []
        from_sitemap = kind == "sitemap"  # страница из sitemap: смотрим её саму, но по ссылкам не идём

        def add_link(raw, kind_, anchor="", nofollow=False, enqueue=True, kind_hint="page", base=url):
            n = U.normalize(raw, base)
            if not n:
                return None
            dst = n
            own_site = U.same_site(n, self.root_host, True)
            if own_site and kind_ == "a" and U.is_relative(raw):
                rel_links.append((raw.strip()[:300], n, (anchor or "")[:200], url))
            if self.cfg.strip_tracking and own_site:
                dst, removed = U.strip_params(n, self.clean_rules(n))
                if removed and not from_sitemap:
                    self.store.add_param_links([(url, n, dst, ",".join(removed))])
            is_int = U.same_site(dst, self.root_host, self.cfg.crawl_subdomains)
            if not from_sitemap or kind_ == "redirect":
                links.append((url, dst, raw[:500], anchor[:300], int(nofollow), kind_, int(is_int)))
            if enqueue:
                self.consider(dst, depth + 1, url, kind_hint, follow=kind_ in ("redirect", "refresh", "canonical"))
            return dst

        # Редирект HTTP
        if 300 <= r.status < 400:
            row["redirect_type"] = f"HTTP {r.status}"
            if r.location:
                # не http(s) (tg://, mailto:) или кривой адрес - add_link его не берёт, но адрес перехода есть: пишем как
                # есть, иначе отчёт назвал бы это «Редирект без адреса» (codes.bucket)
                row["location"] = add_link(r.location, "redirect",
                                           kind_hint=kind if kind in ("resource", "sitemap") else "page") \
                    or r.location.strip()[:500] or None
            row["indexable"], row["indexability"] = 0, "Редирект"

        # Каноникал в заголовке Link
        m = re.search(r'<([^>]+)>\s*;[^,]*rel\s*=\s*"?canonical', r.headers.get("link", ""), re.I)
        if m:
            row["canonical_header"] = U.normalize(m.group(1), url) or m.group(1)

        js_row = {}
        raw_parsed = parsed  # ошибки в <head> смотрим в исходном HTML: браузер после скриптов их уже «починил»
        # часть разбора упала (parser._Both) - страница разобрана не вся: в сбои.txt и в отчёт «Сбои программы»
        perr = ((parsed or {}).get("parse_errors") or []) + (((parsed or {}).get("rendered") or {}).get("parse_errors") or [])
        fail_note = None
        if perr:
            fail_note = "Сбой обработки: разобрана не вся страница (" + perr[0][:80] + ")"
            self.log_failure(url, "\n".join(perr))
        if parsed and parsed.get("extract"):
            row["extract"] = parsed["extract"]
        if parsed and parsed.get("js") is not None:
            parsed, js_row = self.compare_js(url, parsed)

        if parsed:
            p = parsed
            base = U.normalize(p["base"], url) if p["base"] else url
            row.update({
                "title": p["titles"][0] if p["titles"] else None, "title_count": len(p["titles"]),
                "description": p["descriptions"][0] if p["descriptions"] else None,
                "description_count": len(p["descriptions"]),
                "h1": " | ".join(p["h1"]) if p["h1"] else None, "h1_count": len(p["h1"]),
                "h2_count": p["h2_count"], "canonical_count": len(p["canonicals"]),
                "meta_robots": "; ".join(f"{n}: {c}" for n, c in p["robots"]),
                "word_count": p["word_count"], "content_hash": p["content_hash"],
                "text_sample": p["text_sample"], "encoding": p["encoding"],
                "encoding_source": p["encoding_source"], "bad_chars": p["bad_chars"],
                "lang": p["lang"], "hreflang": "; ".join(f"{l} {h}" for l, h in p["hreflang"]),
                "images_no_alt": sum(1 for i in p["images"] if not i["alt"]),
                "minhash": p.get("minhash", ""),
                "viewport": p.get("viewport"), "keywords": p.get("keywords"),
                "og": json.dumps(p.get("og") or {}, ensure_ascii=False),
                "schema_types": ", ".join(p.get("schema_types") or []),
                "schema_errors": p.get("schema_errors", 0),
                "content_words": p.get("content_words"),
                # страница из sitemap без H1 - кандидат в пустую (удалённый товар, checks/content soft404): её текст
                # нужен
                "blocks": p.get("blocks") if internal and (kind == "page" or (kind == "sitemap" and not p.get("h1")))
                else None,
                "contacts": p.get("contacts"),
                "schema_info": p.get("schema_info"),
                "counters": p.get("counters"),
                # без JavaScript подмену не видно - только подсказка, что скрипт сервиса подключён
                "calltrack": CT.compare(None, None, p["calltrack"]) if internal and p.get("calltrack") else None,
                "shop": p.get("shop") if internal and kind == "page" else None,
            })
            if internal and kind == "page":   # ссылки на чужие сайты в спрятанном стилем блоке - так выглядит взлом
                hid, shown = [], set()
                for lk in p["links"]:
                    n = U.normalize(lk["href"], base)
                    if n and n.startswith("http") and not U.same_site(n, self.root_host, True):
                        if lk.get("hidden"):
                            hid.append([n, (lk["anchor"] or "")[:120]])
                        else:
                            shown.add(U.host_of(n))
                # та же ссылка видна на странице (соцсети в мобильном меню, спрятанном на компьютере) - не взлом
                hid = [h for h in hid if U.host_of(h[0]) not in shown]
                row["hidden_links"] = json.dumps(hid[:20], ensure_ascii=False) if hid else None
            rp = raw_parsed or p
            multi = [f"<{t}> ×{n}" for t, n in (rp.get("html_counts") or {}).items() if n > 1]
            row["html_multi"] = ", ".join(multi)
            ids = rp.get("dup_ids") or []
            row["dup_ids"] = (f"{len(ids)}: " + ", ".join(ids[:5])) if ids else ""
            row["head_break"] = rp.get("head_break") or ""
            row["after_break"] = ", ".join(rp.get("after_break") or [])
            bot = "yandex" if self.cfg.robots_for.startswith("yandex") else "googlebot"
            robots_meta = " ".join(c for n, c in p["robots"] if n in ("robots", bot))
            nofollow_page = ("nofollow" in robots_meta or says_none(robots_meta)) and not self.cfg.follow_nofollow
            # JavaScript-редирект: после выполнения скриптов браузер оказался на другом адресе
            if js_row.get("js_redirect"):
                row["redirect_type"] = "JavaScript"
                row["location"] = add_link(js_row["js_redirect"], "redirect", enqueue=not from_sitemap)
            # Meta refresh — редирект, которого не видно по коду ответа
            elif p["refresh_url"]:
                row["redirect_type"] = "meta refresh"
                row["location"] = add_link(p["refresh_url"], "refresh", base=base, enqueue=not from_sitemap)
            if p["canonicals"]:
                row["canonical"] = add_link(p["canonicals"][0], "canonical",
                                            enqueue=self.cfg.crawl_canonicals and not from_sitemap, base=base)
            n_int = n_ext = 0
            for a in p["links"]:
                follow = not nofollow_page and (self.cfg.follow_nofollow or not a["nofollow"]) and not from_sitemap
                dst = add_link(a["href"], "a", a["anchor"], a["nofollow"], enqueue=follow, base=base)
                if dst:
                    if U.same_site(dst, self.root_host, self.cfg.crawl_subdomains):
                        n_int += 1
                    else:
                        n_ext += 1
            row["outlinks_internal"], row["outlinks_external"] = n_int, n_ext
            if not from_sitemap:
                imgs = []
                for im in p["images"]:
                    src = add_link(im["src"], "img", im.get("alt") or "", kind_hint="resource", base=base)
                    if src:
                        imgs.append((url, src, im["alt"], int(im["has_size"]), im["loading"],
                                     int(im["in_picture"]), int(im["srcset"])))
                self.store.add_images(imgs)
                res = []
                for rs in p.get("resources", []):
                    hint = "page" if rs["type"] == "iframe" else "resource"
                    if rs["type"] in ("css", "js", "srcset") and not self.cfg.check_resources:
                        continue
                    src = add_link(rs["src"], rs["type"], kind_hint=hint, base=base)
                    if src:
                        res.append((url, src, rs["type"]))
                self.store.add_resources(res)
                disp = js_row.pop("_img_display", None)
                if disp:
                    rows = []
                    for s_, w, h in disp:
                        n = U.normalize(s_ or "", base)
                        if n and w and h and w > 1 and h > 1:
                            rows.append((url, n, int(w), int(h)))
                    self.store.add_img_display(rows)
                for lang, href in p["hreflang"]:
                    add_link(href, "hreflang", lang, base=base)

        # Индексируемость: что мы «просим» поисковик сделать
        if "indexable" not in row:
            robots_all = (row.get("meta_robots") or "") + " " + row["x_robots"].lower()
            canon = row.get("canonical") or row.get("canonical_header")
            if r.error:
                row["indexable"], row["indexability"] = 0, "Нет ответа"
            elif r.status != 200:
                row["indexable"], row["indexability"] = 0, f"Код {r.status}"
            elif not internal or kind not in ("page", "sitemap"):
                row["indexable"], row["indexability"] = None, ""
            elif not r.is_html:
                row["indexable"], row["indexability"] = 1, "Не HTML"
            elif "noindex" in robots_all or says_none(robots_all) or \
                    "noindex" in (js_row.get("raw_robots") or "").lower():
                # noindex в исходном HTML Google видит до JavaScript и дальше страницу не рендерит
                row["indexable"], row["indexability"] = 0, "noindex"
            elif canon and canon != url:
                row["indexable"], row["indexability"] = 0, "Канонизирована"
            elif row.get("redirect_type") in ("meta refresh", "JavaScript"):
                row["indexable"], row["indexability"] = 0, "Редирект"
            else:
                row["indexable"], row["indexability"] = 1, "Индексируемая"

        js_row.pop("_img_display", None)
        row.update(js_row)
        self.store.save_page(row)
        self.store.add_links(links)
        self.store.add_rel_links(rel_links)
        self.store.mark(url, "done", fail_note)
        if not fail_note:   # со второго раза разобрана целиком (перепроверка, повторно в браузере) - старый сбой
            # снимаем: mark причину не стирает, и страница оставалась «разобрана не целиком» (ревью)
            self.store.db.execute("UPDATE urls SET skip_reason=NULL WHERE url=? AND skip_reason LIKE 'Сбой обработки%'",
                                  (url,))
        if not internal and (kind == "resource" or U.is_file_url(url)):
            self.ext_file_result(url, r.status)

    def compare_js(self, url, raw):
        """Возвращает (что считать страницей, поля сравнения для базы).
        Страницей считаем версию после JavaScript — её видит Google после рендеринга."""
        rd = raw["js"]
        js = raw.get("rendered")
        row = {"js_error": rd.error, "js_time": round(rd.elapsed, 2),
               "js_blocked": "\n".join(rd.blocked_by_robots[:20]), "js_errors": rd.console_errors}
        # исходные значения — для сравнения в отчёте
        row.update({
            "raw_title": raw["titles"][0] if raw["titles"] else "",
            "raw_description": raw["descriptions"][0] if raw["descriptions"] else "",
            "raw_h1": " | ".join(raw["h1"]),
            "raw_canonical": U.normalize(raw["canonicals"][0], url) if raw["canonicals"] else "",
            "raw_robots": "; ".join(f"{n}: {c}" for n, c in raw["robots"]),
            "raw_words": raw["word_count"],
        })
        if not js:
            return raw, row
        row["_img_display"] = rd.img_display
        final = U.normalize(rd.final_url) if rd.final_url else ""
        if final and final != url:
            # Браузер ушёл на другой адрес: после скриптов это уже другая страница, сравнивать нечего.
            # Meta refresh браузер тоже выполняет — его учитываем как meta refresh, а не как JS-редирект.
            if not raw["refresh_url"]:
                row["js_redirect"] = final
            return raw, row
        base_raw = U.normalize(raw["base"], url) if raw["base"] else url
        base_js = U.normalize(js["base"], url) if js["base"] else url

        def targets(p, base):
            out = set()
            for a in p["links"]:
                n = U.normalize(a["href"], base)
                if n and U.same_site(n, self.root_host, self.cfg.crawl_subdomains):
                    out.add(n)
            return out
        t_raw, t_js = targets(raw, base_raw), targets(js, base_js)
        only_js = sorted(t_js - t_raw - {url})  # ссылку страницы на саму себя не считаем
        # пример текста, которого нет в исходном HTML: чтобы можно было проверить глазами
        raw_text = " ".join(raw.get("text", "").split()).lower()
        extra = []
        for frag in re.split(r"(?<=[.!?])\s+|\s{2,}", js.get("text", "")):
            f = " ".join(frag.split())
            if len(f) >= 25 and f.lower() not in raw_text and f not in extra:
                extra.append(f)
            if sum(len(x) for x in extra) > 400:
                break
        row["js_text_sample"] = " … ".join(extra)[:500]
        row.update({"raw_links": len(t_raw), "js_links": len(t_js), "js_only_links_count": len(only_js),
                    "js_only_links": "\n".join(only_js[:30])})
        # коллтрекинг: скрипт подменяет телефон из HTML на свой (сервис - по скриптам до и после JavaScript)
        found = set(raw.get("calltrack") or []) | set(js.get("calltrack") or [])
        svc = [n for n, _ in CT.SERVICES if n in found]
        row["calltrack"] = CT.compare(raw.get("contacts"), js.get("contacts"), svc)
        # кодировку берём из исходного ответа: браузер её уже перевёл в UTF-8
        js["encoding"], js["encoding_source"], js["bad_chars"] = raw["encoding"], raw["encoding_source"], raw["bad_chars"]
        return js, row
