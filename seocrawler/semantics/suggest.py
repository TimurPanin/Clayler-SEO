"""Поисковые подсказки Яндекса и Google: то, что люди на самом деле набирают в поиске.
Ключи и аккаунты не нужны. Ответы запоминаются в папке проверки, повторная сборка не ходит в сеть."""
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .. import jsonfile
from ..sysproxy import urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
YANDEX = "https://suggest.yandex.ru/suggest-ya.cgi?v=4&uil=ru&lr={lr}&part={q}"
GOOGLE = "https://suggestqueries.google.com/complete/search?client=firefox&hl=ru&gl=ru&q={q}"
CACHE_NAME = ".семантика_подсказки.json"
CACHE_DAYS = 30


class Suggest:
    def __init__(self, folder, lr=225, log=print, threads=3, pause=0.25, offline=False):
        self.path = os.path.join(folder, CACHE_NAME)
        self.lr, self.log, self.threads, self.pause, self.offline = lr, log, threads, pause, offline
        self.lock = threading.Lock()
        self.failed = {"yandex": 0, "google": 0}
        self.cache = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self.cache = json.load(f)
        except Exception:
            pass
        old = time.time() - CACHE_DAYS * 86400
        self.cache = {k: v for k, v in self.cache.items() if v.get("t", 0) > old}
        self.fetched = 0

    def save(self):
        jsonfile.save(self.path, self.cache)

    def _get(self, engine, q):
        url = (YANDEX.format(lr=self.lr, q=urllib.parse.quote(q)) if engine == "yandex"
               else GOOGLE.format(q=urllib.parse.quote(q)))
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"})
        for attempt in range(3):
            try:
                with urlopen(req, 15) as r:   # прокси выключенного VPN - напрямую
                    raw = r.read()
                    enc = "utf-8"
                    ct = r.headers.get("content-type") or ""
                    if "charset=" in ct:
                        enc = ct.split("charset=")[-1].split(";")[0].strip() or "utf-8"
                data = json.loads(raw.decode(enc, "replace"))
                items = data[1] if isinstance(data, list) and len(data) > 1 else []
                out = []
                for it in items:
                    s = it if isinstance(it, str) else (it[1] if isinstance(it, list) and len(it) > 1 else "")
                    if isinstance(s, str) and s.strip():
                        out.append(s.strip())
                return out
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        return None

    def get(self, engine, q):
        """Подсказки по фразе (список, первые — самые частые) или None, если сервис не ответил."""
        key = f"{engine}|{self.lr if engine == 'yandex' else 'ru'}|{q}"
        with self.lock:
            hit = self.cache.get(key)
        if hit is not None:
            return hit["s"]
        if self.offline or self.failed[engine] >= 15:  # сервис не отвечает — не мучаем его и себя
            return None
        res = self._get(engine, q)
        time.sleep(self.pause)
        with self.lock:
            if res is None:
                self.failed[engine] += 1
                return None
            self.failed[engine] = 0
            self.cache[key] = {"s": res, "t": time.time()}
            self.fetched += 1
            if self.fetched % 100 == 0:
                self.save()
        return res

    def many(self, tasks, progress=None, stop=None):
        """tasks: [(engine, phrase)] → {(engine, phrase): [подсказки] | None}. stop() - True, если сбор остановили:
        оставшиеся фразы не спрашиваются, уже полученное сохраняется."""
        out, done = {}, [0]

        def one(t):
            if stop and stop():
                return
            r = self.get(*t)
            with self.lock:
                out[t] = r
                done[0] += 1
                if progress and done[0] % 50 == 0:
                    progress(done[0], len(tasks))
        with ThreadPoolExecutor(self.threads) as ex:
            list(ex.map(one, tasks))
        self.save()
        # в порядке заданий, а не ответов: потоки отвечают вразнобой, а от порядка зависят равные места (16.10.2026)
        return {t: out[t] for t in tasks if t in out}
