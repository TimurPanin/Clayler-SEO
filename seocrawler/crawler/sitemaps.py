"""Sitemap: чтение карт сайта и проверка адресов из них."""
import gzip
import xml.etree.ElementTree as ET
from .. import urls as U
from ..robots import sitemap_gone
from .common import _n


class SitemapsMixin:
    # ---------- sitemap
    def load_sitemaps(self, start=None):
        """start — адрес другой части сайта (городской поддомен); по умолчанию — адрес проверки."""
        start = start or self.start
        robots = self.robots_for(start)
        origin = "/".join(start.split("/", 3)[:3])
        todo = list(robots.sitemaps) or [origin + "/sitemap.xml"]
        # в robots.txt не указан - пробуем обычные адреса по очереди, до первого найденного: у WordPress и Yoast
        # карта бывает только по /wp-sitemap.xml или /sitemap_index.xml, и одного 404 на /sitemap.xml мало, чтобы
        # написать клиенту «sitemap на сайте нет»
        spare = [] if robots.sitemaps else [origin + "/sitemap_index.xml", origin + "/wp-sitemap.xml"]
        if not robots.sitemaps:
            self.log("   В robots.txt sitemap не указан, пробую " + todo[0])
        seen, found, gone = set(), [], 0   # gone - файлов, которых нет (404, 410)
        while (todo or (spare and not found)) and len(found) < 200000 and len(seen) < 500:
            if not todo:
                todo.append(spare.pop(0))
                self.log("   Пробую " + todo[0])
            sm = todo.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            self.limiter.wait()
            r = self.fetcher.fetch(sm, any_type=True)
            if r.error.startswith("SSL: ошибка сертификата"):
                r = self.insecure.fetch(sm, any_type=True)
            body = r.body
            if r.status != 200 or not body:
                self.log(f"   {sm}: не открылся ({r.status or r.error})")
                gone += sitemap_gone(r.status, b"")
                continue
            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except Exception:
                    continue
            try:
                root = ET.fromstring(body)
            except ET.ParseError:
                self.log(f"   {sm}: это не XML-файл, пропускаю")
                gone += sitemap_gone(200, body)   # вместо файла обычная страница: файла нет
                continue
            tag = root.tag.split("}")[-1]
            locs = [e.text.strip() for e in root.iter() if e.tag.split("}")[-1] == "loc" and e.text]
            if tag == "sitemapindex":
                todo += locs
            else:
                found += locs
        rows = []
        for raw in found:
            n = U.normalize(raw)
            if n:
                rows.append((n,))
        total = len(rows)
        if self.partial:  # проверяем часть сайта: из sitemap берём только её адреса
            rows = [r for r in rows if self.in_scope(r[0])]
        self.store.db.executemany("INSERT OR IGNORE INTO sitemap VALUES (?)", rows)
        self.store.set_meta("sitemaps", sorted(seen | set(self.store.get_meta("sitemaps", []) or [])))
        # sitemap точно нет (все файлы - 404/410), а не «не прочитался» (5xx, обрыв): так и пишем клиенту
        self.store.set_meta("sitemap_absent", bool(seen) and not found and gone == len(seen))
        self.store.commit()
        if self.partial and total:
            self.log(f"   Файлов sitemap: {len(seen)}, адресов в них: {_n(total)}, из них в проверке: {_n(len(rows))}.")
        elif rows:
            self.log(f"   Файлов sitemap: {len(seen)}, адресов в них: {_n(len(rows))}.")
        else:
            self.log("   Sitemap не найден или пустой. Сравнение с sitemap в отчёте будет пропущено.")
        if self.cfg.crawl_sitemap:
            for (u,) in rows:
                self.consider(u, 1, "sitemap.xml")

    def queue_sitemap_check(self):
        """Адреса из sitemap, на которые не нашлось ни одной ссылки на сайте:
        загружаем их отдельно, чтобы понять — это сирота (200) или мусор (редирект, 404)."""
        rows = self.store.db.execute(
            "SELECT s.url FROM sitemap s LEFT JOIN urls u ON u.url=s.url WHERE u.url IS NULL LIMIT ?",
            (self.cfg.max_pages,)).fetchall()
        for (u,) in rows:
            self.consider(u, 1, "sitemap.xml", "sitemap")
        self.store.commit()
        return len(rows)

    # ---------- адреса, которые знает поиск (Яндекс Вебмастер, Google Search Console)
    def check_search_urls(self, pages_done, left):
        """Страницы, которые Яндекс и Google показывают в поиске, а при обходе по ссылкам их не нашли:
        проверяем их так же, как сирот из sitemap (сама страница, без перехода по её ссылкам).
        Нужен вход через Яндекс/Google в окне программы и доступ к сайту в Вебмастере/Search Console;
        если доступа нет — шаг пропускается, в отчёте («Что не проверено и почему») — понятная пометка.
        meta «search_urls»: {sources: {yandex|google: {state, n}}, urls: {адрес: [yandex, google]}, new, complete}."""
        import os
        from .. import search_console, webmaster
        if os.environ.get("CLAYLER_NO_USER_SETTINGS") == "1" and not os.environ.get("CLAYLER_ACCOUNTS_FILE"):
            return  # автотесты без своего файла доступов: личные входы не трогаем
        if left:
            self.store.set_meta("search_urls", {"sources": {}, "urls": {}, "new": 0, "complete": False})
            self.log("\nАдреса из Яндекс Вебмастера и Search Console не проверяю: сайт обойдён не полностью.")
            return
        self.log("\nБеру адреса страниц, которые знают Яндекс Вебмастер и Google Search Console...")
        sources, found = {}, {}
        for key, mod in (("yandex", webmaster), ("google", search_console)):
            try:
                state, raw = mod.known_urls(self.start, log=self.log)
            except Exception as e:
                self.log(f"   {key}: не получилось - {str(e)[:120]}")
                state, raw = "error", []
            n = 0
            for r in raw:
                u = U.normalize(r)
                if not u or not U.same_site(u, self.root_host, self.cfg.crawl_subdomains) or not self.in_scope(u):
                    continue
                if key not in found.setdefault(u, []):
                    found[u].append(key)
                    n += 1
            sources[key] = {"state": state, "n": n}
            name = "Яндекс Вебмастер" if key == "yandex" else "Google Search Console"
            self.log(f"   {name}: " + {
                "ok": f"адресов сайта - {_n(n)}",
                "not_connected": "вход не подключён в окне программы (пропускаю)",
                "no_access": "у подключённого аккаунта нет доступа к этому сайту (пропускаю)",
                "no_data": "данных по сайту пока нет",
            }.get(state, "не загрузилось (пропускаю)"))
        new = [u for u in found if not self.store.seen(u)]
        base = self.store.progress().get("sitemap", {})
        self._search_base = (base.get("done", 0), sum(base.values()))
        for u in new:
            self.consider(u, 1, "Яндекс Вебмастер" if found[u][0] == "yandex" else "Google Search Console", "sitemap")
        self.store.set_meta("search_urls", {"sources": sources, "urls": found, "new": len(new), "complete": True})
        self.store.commit()
        if new:
            self.log(f"   Из них при обходе не встретились: {_n(len(new))}. Проверяю их отдельно: "
                     f"это страницы, на которые на сайте нет ссылок, или устаревшие адреса.")
            self._drain(pages_done, "search")
        elif found:
            self.log("   Все эти адреса уже встретились при обходе - проверять нечего.")
