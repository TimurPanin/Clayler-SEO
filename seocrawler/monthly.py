"""Отчёт за месяц для клиента (работа с 5-8 клиентами): что изменилось на сайте за месяц - здоровье,
что исправлено, что появилось, график здоровья по проверкам. Сравниваются последняя законченная проверка сайта и
проверка того же охвата, законченная не позже чем за 28 дней до неё (если такой нет - самая ранняя).
Считается тем же сравнением, что «сравнение.html» (compare.py: только страницы, которые открывали обе проверки), но
файл свой - «отчёт за месяц.html» в папке последней проверки и копия в «для клиента». Кнопка - на экране «Клиенты»."""
import os
import shutil
import tempfile

from . import compare as CMP
from .fmt import esc as _e

FILE = "отчёт за месяц.html"
DAYS = 28


def pick(key):
    """(старая папка, новая папка) проверок сайта для отчёта за месяц или (None, None)."""
    from .window.reports_list import REPORTS, list_reports
    g = next((x for x in list_reports()["sites"] if x["key"] == key), None)
    if not g:
        return None, None
    done = [c for c in g["checks"] if c.get("finished") and (c.get("summary") or {}).get("health") is not None]
    if len(done) < 2:
        return None, None
    last = done[0]
    same = [c for c in done[1:] if c.get("scope") == last.get("scope") and c.get("js") == last.get("js")]
    if not same:
        return None, None
    import datetime as dt
    t = lambda c: dt.datetime.strptime(c["finished"][:19], "%Y-%m-%d %H:%M:%S")
    old = next((c for c in same if (t(last) - t(c)).days >= DAYS), same[-1])
    return os.path.join(REPORTS, old["folder"]), os.path.join(REPORTS, last["folder"])


def build(key):
    """Собрать отчёт за месяц. Возвращает (путь к файлу внутри «reports», ошибка)."""
    from .storage import Store
    old_dir, new_dir = pick(key)
    if not old_dir:
        return "", "Для отчёта за месяц нужны две законченные проверки сайта в одном режиме. Проверьте сайт ещё раз."
    old, new = Store(os.path.join(old_dir, "crawl.db")), Store(os.path.join(new_dir, "crawl.db"))
    tmp = tempfile.mkdtemp(prefix="clayler-month-")
    try:
        res = CMP.compare(old, new)
        cmp = CMP.write_compare(tmp, res)   # сравнение.html - во временную папку: своё сравнение проверки не трогаем
        site = new.get_meta("start", "") or key
    finally:
        old.db.close()
        new.db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    pts = CMP.history(new_dir)
    html = _doc(site, cmp, pts)
    path = os.path.join(new_dir, FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    try:   # копия в папку для отправки клиенту
        # имя - как у остальных файлов папки (client_folder): у адреса с портом или разделом двоеточие и «/»
        # в имени файла Windows не принимает, и копия молча не появлялась
        from . import client_folder as CF
        dst = os.path.join(new_dir, CF.DIR)
        if os.path.isdir(dst):
            shutil.copyfile(path, os.path.join(dst, CF.PREFIX + CF._host(site) + CF.MONTHLY_TAIL))
    except OSError:
        pass
    return os.path.relpath(path, os.path.dirname(new_dir)).replace(os.sep, "/"), ""


def _doc(site, cmp, pts):
    from . import brand
    d0, d1 = CMP._ru_date(cmp["old_finished"]), CMP._ru_date(cmp.get("new_finished") or "")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Отчёт за месяц {_e(site)}</title><style>
:root{{--bg:#fff;--tx:#1d1d1f;--mut:#6b6b70;--bd:#e3e3e6;--acc:#3b5bdb;--good:#2f855a;--crit:#c0392b}}
body{{background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:860px;margin:0 auto;padding:24px 16px 60px}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:19px;margin:26px 0 8px}}
h3{{font-size:16px;margin:16px 0 6px}}.mut{{color:var(--mut)}}ul{{padding-left:20px}}li{{margin:3px 0}}
{brand.BRAND_CSS}</style></head><body><main>
{brand.header_html()}
<h1>Отчёт о сайте за месяц</h1>
<p class="mut">{_e(site)} · проверки {_e(d0)}{" и " + _e(d1) if d1 else ""}</p>
{CMP.client_html(cmp, pts, h2="h2", h2_cls="", cls="")}
<p class="mut">Сравнивались две проверки сайта по одним и тем же правилам. Здоровье - внутренняя оценка аудита, а не
показатель Яндекса или Google.</p>
</main></body></html>"""
