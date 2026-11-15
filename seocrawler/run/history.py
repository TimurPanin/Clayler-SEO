"""Прошлая и более новая проверка того же сайта, продолжение прерванного обхода, сравнение двух проверок."""
import json
import os
import re

from seocrawler import compare as CMP
from seocrawler import urls as U
from seocrawler.storage import Store


_FOLDER_RX = re.compile(r"^(.*)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?$")


def previous_crawl(out_dir):
    """Папка прошлой законченной проверки этого же сайта (по имени папки), или None."""
    out_dir = os.path.abspath(out_dir)
    name = os.path.basename(out_dir)
    m = _FOLDER_RX.match(name)
    if not m:
        return None
    parent = os.path.dirname(out_dir)
    cands = []
    for d in os.listdir(parent):
        mm = _FOLDER_RX.match(d)
        if mm and mm.group(1) == m.group(1) and d < name and os.path.exists(os.path.join(parent, d, "crawl.db")):
            cands.append(d)
    # Сравниваем только с проверкой в том же режиме (с JavaScript или без): в разных режимах программа
    # видит разные картинки, ссылки и текст, и сравнение показывает сотни ложных «исправлено/новое».
    try:
        st = Store(out_dir if out_dir.endswith(".db") else os.path.join(out_dir, "crawl.db"))
        js_now = bool(st.get_meta("render_js", False))
        scope_now = st.get_meta("scope", None)
        st.db.close()
    except Exception:
        js_now, scope_now = False, None
    if scope_now and scope_now.get("mode") == "list":
        return None  # свой список адресов: прошлая проверка почти всегда про другие страницы
    other_mode = None
    for d in sorted(cands, reverse=True):
        try:
            st = Store(os.path.join(parent, d, "crawl.db"))
            done = st.get_meta("finished_at", "")
            js = bool(st.get_meta("render_js", False))
            scope = st.get_meta("scope", None)
            st.db.close()
            if scope != scope_now:
                continue  # весь сайт, другой раздел или список: сравнивать нечего
            if done and js == js_now:
                return os.path.join(parent, d)
            if done and not other_mode:
                other_mode = d
        except Exception:
            continue
    if other_mode:
        print("Прошлая проверка этого сайта была " + ("без JavaScript" if js_now else "с JavaScript")
              + " - сравнивать с ней не стал: в разных режимах результаты не сопоставимы.")
    return None


def later_crawl(out_dir):
    """Папка более новой проверки этого же сайта (по имени папки, с базой), или None - эта проверка последняя."""
    out_dir = os.path.abspath(out_dir)
    m = _FOLDER_RX.match(os.path.basename(out_dir))
    if not m:
        return None
    parent = os.path.dirname(out_dir)
    # проверка в архиве («отчёты/архив») - новее может быть в «отчёты», и наоборот
    from seocrawler.window.reports_list import ARCHIVE
    dirs = {parent, os.path.dirname(parent) if os.path.basename(parent) == os.path.basename(ARCHIVE)
            else os.path.join(parent, os.path.basename(ARCHIVE))}
    found = [os.path.join(p, d) for p in dirs if os.path.isdir(p) for d in os.listdir(p)
             if d > os.path.basename(out_dir) and (_FOLDER_RX.match(d) or [None, None])[1] == m.group(1)
             and os.path.exists(os.path.join(p, d, "crawl.db"))]
    # как previous_crawl: новее считается только проверка того же охвата (весь сайт, раздел, список) и режима
    # (с JavaScript или без) - после проверки раздела проверка всего сайта остаётся последней в своём ряду
    mine = _scope_mode(out_dir)
    found = [d for d in found if _scope_mode(d) == mine]
    return max(found, key=os.path.basename) if found else None


def _scope_mode(folder):
    """(охват, с JavaScript ли) проверки - только чтением: соседняя проверка может идти прямо сейчас."""
    import sqlite3
    from urllib.parse import quote
    try:
        db = sqlite3.connect("file:" + quote(os.path.join(folder, "crawl.db").replace("\\", "/")) + "?mode=ro",
                             uri=True, timeout=5)
        try:
            meta = {k: v for k, v in db.execute("SELECT key, value FROM meta WHERE key IN ('scope', 'render_js')")}
        finally:
            db.close()
        load = lambda v: json.loads(v) if v else None  # noqa: E731
        return load(meta.get("scope")), bool(load(meta.get("render_js")))
    except Exception:
        return None



# «Дообойти» (--continue) продолжает ту же проверку: что и как обходить - как в её начале, а не как сейчас стоит
# в форме окна (раньше проверка раздела или с JavaScript продолжалась как весь сайт или без JavaScript, маски
# «Не обходить» пропадали). Новыми берутся только лимит страниц, скорость и добавленные маски.
RESUME_KEEP = ("max_depth", "user_agent", "robots_for", "respect_robots", "use_clean_param", "max_params",
               "follow_nofollow", "regions", "check_external", "check_resources", "use_sitemap", "crawl_sitemap",
               "use_search_urls", "section", "url_list", "verify_ssl", "render_js", "render_tabs", "render_wait",
               "check_exposed")


def resume_settings(cfg, out_dir):
    try:
        st = Store(os.path.join(out_dir, "crawl.db"))
        was = st.get_meta("config", None)
        st.db.close()
    except Exception:
        return
    if not isinstance(was, dict):
        return
    keep = [k for k in RESUME_KEEP if k in was and was[k] != getattr(cfg, k)]
    if isinstance(was.get("crawl_subdomains"), bool) and was["crawl_subdomains"] != cfg.crawl_subdomains:
        keep.append("crawl_subdomains")
    for k in keep:
        setattr(cfg, k, was[k])
    # раздел /catalog/ продолжается с /catalog/, даже если в форме окна сейчас главная (тот же сайт)
    if was.get("start_url") and U.normalize(was["start_url"]) and             U.host_of(was["start_url"]) == U.host_of(cfg.start_url) and was["start_url"] != cfg.start_url:
        cfg.start_url = was["start_url"]
        keep.append("start_url")
    cfg.exclude = list(dict.fromkeys(list(was.get("exclude") or []) + cfg.exclude))
    cfg.skip_masks = list(dict.fromkeys(list(was.get("skip_masks") or []) + cfg.skip_masks))
    if keep or was.get("skip_masks"):
        print("Продолжаю с настройками начала проверки (режим, раздел, маски «Не обходить» и другие).")


def run_compare(old_dir, new_dir):
    print(f"Сравниваю с прошлой проверкой: {os.path.basename(old_dir)}")
    old, new = Store(os.path.join(old_dir, "crawl.db")), Store(os.path.join(new_dir, "crawl.db"))
    res = CMP.compare(old, new)
    info = CMP.write_compare(new_dir, res)
    old.db.close()
    new.db.close()
    return info
