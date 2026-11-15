"""Сайт отвечает через раз: пауза, меньше потоков, повтор адресов без ответа.

Было (dog-comfort.kz): после ~150 страниц сайт начал сбрасывать соединения через раз. Обход шёл
дальше в полную силу, 0,8 адреса в секунду, и из 190 страниц 70 попали в отчёт как «Соединение сброшено» -
будто сайт сломан. Защита от частых запросов только сильнее сердилась. Прежнее правило «сайт упал»
(main_loop.note_health) срабатывает лишь на 40 ошибок подряд за 10 минут, а «через раз» его не трогает.

Стало (общее правило, без привязки к сайту): если из последних 30 адресов сайта (страницы и свои файлы) не
ответили 40 % и больше - обрыв, таймаут, 429 или 503, - программа ставит паузу (1 мин, потом 2, потом 5),
дальше идёт по одному адресу с паузой между запросами втрое больше и прибавляет по потоку после каждых
30 нормальных ответов подряд. Адрес, который не ответил, пока сайт неустойчив, ставится в очередь ещё раз
(до двух раз), а не записывается в отчёт ошибкой. Если и после пяти пауз главная не открывается - обход
прекращается как «сайт перестал отвечать», отчёт собирается по тому, что успели.
Окно показывает плашку и уведомление по строке журнала «Сайт отвечает через раз» (window/job.py)."""
import os
import time
from collections import Counter, deque

from .common import _ago as _ago_s, _n


def _ago(sec):
    """«1 мин», «2 мин 30 с», «40 с»."""
    sec = int(round(sec))
    return f"{sec // 60} мин" if sec >= 60 and sec % 60 == 0 else _ago_s(sec)


def _env_pauses():
    raw = os.environ.get("CLAYLER_SHAKY_PAUSES") or ""
    try:
        v = tuple(float(x) for x in raw.split(",") if x.strip())
    except ValueError:
        v = ()
    return v or (60, 120, 300, 300, 300)


class ShakyMixin:
    SHAKY_WINDOW = 30                                                  # сколько последних адресов смотреть
    SHAKY_MIN = int(os.environ.get("CLAYLER_SHAKY_MIN") or 20)         # раньше стольких ответов не судим
    SHAKY_SHARE = 0.4                                                  # столько без ответа - пауза
    SHAKY_UNSTEADY = 0.25                                              # столько - адрес без ответа повторить
    SHAKY_PAUSES = _env_pauses()                                       # длина пауз по очереди, с
    SHAKY_OK = int(os.environ.get("CLAYLER_SHAKY_OK") or 30)           # нормальных ответов подряд - +1 поток
    SHAKY_REPEAT = 2                                                   # сколько раз адрес ставится в очередь снова

    @staticmethod
    def shaky_fail(r):
        """Нет ответа или «слишком часто»: обрыв, таймаут, ошибка соединения, 429, 503."""
        return bool(r.retryable or r.status in (429, 503))

    def _shaky(self):
        sh = getattr(self, "_sh", None)
        if sh is None:
            sh = self._sh = {"recent": deque(maxlen=self.SHAKY_WINDOW), "level": 0, "until": 0.0, "cap": None,
                             "ok": 0, "pauses": 0, "seconds": 0.0, "again": Counter(), "repeated": 0}
        return sh

    def shaky_cap(self, default):
        """Сколько адресов загружать одновременно: как обычно или меньше, пока сайт неустойчив."""
        cap = self._shaky()["cap"]
        return default if cap is None else cap

    def shaky_left(self):
        """Сколько секунд ещё длится пауза (0 - пауза кончилась или её нет). По концу паузы - проверка главной."""
        sh = self._shaky()
        if not sh["until"]:
            return 0
        left = sh["until"] - time.time()
        if left > 0:
            return left
        sh["until"] = 0.0
        if self.stop_flag:
            return 0
        r = self.fetcher.fetch(self.start, read_body=False)
        if r.status and r.status < 500 and not self.shaky_fail(r):
            self.log("   Пауза закончилась, главная открывается - продолжаю по одному адресу, медленнее.")
            self._shaky_status()
            return 0
        if sh["level"] >= len(self.SHAKY_PAUSES):
            mins = max(1, round(sh["seconds"] / 60))
            self.site_down = f"сайт отвечал через раз, паузы не помогли ({sh['pauses']}, всего {mins} мин)"
            why = self.access_reason(r)
            if why:
                self.site_down += "; " + why
            self.store.set_meta("site_down", self.site_down)
            self.log(f"\nСайт перестал отвечать: {self.site_down}, главная тоже не открывается "
                     f"({r.status or r.error or 'нет ответа'}). Обход прекращаю, отчёт соберу по тому, что успели проверить.")
            self.stop_flag = True
            return 0
        why = self.access_reason(r)   # причина один раз за обход: режут по дороге, не пускает программы (access.py)
        self._shaky_pause(f"главная после паузы не открылась ({r.status or r.error or 'нет ответа'}"
                          + (f"; {why}" if why else "") + ")")
        return sh["until"] - time.time()

    def shaky_note(self, url, internal, r):
        """Учесть ответ адреса сайта. True - адрес не ответил, пока сайт неустойчив: поставить в очередь
        ещё раз, в отчёт пока не записывать."""
        if not internal:
            return False
        sh = self._shaky()
        fail = self.shaky_fail(r)
        sh["recent"].append(fail)
        if not fail:
            if sh["cap"] is not None and not sh["until"]:
                sh["ok"] += 1
                if sh["ok"] >= self.SHAKY_OK:
                    sh["ok"] = 0
                    self._shaky_faster()
            return False
        sh["ok"] = 0
        bad, n = sum(sh["recent"]), len(sh["recent"])
        unsteady = sh["cap"] is not None or (n >= 10 and bad / n >= self.SHAKY_UNSTEADY)
        again = unsteady and sh["again"][url] < self.SHAKY_REPEAT and not self.stop_flag
        if again:
            sh["again"][url] += 1
            sh["repeated"] += 1
        if not sh["until"] and n >= self.SHAKY_MIN and bad / n >= self.SHAKY_SHARE:
            self._shaky_pause(f"из последних {_n(n)} адресов не ответили {_n(bad)} (обрыв соединения, таймаут "
                              f"или «слишком много запросов»)")
        return again

    def _shaky_pause(self, why):
        sh = self._shaky()
        first = sh["cap"] is None
        sec = self.SHAKY_PAUSES[min(sh["level"], len(self.SHAKY_PAUSES) - 1)]
        sh["level"] += 1
        sh["pauses"] += 1
        sh["seconds"] += sec
        sh["until"] = time.time() + sec
        sh["cap"], sh["ok"] = 1, 0
        sh["recent"].clear()  # после паузы судим заново: ответы, начатые до неё, не в счёт
        for lim in (self.limiter, self.res_limiter):
            lim.calm(sec, max(self.cfg.delay * 3, 1.0))
        self.log(f"\n   Сайт отвечает через раз: {why}. Ставлю паузу на {_ago(sec)}"
                 + (", потом проверяю по одному адресу, медленнее. Адреса без ответа проверю ещё раз: в отчёт они "
                    "попадут, только если не ответят и потом." if first else ", потом снова по одному адресу."))
        self._shaky_status()

    def _shaky_faster(self):
        sh = self._shaky()
        full = self.cfg.threads
        if sh["cap"] + 1 >= full:
            sh["cap"], sh["level"] = None, 0
            for lim in (self.limiter, self.res_limiter):
                lim.uncalm()
            self.log("   Сайт снова отвечает стабильно - скорость как в настройках.")
        else:
            sh["cap"] += 1
            self.log(f"   Сайт отвечает стабильно - прибавляю скорость: адресов одновременно {sh['cap']} из {full}.")
        self._shaky_status()

    def _shaky_status(self):
        """Строка для окна: что сейчас с сайтом (пусто - всё как обычно)."""
        sh = self._shaky()
        left = sh["until"] - time.time() if sh["until"] else 0
        if left > 0:
            note = f"сайт отвечает через раз, пауза ещё {_ago(left)}, потом продолжу медленнее"
        elif sh["cap"] is not None:
            note = (f"сайт отвечал через раз, проверяю бережно: адресов одновременно {sh['cap']} из {self.cfg.threads}, "
                    f"скорость прибавлю сама, когда сайт начнёт отвечать стабильно")
        else:
            note = ""
        self.st(shaky_note=note)
        return note

    def shaky_meta(self):
        """Для отчёта: сколько было пауз и повторов (пусто - сайт отвечал ровно)."""
        sh = self._shaky()
        if sh["pauses"]:
            self.store.set_meta("shaky", {"pauses": sh["pauses"], "seconds": round(sh["seconds"]),
                                          "repeated": sh["repeated"]})
