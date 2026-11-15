"""Анализ после обхода: проверки, которые видны только на всём сайте целиком.

Как устроено:
- prepare.py — общие данные (страницы, ссылки, редиректы), считаются один раз;
- checks/ — по одному файлу на тему проверок (коды ответа, title, картинки, sitemap…),
  у каждого функция run(ctx): берёт из ctx нужные данные и добавляет проблемы через ctx.add(...);
- health.py — PageRank, здоровье сайта и сводка (идёт последним: считает по всем найденным проблемам);
- common.py — Issue, важность (CRIT/WARN/NOTE), пороги, общие расчёты.
Порядок проверок важен: он же порядок проблем при равной важности и числе, а некоторые проверки
используют данные предыдущих (например, sitemap → бюджет обхода). Новую проверку — отдельным файлом
в checks/ и строкой в CHECKS."""
from types import SimpleNamespace

from .common import (FAULTS, CRIT, WARN, NOTE, SEV_RU, Issue, own_text, near_duplicates, pagerank,  # noqa: F401
                     TEMPLATE_KEYS, ALL_PAGES_KEYS)
from . import prepare, health
from ..memory import LowMemory
from .checks import (codes, private_host, https, redirects, titles, content, text_quality, indexing, hreflang, pagination, url_params, structure,
                     sitemap, images, css_js, caching, mixed_content, page_weight, speed, mirrors, sitewide_links,
                     param_explosion, anchors, relative_links, crashes, crawl_budget, url_variants, cannibalization,
                     local_seo,
                     cloaking, dup_resistance, not_found_cert, exposed_files, hacked_links, mobile_social, mobile_version, mixed_letters,
                     spelling, commercial, javascript, webmaster, search_console, search_urls, metrika, regions,
                     counters, rich, crumbs, stock, buy, inlink_anchors, speed_lab, meta_suggest, link_plan, lost_clicks)

# Проверки по порядку
CHECKS = [codes, private_host, https, redirects, titles, content, text_quality, indexing, hreflang, pagination, url_params, structure,
          sitemap, images, css_js, caching, mixed_content, page_weight, speed, mirrors, sitewide_links,
          param_explosion, anchors, relative_links, crashes, crawl_budget, url_variants, cannibalization, local_seo,
          cloaking, dup_resistance, not_found_cert, exposed_files, hacked_links, mobile_social, mobile_version, mixed_letters,
          spelling, commercial, javascript, webmaster, search_console, search_urls, metrika, regions,
          counters, rich, crumbs, stock, buy, inlink_anchors, speed_lab, meta_suggest, link_plan, lost_clicks]


# Проверена часть сайта («Только этот раздел», «Мой список адресов»): эти проблемы про связи всего сайта —
# глубину, сирот, входящие ссылки, — по части сайта они неверны (ссылки с остальных страниц не видны)
PARTIAL_HIDE = {"deep", "one_inlink", "orphans", "search_orphans", "behind_blocked", "hidden_behind_blocked", "anchors_off_topic", "anchors_menu_only",
                "crawl_waste"}


# Кому сообщать, сколько анализа сделано (0..1): crawl.py показывает это в окне при сборке отчёта
ON_PROGRESS = None


def _progress(frac):
    if ON_PROGRESS:
        try:
            ON_PROGRESS(frac)
        except LowMemory:
            raise   # памяти почти не осталось - сборку отчёта останавливаем (memory.guard в run/build)
        except Exception:
            pass


def analyze(store):
    """Все проверки по базе проверки. Возвращает (проблемы, страницы, сводка)."""
    try:
        return _analyze(store)
    finally:
        from .common import forget_strs
        forget_strs()   # словарь адресов базы (link_rows) после анализа не нужен


def _analyze(store):
    ctx = SimpleNamespace(store=store)
    FAULTS.clear()
    _progress(0.0)
    prepare.run(ctx)
    _progress(0.3)  # общие данные (страницы, ссылки, тексты) — заметная часть времени
    for n, check in enumerate(CHECKS, 1):
        check.run(ctx)
        _progress(0.3 + 0.65 * n / len(CHECKS))
    if store.get_meta("scope", None):
        ctx.issues[:] = [i for i in ctx.issues if i.key not in PARTIAL_HIDE]
        ctx.link_plan, ctx.anchor_table = [], []
    from .. import settings
    if settings.DISABLED:  # отключённые в окне программы: не показываются и не влияют на здоровье
        off = set(settings.DISABLED)
        ctx.issues[:] = [i for i in ctx.issues if i.key not in off]
    # метка «не ошибка» у проблемы этого сайта (labels.py, ставится в отчёте): так же, но только для одного сайта
    from .. import labels
    mine = labels.not_errors(store.get_meta("start", "") or "")
    hidden = [{"key": i.key, "title": i.title, "count": i.count_text} for i in ctx.issues if i.key in mine]
    if hidden:
        ctx.issues[:] = [i for i in ctx.issues if i.key not in mine]
    out = health.run(ctx)
    out[2]["labels_hidden"] = hidden
    # последним: разделы, вес и шаблоны считаются внутри health.run и тоже могут встретить испорченные данные
    crashes.data_faults(ctx)
    return out


def cached_analyze(store):
    """analyze() с сохранением результата рядом с базой (.анализ.pickle). Пересчитывается, только если изменились
    данные проверки, версия программы или пороги (settings.py). Сравнения и конкуренты не анализируют базу заново."""
    import hashlib
    import os
    import pickle
    from .. import VERSION, labels, settings
    path = os.path.join(os.path.dirname(os.path.abspath(store.path)), ".анализ.pickle")
    db = store.db
    # код проверок тоже в подписи: поправили проверку — кеш пересчитается сам, даже без смены VERSION.
    # Весь пакет seocrawler, кроме окна: проверки берут и код снаружи analyze/ (lost_clicks.py, mirror_copy.py,
    # labels.py, search_console.py…). Раньше в подписи была только analyze/, и после правки такого файла
    # «Обновить отчёт» показывал старый расчёт
    code = hashlib.md5()
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for root, dirs, files in os.walk(here):
        # run/ - запуск и сборка отчёта (раньше crawl.py, вне пакета): анализ не меняет
        dirs[:] = sorted(d for d in dirs if d not in ("window", "run", "__pycache__"))
        for f in sorted(files):
            if f.endswith(".py"):
                with open(os.path.join(root, f), "rb") as fh:
                    code.update(fh.read())
    sig = [VERSION, code.hexdigest(), hashlib.md5(repr(sorted((k, v) for k, v in vars(settings).items() if k.isupper())).encode()).hexdigest(),
           store.get_meta("finished_at", ""),
           tuple(db.execute("SELECT COUNT(*), MAX(rowid) FROM pages").fetchone()),  # tuple: у Row repr с адресом в памяти
           db.execute("SELECT COUNT(*) FROM urls").fetchone()[0],
           (store.get_meta("webmaster", None) or {}).get("fetched"),
           (store.get_meta("gsc", None) or {}).get("fetched"),
           (store.get_meta("metrika", None) or {}).get("fetched"),
           (store.get_meta("security", None) or {}).get("checked_at"),
           repr(store.get_meta("shop_sampled", None)), repr(store.get_meta("buy_clicks", None)),
           repr(store.get_meta("consent_forms", None)),  # дочитанные страницы для «Что мешает покупать»
           # дочитано при сборке (reread)
           repr(store.get_meta("redirect_ends", None)), repr(store.get_meta("sitemap_blocks", None)),
           store.get_meta("sitemap_absent", None),
           repr(sorted(labels.not_errors(store.get_meta("start", "") or ""))),   # метки «не ошибка» сайта
           len((store.get_meta("mobile_view", None) or {}).get("pages") or []),  # снимки телефона, снятые при сборке отчёта
           # семантика — для готовых заголовков и перелинковки (главный запрос группы)
           link_plan.sem_sig(os.path.dirname(os.path.abspath(store.path))),   # решения по семантике
           os.path.getmtime(os.path.join(os.path.dirname(os.path.abspath(store.path)), "семантика.json"))
           if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(store.path)), "семантика.json")) else None]
    sig = repr(sig)
    try:
        with open(path, "rb") as f:
            saved = pickle.load(f)
        if saved.get("sig") == sig:
            return saved["issues"], saved["pages"], saved["summary"]
    except Exception:
        pass   # готовый анализ не прочитался (нет файла, другая версия) - просто считаем заново
    issues, pages, summary = analyze(store)
    try:
        slim = [{k: v for k, v in p.items() if k not in ("blocks", "minhash", "text_sample", "js_text_sample", "shop")} for p in pages]
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump({"sig": sig, "issues": issues, "pages": slim, "summary": summary}, f, protocol=4)
        os.replace(tmp, path)
    except Exception:
        pass
    return issues, pages, summary
