"""Журнал программы: что нажимали в окне, что закончилось и что сломалось. Вкладка «Журнал» в окне.

Файл «журнал программы.txt» в папке «данные», строка на запись:
  2026-10-16 07:12:03 | Действие | gasprofservice.ru | «Собрать заново» (Семантика)
  2026-10-16 07:15:40 | Ошибка | site.ru | Сайт не найден по этому адресу | Подробнее: getaddrinfo failed
Хранятся последние 30 дней и не больше 5 МБ: старое срезается само.
Токены, ключи и пароли в журнал не попадают никогда: известные значения из доступы.json
и всё похожее на ключ заменяется на «•••» (scrub). «Подробный журнал» проверки - отдельно, это ход обхода сайта."""
import json
import os
import re
import threading
import time

KINDS = {"action": "Действие", "event": "Уведомление", "error": "Ошибка", "info": "Сообщение"}
KIND_OF = {v: k for k, v in KINDS.items()}
KEEP_DAYS = 30
MAX_BYTES = 5_000_000
NAME = "журнал программы.txt"

_lock = threading.Lock()
_writes = 0
_secrets = {"at": 0.0, "values": []}


def _here():
    from . import paths
    return os.path.dirname(paths.data(NAME))   # «данные» (до переноса - корень)


def folder():
    """Папка журнала и уведомлений. Автотесты пишут в свою папку (CLAYLER_REPORTS), а не в папку программы."""
    return os.environ.get("CLAYLER_JOURNAL_DIR") or os.environ.get("CLAYLER_REPORTS") or _here()


def path():
    return os.path.join(folder(), NAME)


# ---------- токены и пароли - никогда в журнал ----------

_OPEN_KEYS = {"account", "since", "sites", "login", "chat_name", "bot", "day", "check", "check_ok", "user_id", "chat_id",
              "expires", "used", "units"}   # в доступы.json это не секреты: имя аккаунта, сайты, даты
_PAIR = re.compile(r"(?i)\b(access_token|refresh_token|oauth_token|token|client_secret|secret|password|passwd|пароль|"
                   r"api[_-]?key|apikey|code)(\"?\s*[:=]\s*\"?)([^\s\"'&,;|]{4,})")
_BEARER = re.compile(r"(?i)\b(bearer|oauth)\s+([^\s\"',;|]{8,})")
_BOT = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b")   # токен Telegram-бота
_LONG = re.compile(r"[A-Za-z0-9_\-.]{32,}")            # похоже на ключ: длинное, с цифрами и разным регистром


def _collect(obj, key, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) not in _OPEN_KEYS:
                _collect(v, str(k), out)
    elif isinstance(obj, list):
        for v in obj:
            _collect(v, key, out)
    elif isinstance(obj, str) and len(obj) >= 8:
        out.append(obj)
        if obj.startswith(("dpapi:", "plain:")):   # зашифрованный ключ: заменяем и его настоящее значение
            try:
                from .accounts import unseal
                out.append(unseal(obj))
            except Exception:   # noqa: BLE001 - не расшифровался, значит и в тексты попасть не мог
                pass


def _known_secrets():
    """Ключи и токены из доступы.json (раз в минуту): их заменяем, где бы они ни встретились."""
    if time.time() - _secrets["at"] < 60:
        return _secrets["values"]
    vals = []
    try:
        from .accounts import FILE
        with open(FILE, encoding="utf-8") as f:
            _collect(json.load(f), "", vals)
    except (OSError, ValueError, ImportError):
        pass
    _secrets.update(at=time.time(), values=sorted({v for v in vals if len(v) >= 8}, key=len, reverse=True))
    return _secrets["values"]


def _long(m):
    s = m.group(0)
    if re.search(r"\d", s) and re.search(r"[a-z]", s) and re.search(r"[A-Z]", s):
        return "•••"
    return s


def scrub(text):
    """Убрать из текста всё, что похоже на токен, ключ или пароль."""
    s = str(text or "")
    for v in _known_secrets():
        if v in s:
            s = s.replace(v, "•••")
    s = _BOT.sub("•••", s)
    s = _PAIR.sub(lambda m: m.group(1) + m.group(2) + "•••", s)
    s = _BEARER.sub(lambda m: m.group(1) + " •••", s)
    return _LONG.sub(_long, s)


def _field(s, limit):
    s = re.sub(r"\s*[\r\n]+\s*", " ⏎ ", scrub(s)).replace("|", "/").strip()
    return s[:limit - 1] + "…" if len(s) > limit else s


# ---------- запись и чтение ----------

def write(kind, text, site="", detail=""):
    """kind: action | event | error | info. Ошибки записи журнала программе не мешают."""
    global _writes
    line = " | ".join([time.strftime("%Y-%m-%d %H:%M:%S"), KINDS.get(kind, KINDS["info"]),
                       _field(site, 80) or "-", _field(text, 400) or "-"])
    if detail:
        line += " | Подробнее: " + _field(detail, 2000)
    try:
        with _lock:
            os.makedirs(folder(), exist_ok=True)
            with open(path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _writes += 1
            if _writes % 200 == 1:
                _trim()
    except OSError:
        pass


def _trim():
    """Оставить последние KEEP_DAYS дней и не больше MAX_BYTES (под замком)."""
    p = path()
    try:
        size = os.path.getsize(p)
        with open(p, encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        return
    old = time.strftime("%Y-%m-%d", time.localtime(time.time() - KEEP_DAYS * 86400))
    if size <= MAX_BYTES and first[:10] >= old:
        return
    with open(p, encoding="utf-8", errors="replace") as f:
        lines = [ln for ln in f if ln[:10] >= old]
    while lines and sum(len(ln.encode("utf-8")) for ln in lines) > MAX_BYTES // 2:
        lines = lines[len(lines) // 4:]
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, p)


def parse(line):
    parts = line.rstrip("\n").split(" | ")
    if len(parts) < 4:
        return None
    detail = " | ".join(parts[4:])
    return {"t": parts[0], "kind": KIND_OF.get(parts[1], "info"), "site": "" if parts[2] == "-" else parts[2],
            "text": parts[3], "detail": detail.removeprefix("Подробнее: ")}


def read(limit=500, kind="", q=""):
    """Последние записи, новые сверху. kind - один вид, q - искать в тексте и сайте."""
    try:
        with open(path(), encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    out, q = [], (q or "").strip().lower()
    for ln in reversed(lines):
        r = parse(ln)
        if not r or (kind and r["kind"] != kind) or (q and q not in ln.lower()):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out
