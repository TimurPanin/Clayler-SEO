"""Рендеринг JavaScript: открываем страницу во встроенном Chromium (без окна),
ждём, пока скрипты отработают, и забираем итоговый HTML.

Playwright работает в своём отдельном потоке с собственным циклом asyncio.
Потоки-загрузчики краулера отдают ему адрес и ждут результат. Одновременно
открыто несколько вкладок (render_tabs), поэтому страницы рендерятся параллельно.
"""
import asyncio
import os
import re
import threading
import time
from dataclasses import dataclass, field

# Что не нужно для рендеринга: картинки, шрифты, видео. Их блокируем ради скорости —
# на текст, ссылки и мета-теги они не влияют.
BLOCK_TYPES = {"media", "font"}
# Картинки не скачиваем, а подменяем прозрачной точкой 1×1. Так страница грузится быстро, а размеры
# на экране остаются честными: картинка с заданными в HTML или CSS размерами занимает своё место,
# а картинка без размеров сжимается в точку — её размер на экране мы тогда просто не учитываем.
PIXEL = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                      "1f15c4890000000d49444154789c6360000002000100e5270de40000000049454e44ae426082")


# Браузер или его вкладки закрылись не по нашей воле: Playwright так отвечает на любой вызов после смерти браузера
DEAD = re.compile(r"Target page, context or browser has been closed|Browser has been closed|"
                  r"browser has disconnected|Connection closed|Target closed", re.I)


@dataclass
class Rendered:
    html: str = ""
    final_url: str = ""       # адрес после JS-редиректа (если был)
    error: str = ""
    elapsed: float = 0.0
    blocked_by_robots: list = field(default_factory=list)  # JS/CSS, закрытые в robots.txt
    console_errors: int = 0
    img_display: list = field(default_factory=list)  # [адрес картинки, ширина и высота на экране]


def available():
    """Можно ли рендерить: установлен ли playwright. Возвращает (bool, пояснение)."""
    try:
        import playwright  # noqa: F401
    except Exception:
        return False, "не установлен модуль playwright"
    return True, ""


class Renderer:
    # Через столько страниц браузер и Playwright запускаются заново. Playwright (1.56-1.63) на каждую открытую
    # страницу оставляет в памяти 3 служебных вызова без ответа (__waitInfo__ из goto и wait_for_load_state) со
    # стеком вызовов и никогда их не удаляет: на thehome.ru память программы росла на 80 МБ в минуту,
    # через 17 часов проверка упала с MemoryError. Перезапуск выбрасывает накопленное; он занимает пару секунд.
    RECYCLE_EVERY = int(os.environ.get("CLAYLER_RENDER_RECYCLE") or 200)

    def __init__(self, user_agent, tabs=2, wait_seconds=5.0, timeout=30.0, mobile=True,
                 robots_check=None):
        self.user_agent = user_agent
        self.tabs = max(1, tabs)
        self.wait_seconds = wait_seconds
        self.timeout = timeout
        self.mobile = mobile
        self.robots_check = robots_check  # функция url -> (разрешено, правило)
        self.loop = None
        self.thread = None
        self.ready = threading.Event()
        self.start_error = ""
        self.rendered = 0    # страниц с прошлого запуска браузера
        self.restarts = 0    # сколько раз браузер запускался заново
        self.revived = 0     # из них потому, что браузер умер посреди проверки
        self.launch_fails, self.launch_error, self.retry_at = 0, "", 0.0   # браузер не запустился заново

    # ---------- запуск и остановка
    def start(self):
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="renderer")
        self.thread.start()
        self.ready.wait(120)
        if not self.ready.is_set():
            self.start_error = "браузер не запустился за 2 минуты"
        return not self.start_error

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._startup())
        except Exception as e:
            self.start_error = _short(e)
            self.ready.set()
            return
        self.ready.set()
        self.loop.run_forever()

    async def _startup(self):
        self.sem = asyncio.Semaphore(self.tabs)
        self.recycle_lock = asyncio.Lock()
        await self._launch()

    async def _launch(self):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        try:
            self.browser = await self.pw.chromium.launch(headless=True)
        except Exception as e:
            msg = _short(e)
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                msg = "не скачан браузер Chromium (нужно: python -m playwright install chromium)"
            await self.pw.stop()
            raise RuntimeError(msg)
        vp = {"width": 412, "height": 915} if self.mobile else {"width": 1366, "height": 900}
        try:
            self.context = await self.browser.new_context(
                user_agent=self.user_agent, viewport=vp, is_mobile=self.mobile, has_touch=self.mobile,
                java_script_enabled=True, ignore_https_errors=True, service_workers="block")
        except Exception:
            # браузер запустился, а вкладки нет - закрываем его сразу, а не ждём следующей попытки или конца
            # проверки: иначе процессы Chromium висели бы зря
            for close in (self.browser.close, self.pw.stop):
                try:
                    await asyncio.wait_for(close(), 15)
                except Exception:
                    pass
            raise

    async def _recycle(self):
        """Запустить браузер и Playwright заново, когда открыто RECYCLE_EVERY страниц. Ждёт, пока закроются все
        вкладки (забирает все места семафора), новые страницы в это время ждут."""
        if self.rendered < self.RECYCLE_EVERY or time.time() < self.retry_at:
            return
        async with self.recycle_lock:
            if self.rendered < self.RECYCLE_EVERY or time.time() < self.retry_at:
                return   # пока ждали, браузер уже перезапустил другой поток (или ждём новой попытки)
            got = 0   # сколько мест взяли: отдаём ровно столько, даже если перезапуск прервали посередине
            try:
                for _ in range(self.tabs):
                    await self.sem.acquire()
                    got += 1
                await self._shutdown()
                try:
                    await self._launch()
                except Exception as e:
                    # не запустился (например, на минуту кончилась память) - пробуем снова через минуту, страницы
                    # пока без JavaScript; после 5 неудач подряд - как незапустившийся браузер
                    self.launch_fails += 1
                    self.launch_error = "браузер не запустился заново: " + _short(e)
                    self.retry_at = time.time() + 60
                    if self.launch_fails >= 5:
                        self.start_error = self.launch_error
                    return
                self.launch_fails, self.launch_error, self.retry_at = 0, "", 0.0
                self.restarts += 1
                self.rendered = 0
            finally:
                for _ in range(got):
                    self.sem.release()

    def stop(self):
        if not self.loop:
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
            fut.result(50)   # _shutdown закрывает три части по 15 с: ждём все, иначе Chromium мог остаться
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop = None  # render() после остановки сразу отвечает «браузер не запущен», а не ждёт минуту
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(5)

    async def _shutdown(self):
        # по отдельности: не закрылась вкладка - браузер и Playwright всё равно закрываем, иначе при перезапуске
        # оставались бы лишние процессы
        for close in (self.context.close, self.browser.close, self.pw.stop):
            try:
                await asyncio.wait_for(close(), 15)   # умерший браузер не должен держать перезапуск
            except Exception:
                pass

    # ---------- рендеринг одной страницы (вызывается из потоков краулера)
    def render(self, url, html: bytes = None, content_type: str = "text/html; charset=utf-8") -> Rendered:
        """html — уже скачанный ответ сервера. Браузер получит именно его, а не скачает страницу заново:
        иначе сравнение «до и после JavaScript» ловило бы случайные отличия между двумя ответами сервера
        (случайные блоки, баннеры, ротацию меню)."""
        if self.start_error or not self.loop:
            return Rendered(error=self.start_error or "браузер не запущен")
        fut = asyncio.run_coroutine_threadsafe(self._render(url, html, content_type), self.loop)
        try:
            return fut.result(self.timeout + self.wait_seconds + 30)
        except Exception as e:
            fut.cancel()
            return Rendered(error="Рендеринг не закончился: " + _short(e))

    async def _render(self, url, html=None, content_type="") -> Rendered:
        """Страница в браузере. Браузер умер (кончилась память компьютера, его закрыли) - запускаем заново и
        повторяем страницу один раз: 31.10.2026 на thehome.ru после смерти браузера 3 418 страниц подряд записались
        как «не удалось отрендерить»."""
        try:
            res = await self._render_once(url, html, content_type)
            if not (res.error and DEAD.search(res.error)):
                return res
        except Exception as e:
            if not DEAD.search(str(e)):
                raise
        if self.start_error:
            return Rendered(error=self.start_error)
        self.revived += 1
        self.rendered = max(self.rendered, self.RECYCLE_EVERY)   # _recycle перезапустит браузер
        return await self._render_once(url, html, content_type)

    async def _render_once(self, url, html=None, content_type="") -> Rendered:
        res = Rendered()
        served = {"done": html is None}
        t0 = time.perf_counter()
        await self._recycle()
        if self.start_error or self.launch_error:   # браузера сейчас нет: не ждём закрытую вкладку
            return Rendered(error=self.start_error or self.launch_error)
        async with self.sem:
            self.rendered += 1
            page = await self.context.new_page()
            blocked = []

            async def route(r):
                req = r.request
                if not served["done"] and req.resource_type == "document" and req.url.split("#")[0] == url:
                    served["done"] = True
                    return await r.fulfill(status=200, body=html, content_type=content_type or "text/html")
                if req.resource_type in BLOCK_TYPES:
                    return await r.abort()
                if req.resource_type == "image":
                    return await r.fulfill(status=200, content_type="image/png", body=PIXEL)
                if self.robots_check and req.resource_type in ("script", "stylesheet", "xhr", "fetch"):
                    ok, rule = self.robots_check(req.url)
                    if not ok:
                        blocked.append(req.url)
                        return await r.abort()  # как поисковик: закрытое в robots.txt он не загрузит
                await r.continue_()

            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            try:
                await page.route("**/*", route)
                await page.goto(url, wait_until="load", timeout=self.timeout * 1000)
                # Ждём, пока страница перестанет загружать данные, но не дольше wait_seconds —
                # так же поступает Screaming Frog (5 секунд по умолчанию).
                try:
                    await page.wait_for_load_state("networkidle", timeout=self.wait_seconds * 1000)
                except Exception:
                    pass
                res.html = await page.content()
                res.final_url = page.url
                try:  # какого размера картинки на экране (в CSS-пикселях)
                    res.img_display = await page.evaluate(
                        "() => Array.from(document.images).map(i => [i.currentSrc || i.src, i.clientWidth, i.clientHeight])")
                except Exception:
                    pass
            except Exception as e:
                res.error = _short(e)
            finally:
                res.blocked_by_robots = blocked
                res.console_errors = len(errors)
                try:
                    await page.close()
                except Exception:
                    pass
        res.elapsed = time.perf_counter() - t0
        return res


def _short(e):
    s = str(e).strip().splitlines()
    s = s[0] if s else type(e).__name__
    return s[:160]
