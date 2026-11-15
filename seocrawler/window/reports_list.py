"""Список готовых отчётов для окна программы: одна карточка на сайт (www и без www вместе),
в ней последняя проверка сверху и история прошлых. Архив - папка «reports/archive»: проверки туда
переносятся целиком и возвращаются обратно одной кнопкой."""
import json
import os
import shutil
import sqlite3

from .. import paths
from . import REPORTS
from ..urls import site_key  # noqa: F401 (RL.site_key - и для compare.py)

ARCHIVE = os.path.join(REPORTS, "archive")
# избранные сайты в «Отчётах» (звёздочка): в папке «data», рядом с очередь.json (личный файл, не в git)
FAV = paths.data("избранное.json")


def favorites():
    try:
        with open(FAV, encoding="utf-8") as f:
            d = json.load(f)
        return [str(k) for k in d.get("sites") or []] if isinstance(d, dict) else []
    except (OSError, ValueError):
        return []


def set_favorite(key, on):
    from .. import jsonfile
    key = site_key(str(key or "")) or str(key or "").strip().lower()
    if not key:
        return "Нет такого сайта."
    favs = [k for k in favorites() if k != key] + ([key] if on else [])
    jsonfile.save(FAV, {"sites": favs}, indent=1)
    return ""


# метка сайта (работа с несколькими клиентами): «клиент», «конкурент», «tests» - для экрана «Клиенты» и
# фильтра списка. Личный файл в папке «data», не в git
TAGS = os.path.join(os.path.dirname(FAV), "метки сайтов.json")
TAG_NAMES = {"client": "клиент", "rival": "конкурент", "test": "тест"}


def site_tags():
    from .. import jsonfile
    d = jsonfile.load(TAGS)
    return {str(k): v for k, v in d.items() if v in TAG_NAMES} if isinstance(d, dict) else {}


def set_site_tag(key, tag):
    from .. import jsonfile
    key = site_key(str(key or "")) or str(key or "").strip().lower()
    if not key:
        return "Нет такого сайта."
    if tag and tag not in TAG_NAMES:
        return "Нет такой метки."
    tags = site_tags()
    if tag:
        tags[key] = tag
    else:
        tags.pop(key, None)
    jsonfile.save(TAGS, tags, indent=1)
    return ""


FILES = {"has_html": "отчёт.html", "has_xlsx": "отчёт.xlsx", "has_compare": "сравнение.html",
         "has_competitors": "конкуренты.html", "has_audit": "аудит.html", "has_audit_docx": "аудит.docx",
         "has_audit_pdf": "аудит.pdf", "has_semantics": "семантика.json",
         "has_semantics_xlsx": "семантика.xlsx", "has_express_pdf": "экспресс.pdf", "has_card": "карточка.html",
         "has_client_html": "отчёт_для_клиента.html", "has_demo_pdf": "аудит_демо.pdf",
         "has_dev_files": os.path.join("для клиента", "файлы для разработчика"),
         "has_video": "видео обхода.mp4", "has_web_png": "паутина.png", "has_video_webm": "видео обхода.webm"}


def folder_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


_CACHE = {}  # {папка: (отпечаток, карточка)}
HEALTH_V2_AT = 1792045972   # 15.10.2026 15:32 (+09): новый расчёт здоровья (analyze/health.py, SITE_PENALTY)


def _built(path):
    try:
        return os.path.getmtime(os.path.join(path, "отчёт.html"))
    except OSError:
        return 0


def _stamp(path):
    """Отпечаток папки проверки: меняется, когда меняется база или появляются/пропадают файлы."""
    out = []
    for name in ("", "crawl.db", "crawl.db-wal", "отчёт.html", "для клиента"):
        try:
            st = os.stat(os.path.join(path, name))
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def read_check(base, d):
    """Карточка проверки. Запоминается до изменения папки: при сотнях проверок список отчётов каждый раз
    обходил все файлы всех папок (размер) и читал все базы, и окно открывало «Отчёты» по полминуты."""
    path = os.path.join(base, d)
    stamp = _stamp(path)
    hit = _CACHE.get(path)
    if hit and hit[0] == stamp:
        return dict(hit[1])
    item = _read_check(path, d)
    if item:
        _CACHE[path] = (stamp, item)
        return dict(item)
    _CACHE.pop(path, None)
    return None


def _read_check(path, d):
    db = os.path.join(path, "crawl.db")
    if not os.path.isdir(path) or not os.path.exists(db):
        return None
    item = {"folder": d, "size": folder_size(path)}
    for k, name in FILES.items():
        item[k] = os.path.exists(os.path.join(path, name))
    meta = {}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
        try:
            meta = {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM meta")}
        finally:
            con.close()  # иначе на Windows файл базы остаётся занятым и папку не удалить и не перенести
    except Exception:
        pass
    item.update({"site": meta.get("start") or d, "finished": meta.get("finished_at", ""),
                 "started": meta.get("started_at", ""), "js": bool(meta.get("render_js")), "scope": meta.get("scope"),
                 "version": meta.get("app_version", ""), "max_pages": meta.get("max_pages") or (meta.get("config") or {}).get("max_pages"),
                 "summary": meta.get("summary") or {}, "compare": meta.get("compare"),
                 "new_site": meta.get("new_site")})   # проект семантики нового сайта (semantics/newsite.py)
    if item["summary"].get("unchecked"):   # ни одна страница не открылась: здоровья нет, а не 0%
        item["summary"] = dict(item["summary"], health=None)
    elif item["summary"].get("health") is not None and not item["summary"].get("hv") and _built(path) < HEALTH_V2_AT:
        # отчёт собран до 15.10.2026: здоровье по старому расчёту (проблема меню давала 0%) - «Обновить отчёт»
        item["health_old"] = True
    if (item["scope"] or {}).get("mode") == "list":  # список адресов: в карточке сайт, а не первый адрес списка
        item["site"] = "/".join(item["site"].split("/", 3)[:3]) + "/"
    from ..duration import fmt, seconds
    item["took"] = fmt(seconds(meta))
    item["key"] = site_key(item["site"])
    ctry = item["summary"].get("country") or {}
    if ctry.get("code"):   # страна сайта (country.py): флаг картинкой - эмодзи-флаги Windows не рисует
        from ..country import flag_svg
        item["flag"] = flag_svg(ctry["code"], 12)
        item["country"] = ("" if ctry.get("sure") else "скорее всего ") + (ctry.get("name") or ctry["code"])
    return item


def list_checks(base):
    if not os.path.isdir(base):
        return []
    out = []
    for d in os.listdir(base):
        item = read_check(base, d)
        if item:
            out.append(item)
    # новые сверху: по времени начала, иначе по имени папки (в нём дата и время)
    out.sort(key=lambda r: (r["started"] or r["finished"] or "", r["folder"]), reverse=True)
    return out


def list_reports(busy=()):
    """{"sites": [{key, site, checks: [...новые сверху]}], "archive": [...проверки в архиве],
    "new_sites": [...проекты «Семантика нового сайта»: не проверки, в списке отчётов их нет]}"""
    groups, new = {}, []
    for item in list_checks(REPORTS):
        item["running"] = item["folder"] in busy  # с ней сейчас работает программа
        if item.get("new_site"):
            new.append({"key": item["folder"], "site": item["site"], "checks": [item], "new_site": item["new_site"]})
            continue
        g = groups.setdefault(item["key"], {"key": item["key"], "site": item["site"], "checks": []})
        g["checks"].append(item)
    sites = sorted(groups.values(), key=lambda g: g["checks"][0]["started"] or g["checks"][0]["folder"], reverse=True)
    favs, tags = set(favorites()), site_tags()
    for g in sites:
        g["tag"] = tags.get(g["key"], "")
        # показываем адрес последней проверки (с www или без — как проверяли в последний раз)
        g["site"] = g["checks"][0]["site"]
        g["fav"] = g["key"] in favs
        # «Семантика собрана»: у какой-нибудь проверки сайта есть семантика (последняя такая - для кнопок)
        g["sem_folder"] = next((c["folder"] for c in g["checks"] if c.get("has_semantics")), "")
    return {"sites": sites, "archive": [x for x in list_checks(ARCHIVE) if not x.get("new_site")], "new_sites": new}


def _safe(base, folder):
    folder = os.path.basename(folder or "")
    full = os.path.join(base, folder)
    if not folder or not os.path.isfile(os.path.join(full, "crawl.db")):
        return None
    return full


def archive(folder):
    src = _safe(REPORTS, folder)
    if not src:
        return "Нет такой проверки."
    os.makedirs(ARCHIVE, exist_ok=True)
    try:
        os.replace(src, os.path.join(ARCHIVE, os.path.basename(src)))
    except OSError as e:
        return "Не получилось перенести в архив (файлы проверки открыты в другой программе?): " + str(e)[:120]
    return ""


def unarchive(folder):
    src = _safe(ARCHIVE, folder)
    if not src:
        return "Нет такой проверки в архиве."
    try:
        os.replace(src, os.path.join(REPORTS, os.path.basename(src)))
    except OSError as e:
        return "Не получилось вернуть из архива: " + str(e)[:120]
    return ""


def delete(folder, archived=False):
    full = _safe(ARCHIVE if archived else REPORTS, folder)
    if not full:
        return "Нет такой проверки."
    try:
        shutil.rmtree(full)
    except OSError as e:
        return "Удалилось не всё (файлы открыты в другой программе?): " + str(e)[:120]
    return ""


def open_folder(folder, client=False, dev=False):
    """client — папка «для клиента»; у проверок, собранных до её появления, она заполняется тут же."""
    full = _safe(REPORTS, folder) or _safe(ARCHIVE, folder)
    if not full:
        return "Нет такой проверки."
    if client:
        from .. import client_folder as CF
        if not CF.has_files(full):
            return "Файлов для клиента в этой проверке нет. Нажмите «Ещё → Обновить отчёт»."
        try:
            full, _busy = CF.fill(full, (read_check(os.path.dirname(full), os.path.basename(full)) or {}).get("site", ""))
        except OSError as e:
            return "Не получилось собрать папку для клиента: " + str(e)[:120]
    if dev:  # готовые robots.txt, sitemap.xml, редиректы, title — внутри папки для клиента
        from .. import fix_files
        full = fix_files.folder(full)
        if not os.path.isdir(full):
            return "Файлов для разработчика в этой проверке нет. Нажмите «Ещё → Обновить отчёт»."
    try:
        os.startfile(full)  # только Windows: открыть папку в Проводнике
    except Exception as e:
        return "Не получилось открыть папку: " + str(e)[:120]
    return ""
