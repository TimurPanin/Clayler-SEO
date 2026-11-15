"""Коллтрекинг: подменные номера телефонов. Основа - сравнение: телефоны в HTML от сервера и после
выполнения JavaScript в браузере. Если скрипт убрал номер и поставил другой - номер подменяется. Название сервиса -
только подсказка по адресу подключённого скрипта; номер, который увидит конкретный посетитель, узнать нельзя."""
import json
import re

# название сервиса -> адреса его скриптов (часть адреса, по которой узнаётся)
SERVICES = [
    ("Calltouch", r"calltouch\.ru"),
    ("CoMagic / UIS", r"comagic\.ru|uiscom\.ru"),
    ("Roistat", r"roistat\.com"),
    ("Mango Office", r"mango-office\.ru"),
    ("Callibri", r"callibri\.ru"),
    ("Alloka", r"alloka\.ru"),
    ("Calltracking.ru", r"(?<![\w-])calltracking\.ru"),
    ("Ringostat", r"ringostat\.(?:net|com)"),
]
_RX = [(name, re.compile(rx, re.I)) for name, rx in SERVICES]


_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)


def services(html_text):
    """Сервисы коллтрекинга, чьи скрипты подключены (список названий). Ищется только в тегах <script> - адрес
    и код подключения; ссылка «Calltouch» в тексте или логотип партнёра - не подключённый скрипт."""
    scripts = " ".join(a + " " + b for a, b in _SCRIPT.findall(html_text or ""))
    return [name for name, rx in _RX if rx.search(scripts)]


def _phones(contacts_json):
    try:
        return set(json.loads(contacts_json or "{}").get("phones") or [])
    except ValueError:
        return set()


def compare(raw_contacts, js_contacts, svc):
    """Сведения для колонки calltrack (JSON) или None. raw - телефоны в HTML от сервера, js - после скриптов.
    swap - номер подменяется: скрипт убрал номер из HTML и поставил другой (или сервис дописал свой номер)."""
    raw, js = _phones(raw_contacts), _phones(js_contacts)
    gone, new = raw - js, js - raw
    # без номера в HTML от сервера («телефон дорисовал скрипт» - одностраничное приложение, подвал подгружается) это
    # не подмена: скрипт мог просто вывести тот же номер
    swap = bool(new and raw and (gone or svc))
    if not swap and not svc:
        return None
    return json.dumps({"swap": swap, "raw": sorted(raw), "js": sorted(js), "svc": svc}, ensure_ascii=False)


def server_phones(p):
    """Телефоны страницы для проверок «одинаковый ли телефон»: при подмене - номера из HTML от сервера,
    а не подменённые скриптом (у каждого посетителя они свои)."""
    c = load(p)
    if c and c.get("swap"):
        return list(c.get("raw") or [])
    return None


def load(p):
    try:
        return json.loads(p.get("calltrack") or "null")
    except ValueError:
        return None
