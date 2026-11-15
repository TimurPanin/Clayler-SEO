"""Метки состояния работы у проблем сайта: «не ошибка», «передано
разработчику», «ждёт проверки». Ставятся в отчёте (отчёт.html, открытый из окна программы) у каждой проблемы и
запоминаются для сайта, а не для одной проверки: следующая проверка того же сайта их тоже видит.
- «не ошибка» - проблема убирается из отчёта и из здоровья этого сайта (как снятая галочка в «Пороги и проверки»,
  но только для одного сайта); список таких проблем - в конце отчёта, метку можно снять.
- «передано разработчику», «ждёт проверки» - только пометка у названия проблемы, на расчёт не влияют.
Файл «метки проблем.json» в папке «data»: {сайт: {ключ проблемы: {"state", "at"}}}. Личные данные - не в git."""
import os
import time

from . import jsonfile, paths
from .urls import site_key  # noqa: F401 (labels.site_key - и для report.py)

FILE = paths.data("метки проблем.json")
STATES = {"not_error": "не ошибка", "sent": "передано разработчику", "wait": "ждёт проверки"}


def _all():
    if os.environ.get("CLAYLER_NO_USER_SETTINGS") == "1":   # автотесты: эталоны не зависят от меток
        return {}
    data = jsonfile.load(FILE)
    return data if isinstance(data, dict) else {}


def load(site):
    """{ключ проблемы: {"state", "at"}} для сайта (адрес или ключ сайта)."""
    got = _all().get(site_key(site) if "/" in (site or "") else (site or "").lower())
    return {k: v for k, v in (got or {}).items() if isinstance(v, dict) and v.get("state") in STATES}


def everything():
    """Метки всех сайтов: {ключ сайта: {ключ проблемы: {"state", "at"}}} - окно: карточка сайта и фильтры
    «Передано разработчику», «Ждёт проверки» в списке отчётов."""
    out = {}
    for site, got in _all().items():
        items = {k: v for k, v in (got or {}).items() if isinstance(v, dict) and v.get("state") in STATES}
        if items:
            out[site] = items
    return out


def not_errors(site):
    return {k for k, v in load(site).items() if v["state"] == "not_error"}


def put(site, key, state):
    """Поставить метку (state из STATES) или снять (пустая). Возвращает текст ошибки или ""."""
    site = site_key(site) if "/" in (site or "") else (site or "").lower()
    if not site or not key:
        return "Не указан сайт или проблема."
    if state and state not in STATES:
        return "Нет такой метки."
    data = _all()
    cur = data.setdefault(site, {})
    if state:
        cur[key] = {"state": state, "at": time.strftime("%Y-%m-%d %H:%M")}
    else:
        cur.pop(key, None)
    if not cur:
        data.pop(site, None)
    jsonfile.save(FILE, data, indent=1)
    return ""
