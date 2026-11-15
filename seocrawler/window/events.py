"""Уведомления окна: «Отчёт готов», «Семантика собрана», ошибки. Плашки показывает page/notify.js на любой
странице окна (главная, «Семантика», «Словарь»), колокольчик в меню хранит историю.

push() кладёт уведомление в список (последние 100, файл «уведомления.json» - история переживает перезапуск),
пишет его в «Журнал» и играет звук: на «готово» и «ошибку», если звук не выключен в колокольчике.
Звук играет сама программа (winsound), а не страница: так он слышен, даже когда окно свёрнуто."""
import io
import json
import math
import os
import struct
import threading
import time
import wave

from .. import applog

KEEP = 100
_lock = threading.Lock()
_state = None   # {"items": [...], "seen": id, "sound": bool}
_last = {}      # одинаковая ошибка не чаще раза в минуту


def _file():
    return os.path.join(applog.folder(), "уведомления.json")


def _load():
    global _state
    if _state is None:
        try:
            with open(_file(), encoding="utf-8") as f:
                _state = json.load(f)
        except (OSError, ValueError):
            _state = {}
        _state.setdefault("items", [])
        _state.setdefault("seen", 0)
        _state.setdefault("sound", True)
    return _state


def _save():
    try:
        tmp = _file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False)
        os.replace(tmp, _file())
    except OSError:
        pass


def push(kind, title, text="", link="", site="", detail="", todo=""):
    """kind: ok (готово), err (ошибка), warn (нужно ваше действие), info. Возвращает уведомление или None
    (одинаковая ошибка чаще раза в минуту не повторяется)."""
    key = (kind, title, text)
    if kind == "err" and time.time() - _last.get(key, 0) < 60:
        return None
    _last[key] = time.time()
    with _lock:
        st = _load()
        prev = st["items"][-1]["id"] if st["items"] else 0
        ev = {"id": max(prev + 1, int(time.time() * 1000)), "t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind,
              "title": applog.scrub(title)[:200], "text": applog.scrub(text)[:600], "todo": todo[:400],
              "link": link, "site": site, "detail": applog.scrub(detail)[:2000]}
        st["items"] = (st["items"] + [ev])[-KEEP:]
        _save()
        sound = st["sound"]
    applog.write("error" if kind == "err" else "event", title + (". " + text if text else ""), site,
                 detail if kind == "err" else "")
    if sound and kind in ("ok", "err"):
        play(kind)
    return ev


def error(text, site="", where="", link=""):
    """Ошибка простыми словами: заголовок и «что сделать» из plain_errors, исходный текст - «Подробнее»."""
    from ..plain_errors import explain
    e = explain(text)
    return push("err", (where + ": " if where else "") + e["title"], "", link, site, e["detail"], e["todo"])


def since(after=0):
    with _lock:
        st = _load()
        return {"items": [e for e in st["items"] if e["id"] > after], "seen": st["seen"], "sound": st["sound"],
                "last": st["items"][-1]["id"] if st["items"] else 0}


def update(seen=None, sound=None, clear=False):
    with _lock:
        st = _load()
        if seen is not None:
            st["seen"] = max(st["seen"], int(seen))
        if sound is not None:
            st["sound"] = bool(sound)
        if clear:
            st["seen"] = st["items"][-1]["id"] if st["items"] else st["seen"]
            st["items"] = []
        _save()
    return since(0)


# ---------- звук: короткий перезвон, без файлов ----------

def _chime(notes):
    """WAV в памяти: ноты (частота, длительность) с мягким затуханием."""
    rate, frames = 22050, bytearray()
    for freq, dur in notes:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = min(1.0, i / (rate * 0.01)) * math.exp(-4.5 * t / dur)
            v = 0.32 * env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t))
            frames += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


_SOUNDS = {}
NOTES = {"ok": [(784, 0.14), (1046.5, 0.32)],                    # вверх: готово
         "err": [(440, 0.16), (349.2, 0.16), (293.7, 0.34)]}     # вниз: ошибка


def play(kind):
    """Сыграть звук в отдельном потоке. Автотесты (CLAYLER_REPORTS) и не-Windows - без звука."""
    if os.name != "nt" or os.environ.get("CLAYLER_REPORTS") or os.environ.get("CLAYLER_NO_SOUND"):
        return

    def run():
        try:
            import winsound
            if kind not in _SOUNDS:
                _SOUNDS[kind] = _chime(NOTES[kind])
            winsound.PlaySound(_SOUNDS[kind], winsound.SND_MEMORY)
        except Exception:   # noqa: BLE001 - нет звука, не беда
            pass
    threading.Thread(target=run, daemon=True).start()


# ---------- откуда берутся уведомления ----------

def from_telegram(text, link=""):
    """То же сообщение, что уходит в Telegram (очередь, наблюдение), - плашкой в окне. Вид - по значку в начале."""
    import html
    import re
    plain = html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    if not lines:
        return None
    head = lines[0]
    kind = ("warn" if head.startswith("⚠") else "err" if head.startswith(("❌", "🚨", "🔴")) else
            "ok" if head.startswith(("✅", "🏁", "🎉")) else "info")
    title = re.sub(r"^[^\wА-Яа-яЁё«(]+", "", head).strip()
    return push(kind, title, " ".join(lines[1:4]), link)


def _host_of(folder_or_url):
    from urllib.parse import urlsplit
    s = str(folder_or_url or "")
    if "://" in s:
        return urlsplit(s).netloc.removeprefix("www.")
    return os.path.basename(s.rstrip("\\/")).split("_")[0]


def _last_error(lines):
    """Последняя строка журнала проверки, похожая на ошибку (для «Подробнее»)."""
    for i in range(len(lines) - 1, -1, -1):
        ln = lines[i].strip()
        if ln.startswith("Traceback"):
            return next((x.strip() for x in reversed(lines[i:]) if x.strip()), ln)
        if ln.startswith("Сайт не открывается:") or "шибка" in ln or "Не понял адрес" in ln or "Не удалось" in ln or "не получилось" in ln:
            return ln
    return lines[-1].strip() if lines else ""


def job_finished(job, what):
    """Окно (job.py): задача закончилась. what: check | rebuild | semantics | masks | compare | list."""
    from urllib.parse import quote
    if getattr(job, "from_queue", False):
        return   # очередь сама говорит о пропущенных сайтах и об итоге (site_queue._tg)
    folder = job.out_dir or ""
    if what == "semantics":
        folder = getattr(job, "semantics_dir", "") or folder
    host = _host_of(folder or (job.sites[0] if getattr(job, "sites", None) else job.site))
    name = os.path.basename(folder)
    fresh = lambda f: os.path.exists(f) and os.path.getmtime(f) >= (job.started or 0) - 1  # noqa: E731
    if getattr(job, "was_stopped", False):
        if what == "rebuild":
            return push("info", f"Остановлено: {host}", "Отчёт обновлён не до конца: нажмите «Обновить отчёт» ещё раз.",
                        site=host)
        return push("info", f"Остановлено: {host}", "Отчёт собран по тому, что успели проверить."
                    if folder and fresh(os.path.join(folder, "отчёт.html")) else "", site=host)
    if what == "semantics":
        if folder and fresh(os.path.join(folder, "семантика.json")):
            return push("ok", f"Семантика собрана: {host}", link="/semantics?f=" + quote(name), site=host)
        return error(_last_error(job.lines), host, "Семантика не собралась")
    if what == "masks":
        # итог - по строке «маски готовы: …» (semantics/masks.py): раньше у задачи не было папки, и готовые маски
        # показывались красным «Маски не предложились: маски готовы: 18…» (gruzoperevozka23.ru 17.10.2026)
        done = next((ln.strip() for ln in reversed(job.lines) if ln.strip().startswith("маски готовы:")), "")
        if done or (folder and os.path.isdir(folder)):
            return push("warn", f"Маски семантики готовы: {host}",
                        (done[0].upper() + done[1:] + ". " if done else "") +
                        "Откройте «Семантику», выключите лишние маски и нажмите «Подтвердить маски и собрать».",
                        "/semantics?f=" + quote(name), host)
        return error(_last_error(job.lines), host, "Маски не предложились")
    if what == "compare":
        rep = getattr(job, "competitors_report", "")
        if rep and fresh(rep):
            return push("ok", f"Сравнение с конкурентами готово: {host}",
                        link="/r/" + quote(os.path.basename(os.path.dirname(rep))) + "/" + quote(os.path.basename(rep)),
                        site=host)
        return error(_last_error(job.lines), host, "Сравнение не получилось")
    if what == "list":
        res = getattr(job, "result_html", "")
        if res and os.path.exists(res):
            from . import REPORTS
            rel = os.path.relpath(res, REPORTS).replace("\\", "/")
            return push("ok", "Проверка списка адресов готова", link="/r/" + "/".join(quote(p) for p in rel.split("/")))
        return error(_last_error(job.lines), "", "Проверка списка не получилась")
    # сборку остановили из-за памяти (memory.build_stopped_text): часть файлов могла уже обновиться, и свежий отчёт.html
    # ещё не значит «готово» - раньше окно и Telegram говорили «Отчёт обновлён» (ревью кода 05.11.2026)
    mem = next((ln.strip() for ln in reversed(job.lines) if ln.strip().startswith("Нехватка памяти:")), "")
    if mem and what in ("check", "rebuild"):
        return error(mem, host, "Отчёт собран не до конца")
    rep = os.path.join(folder, "отчёт.html") if folder else ""
    if rep and fresh(rep):
        link = "/r/" + quote(name) + "/" + quote("отчёт.html")
        if what == "rebuild":
            return push("ok", f"Отчёт обновлён: {host}", link=link, site=host)
        down = getattr(job, "site_down", "")
        if down:
            return push("warn", f"Отчёт готов, но неполный: {host}",
                        f"Сайт перестал отвечать посреди проверки ({down}), отчёт по тому, что успели.", link, host)
        many = len(getattr(job, "sites", []) or []) > 1
        return push("ok", f"Отчёт готов: {host}", "Вместе со сравнением с конкурентами." if many else "", link, host)
    return error(_last_error(job.lines), host, "Отчёт обновить не получилось" if what == "rebuild" else "Проверка не получилась")
